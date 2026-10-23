"""Omnix audio service (Voice Studio Phase 4): vocal isolation, speech enhancement, watermarks.

Its models are exempt helpers (``services.helper_models``): they load beside the
TTS engine when VRAM allows, fail fast when it does not, and unload after five
idle minutes. Work runs on one thread, so two large separations never compete
for the GPU.

- ``POST /audio/isolate``: Mel-Band RoFormer (``roformer``) or Demucs
  ``htdemucs_ft`` (``demucs``) through ``audio-separator``; a vocal stem and a
  background stem (every other stem summed).
- ``POST /audio/enhance``: sherpa-onnx's offline denoiser with GTCRN. It works
  at 16 kHz, so the result is 16 kHz mono speech.
- ``POST /audio/watermark`` and ``POST /audio/watermark/detect``: AudioSeal
  (16-bit messages). Marking happens at 16 kHz and the watermark is resampled
  back to the file's own rate and added, so the audio keeps its rate.

Weights live under ``resources/models/audio``. The separator and AudioSeal
fetch theirs on first use; GTCRN is downloaded from the sherpa-onnx release.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import shutil
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from app.config.env import env_int
from app.runtime.net import bind_host
from app.security.model_service import ModelServiceMiddleware
from services.helper_models import HelperModel, HelperUnavailable, free_vram_gb

logger = logging.getLogger(__name__)

# AudioSeal's SEANet layers torch.compile themselves unless this is set, and compiling needs
# Triton, which has no Windows build. Eager mode is fast enough for marking renders.
os.environ.setdefault("NO_TORCH_COMPILE", "1")

IDLE_UNLOAD_SECONDS = 300.0
WATERMARK_RATE = 16_000
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
SEPARATION_MODELS = {
    "roformer": ("vocals_mel_band_roformer.ckpt", "Mel-Band RoFormer (vocals)"),
    "demucs": ("htdemucs_ft.yaml", "Demucs htdemucs_ft"),
}
GTCRN_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/speech-enhancement-models/gtcrn_simple.onnx"
EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="omnix-audio")

app = FastAPI(title="Omnix audio tools", version="1.0.0")
app.add_middleware(ModelServiceMiddleware)


class ModelMissing(HelperUnavailable):
    """The tool's weights are not set up; retrying cannot help."""


def models_root() -> Path:
    from app.runtime.paths import resources_models_root

    return resources_models_root() / "audio"


# --- Audio helpers ---------------------------------------------------------------------------------


def decode(payload: bytes) -> tuple[np.ndarray, int]:
    """Float samples (frames x channels) and the rate of any file soundfile reads."""
    samples, rate = sf.read(io.BytesIO(payload), dtype="float32", always_2d=True)
    return samples, int(rate)


def mono(samples: np.ndarray) -> np.ndarray:
    return samples.mean(axis=1) if samples.ndim > 1 else samples


def wav_bytes(samples: np.ndarray, rate: int) -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, np.clip(samples, -1.0, 1.0), rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def resample(samples: np.ndarray, source: int, target: int) -> np.ndarray:
    """Band-limited resampling along the first axis."""
    if source == target or not len(samples):
        return samples
    from scipy.signal import resample_poly

    divisor = int(np.gcd(source, target))
    return resample_poly(samples, target // divisor, source // divisor, axis=0).astype(np.float32)


def message_bits(message: int) -> list[int]:
    return [(int(message) >> (15 - index)) & 1 for index in range(16)]


def bits_message(bits: Any) -> int:
    value = 0
    for bit in [int(round(float(bit))) for bit in list(bits)][:16]:
        value = (value << 1) | (bit & 1)
    return value


# --- Models ----------------------------------------------------------------------------------------


def ensure_ffmpeg() -> str:
    """Put an ``ffmpeg`` executable on this process's PATH (audio-separator calls it by name).

    PATH wins; otherwise ``OMNIX_FFMPEG`` (the launcher sets it to the repository's
    bundled imageio-ffmpeg binary) or that bundled binary is linked as
    ``resources/models/audio/bin/ffmpeg(.exe)``.
    """
    found = shutil.which("ffmpeg")
    if found:
        return found
    from app.config.env import env_str

    root = Path(__file__).resolve().parents[3]
    candidates = [env_str("OMNIX_FFMPEG", "") or "",
                  *sorted(str(path) for path in (root / "venv" / "Lib" / "site-packages" / "imageio_ffmpeg"
                                                  / "binaries").glob("ffmpeg*.exe"))]
    source = next((Path(value) for value in candidates if value and Path(value).is_file()), None)
    if source is None:
        raise ModelMissing("FFmpeg is required for vocal isolation; set OMNIX_FFMPEG or add ffmpeg to PATH")
    folder = models_root() / "bin"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if not target.is_file():
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)
    os.environ["PATH"] = f"{folder}{os.pathsep}{os.environ.get('PATH', '')}"
    return str(target)


def _load_separator(model: str) -> Any:
    from audio_separator.separator import Separator

    ensure_ffmpeg()

    filename, _label = SEPARATION_MODELS[model]
    directory = models_root() / "separator"
    directory.mkdir(parents=True, exist_ok=True)
    separator = Separator(model_file_dir=str(directory), output_dir=str(directory / "out"), output_format="WAV",
                          use_soundfile=True, log_level=logging.WARNING)
    try:
        separator.load_model(model_filename=filename)
    except Exception as exc:
        logger.warning("Separation model %s could not be loaded", filename, exc_info=True)
        raise ModelMissing(f"The {model} separation model could not be loaded or downloaded; "
                           "see the audio service log") from exc
    return separator


def _load_denoiser() -> Any:
    import sherpa_onnx

    path = models_root() / "gtcrn" / "gtcrn_simple.onnx"
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            urllib.request.urlretrieve(GTCRN_URL, path)  # noqa: S310 - fixed https release URL
        except Exception as exc:
            path.unlink(missing_ok=True)
            logger.warning("GTCRN download failed", exc_info=True)
            raise ModelMissing("The GTCRN enhancement model could not be downloaded; see the audio service log") from exc
    config = sherpa_onnx.OfflineSpeechDenoiserConfig(
        model=sherpa_onnx.OfflineSpeechDenoiserModelConfig(
            gtcrn=sherpa_onnx.OfflineSpeechDenoiserGtcrnModelConfig(model=str(path)),
            num_threads=2,
            provider="cpu",
        ),
    )
    return sherpa_onnx.OfflineSpeechDenoiser(config)


def _load_watermarker() -> Any:
    from audioseal import AudioSeal

    try:
        generator = AudioSeal.load_generator("audioseal_wm_16bits")
        detector = AudioSeal.load_detector("audioseal_detector_16bits")
    except Exception as exc:
        logger.warning("AudioSeal could not be loaded", exc_info=True)
        raise ModelMissing("AudioSeal could not be loaded or downloaded; see the audio service log") from exc
    device = "cuda" if free_vram_gb() is not None else "cpu"
    return generator.to(device).eval(), detector.to(device).eval(), device


SEPARATORS = {name: HelperModel(label, 2.0, lambda name=name: _load_separator(name))
              for name, (_filename, label) in SEPARATION_MODELS.items()}
DENOISER = HelperModel("GTCRN speech enhancement", 0.0, _load_denoiser)
WATERMARKER = HelperModel("AudioSeal", 0.5, _load_watermarker)
HELPERS = [*SEPARATORS.values(), DENOISER, WATERMARKER]


# --- Tools -----------------------------------------------------------------------------------------


def isolate(payload: bytes, filename: str, model: str) -> dict[str, Any]:
    separator = SEPARATORS[model].get()
    suffix = Path(filename or "audio.wav").suffix or ".wav"
    with tempfile.TemporaryDirectory(prefix="omnix-isolate-") as work:
        source = Path(work) / f"source{suffix}"
        source.write_bytes(payload)
        separator.output_dir = work
        if hasattr(separator, "model_instance") and separator.model_instance is not None:
            separator.model_instance.output_dir = work
        outputs = [Path(work) / Path(name).name for name in separator.separate(str(source))]
        vocals = [path for path in outputs if "(vocals)" in path.name.casefold()]
        others = [path for path in outputs if path not in vocals]
        if not vocals or not others:
            raise RuntimeError(f"the separator returned no vocal and background stems: {[p.name for p in outputs]}")
        voice, rate = sf.read(str(vocals[0]), dtype="float32", always_2d=True)
        background = None
        for path in others:
            stem, stem_rate = sf.read(str(path), dtype="float32", always_2d=True)
            stem = resample(stem, stem_rate, rate)
            background = stem if background is None else background[: len(stem)] + stem[: len(background)]
    return {"vocals": base64.b64encode(wav_bytes(voice, rate)).decode("ascii"),
            "background": base64.b64encode(wav_bytes(background, rate)).decode("ascii"),
            "sample_rate": rate, "model": SEPARATION_MODELS[model][1]}


def enhance(payload: bytes) -> dict[str, Any]:
    denoiser = DENOISER.get()
    samples, rate = decode(payload)
    result = denoiser.run(np.ascontiguousarray(mono(samples), dtype=np.float32), rate)
    cleaned = np.asarray(result.samples, dtype=np.float32)
    return {"audio": base64.b64encode(wav_bytes(cleaned, int(result.sample_rate))).decode("ascii"),
            "sample_rate": int(result.sample_rate), "model": DENOISER.label}


def watermark(payload: bytes, message: int) -> dict[str, Any]:
    import torch

    generator, _detector, device = WATERMARKER.get()
    samples, rate = decode(payload)
    voice = mono(samples)
    with torch.no_grad():
        at_16k = torch.from_numpy(resample(voice, rate, WATERMARK_RATE)).to(device)[None, None, :]
        bits = torch.tensor([message_bits(message)], dtype=torch.int32, device=device)
        mark = generator.get_watermark(at_16k, WATERMARK_RATE, message=bits)[0, 0].float().cpu().numpy()
    mark = resample(mark, WATERMARK_RATE, rate)
    length = min(len(mark), len(samples))
    marked = samples.copy()
    marked[:length] += mark[:length, None]
    return {"audio": base64.b64encode(wav_bytes(marked, rate)).decode("ascii"), "sample_rate": rate,
            "model": "audioseal_wm_16bits", "message": int(message)}


def detect(payload: bytes) -> dict[str, Any]:
    import torch

    _generator, detector, device = WATERMARKER.get()
    samples, rate = decode(payload)
    with torch.no_grad():
        at_16k = torch.from_numpy(resample(mono(samples), rate, WATERMARK_RATE)).to(device)[None, None, :]
        probability, message = detector.detect_watermark(at_16k, WATERMARK_RATE)
    probability = float(probability)
    return {"probability": round(probability, 4), "detected": probability >= 0.5,
            "message": bits_message(message[0]) if probability >= 0.5 else None}


# --- Routes ----------------------------------------------------------------------------------------


async def _read(upload: UploadFile) -> bytes:
    payload = await upload.read(MAX_UPLOAD_BYTES + 1)  # never more than one byte past the cap
    if not payload:
        raise HTTPException(status_code=400, detail="empty_audio")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="upload_too_large")
    return payload


async def _run(function: Any, *args: Any) -> dict[str, Any]:
    """Run a tool on the worker thread.

    ModelServiceMiddleware replaces every error body, so outcomes the caller acts on travel as
    200 envelopes written here: ``model_missing`` (set up the model), ``model_busy`` (VRAM is
    short now) and ``decode_failed`` (unreadable audio).
    """
    try:
        return await asyncio.get_running_loop().run_in_executor(EXECUTOR, function, *args)
    except ModelMissing as exc:
        return {"ok": False, "code": "model_missing", "message": str(exc)}
    except HelperUnavailable as exc:
        return {"ok": False, "code": "model_busy", "message": str(exc)}
    except sf.LibsndfileError:
        logger.warning("Audio tool could not decode the upload", exc_info=True)
        return {"ok": False, "code": "decode_failed", "message": "The audio could not be decoded"}


@app.get("/health")
def health() -> dict[str, Any]:
    tools = {
        "isolate": {"models": {name: {"label": label, "loaded": SEPARATORS[name].loaded}
                               for name, (_filename, label) in SEPARATION_MODELS.items()}},
        "enhance": {"model": DENOISER.label, "loaded": DENOISER.loaded,
                    "installed": (models_root() / "gtcrn" / "gtcrn_simple.onnx").is_file()},
        "watermark": {"model": "audioseal_wm_16bits", "loaded": WATERMARKER.loaded},
    }
    free = free_vram_gb()
    return {"ok": True, "status": "ready", "tools": tools,
            "gpu": {"vram_free_bytes": int(free * 1024 ** 3)} if free is not None else {}}


@app.post("/audio/isolate")
async def isolate_route(file: UploadFile = File(...), model: str = Form("roformer")) -> dict[str, Any]:  # noqa: B008
    if model not in SEPARATION_MODELS:
        raise HTTPException(status_code=400, detail="invalid_request")
    return await _run(isolate, await _read(file), file.filename or "audio.wav", model)


@app.post("/audio/enhance")
async def enhance_route(file: UploadFile = File(...)) -> dict[str, Any]:  # noqa: B008
    return await _run(enhance, await _read(file))


@app.post("/audio/watermark")
async def watermark_route(file: UploadFile = File(...), message: int = Form(0)) -> dict[str, Any]:  # noqa: B008
    if not 0 <= message < 2 ** 16:
        raise HTTPException(status_code=400, detail="invalid_request")
    return await _run(watermark, await _read(file), message)


@app.post("/audio/watermark/detect")
async def detect_route(file: UploadFile = File(...)) -> dict[str, Any]:  # noqa: B008
    return await _run(detect, await _read(file))


@app.on_event("startup")
async def unload_idle_helpers() -> None:
    async def loop() -> None:
        while True:
            await asyncio.sleep(60)
            for helper in HELPERS:
                if await asyncio.get_running_loop().run_in_executor(EXECUTOR, helper.unload_if_idle, IDLE_UNLOAD_SECONDS):
                    logger.info("Unloaded idle %s", helper.label)

    app.state.unload_task = asyncio.create_task(loop())


def main() -> None:
    from app.observability.logging import configure_logging

    configure_logging()
    host = bind_host()
    port = env_int("OMNIX_AUDIO_PORT", 5401, minimum=1, maximum=65535)
    print(f"[AUDIO] Starting audio tools on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
