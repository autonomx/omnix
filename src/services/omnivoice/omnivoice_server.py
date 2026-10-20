"""OmniVoice child server (Voice Studio Phase 5), started by the TTS service's ``omnivoice`` provider.

OmniVoice (k2-fsa, 600+ languages, zero-shot cloning) needs transformers 5,
which the Qwen TTS environment cannot take, so it runs here, in the
``omnix-omnivoice`` environment, as a child process of whichever Omnix process
owns TTS. Stopping the process releases all of its GPU memory, which is how the
engine is swapped out.

The server binds to loopback only and accepts requests only with the token the
provider generated for this launch (``OMNIX_CHILD_TOKEN``). It imports nothing
from Omnix: its environment has none of Omnix's packages.

    python omnivoice_server.py --model-dir DIR --port 5103
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import io
import logging
import os
import threading
from typing import Any

import numpy as np
import soundfile as sf
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

logger = logging.getLogger("omnivoice-server")
SAMPLE_RATE = 24_000
MAX_TEXT_CHARS = 5_000
_PROMPT_CACHE_SIZE = 16

app = FastAPI(title="Omnix OmniVoice", version="1.0.0")
_STATE: dict[str, Any] = {"model": None, "model_dir": "", "error": ""}
_LOCK = threading.Lock()
_PROMPTS: dict[str, Any] = {}


class GenerateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    # A reference clip (base64 WAV) and its exact words, for cloning; neither for an automatic voice.
    ref_audio: str = ""
    ref_text: str = ""
    # Speaker attributes ("female, low pitch, british accent") when no reference is given.
    instruct: str = Field(default="", max_length=600)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    duration: float | None = Field(default=None, gt=0, le=600)
    num_step: int = Field(default=32, ge=4, le=64)
    # Classifier-free guidance strength and token sampling temperature (OmniVoiceGenerationConfig).
    guidance_scale: float | None = Field(default=None, ge=0.5, le=5.0)
    class_temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    # An ISO code or language name; unknown values fall back to language-agnostic mode.
    language: str = Field(default="", max_length=32)
    seed: int | None = None


@app.middleware("http")
async def require_token(request: Request, call_next):
    expected = os.environ.get("OMNIX_CHILD_TOKEN", "")
    if request.url.path != "/health":
        supplied = request.headers.get("x-omnix-child-token", "")
        if not expected or not hmac.compare_digest(expected.encode(), supplied.encode()):
            return Response(status_code=401, content=b'{"error":"invalid_child_token"}', media_type="application/json")
    return await call_next(request)


def load(model_dir: str) -> None:
    import torch
    from omnivoice import OmniVoice

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device.startswith("cuda") else torch.float32
    _STATE["model"] = OmniVoice.from_pretrained(model_dir, device_map=device, dtype=dtype)
    _STATE["model_dir"] = model_dir


def _seeded(seed: int | None) -> None:
    if seed is None:
        return
    import random

    import torch

    random.seed(seed)
    np.random.seed(seed % (2 ** 32))
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _clone_prompt(model: Any, ref_audio: bytes, ref_text: str) -> Any:
    """The encoded reference, cached by content: a voice is encoded once per server lifetime."""
    key = hashlib.sha256(ref_audio + b"\0" + ref_text.encode("utf-8")).hexdigest()
    if key in _PROMPTS:
        return _PROMPTS[key]
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        handle.write(ref_audio)
        path = handle.name
    try:
        prompt = model.create_voice_clone_prompt(ref_audio=path, ref_text=ref_text or None)
    finally:
        os.unlink(path)
    if len(_PROMPTS) >= _PROMPT_CACHE_SIZE:
        _PROMPTS.pop(next(iter(_PROMPTS)))
    _PROMPTS[key] = prompt
    return prompt


@app.get("/health")
def health() -> dict[str, Any]:
    free = total = None
    try:
        import torch

        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
    except Exception:
        logger.debug("CUDA memory query failed", exc_info=True)
    return {"ok": _STATE["model"] is not None, "model_dir": _STATE["model_dir"], "error": _STATE["error"],
            "sample_rate": SAMPLE_RATE, "vram_free_bytes": free, "vram_total_bytes": total}


@app.post("/generate")
def generate(request: GenerateRequest) -> Response:
    model = _STATE["model"]
    if model is None:
        raise HTTPException(status_code=503, detail="model_not_loaded")
    options: dict[str, Any] = {"num_step": request.num_step}
    if request.guidance_scale is not None:
        options["guidance_scale"] = request.guidance_scale
    if request.class_temperature is not None:
        options["class_temperature"] = request.class_temperature
    if request.language.strip():
        options["language"] = request.language.strip()
    if request.duration:
        options["duration"] = request.duration
    else:
        options["speed"] = request.speed
    with _LOCK:
        if request.ref_audio:
            options["voice_clone_prompt"] = _clone_prompt(model, base64.b64decode(request.ref_audio), request.ref_text)
        elif request.instruct.strip():
            options["instruct"] = request.instruct.strip()
        _seeded(request.seed)
        audio = model.generate(text=request.text, **options)
    samples = np.asarray(audio[0], dtype=np.float32).reshape(-1)
    peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
    if peak > 0.99:
        samples = samples * (0.99 / peak)
    buffer = io.BytesIO()
    sf.write(buffer, samples, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return Response(content=buffer.getvalue(), media_type="audio/wav",
                    headers={"X-Omnix-Sample-Rate": str(SAMPLE_RATE),
                             "X-Omnix-Duration": f"{len(samples) / SAMPLE_RATE:.3f}"})


def main() -> None:
    parser = argparse.ArgumentParser(description="OmniVoice child server for Omnix")
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--port", type=int, default=5103)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        load(args.model_dir)
    except Exception as exc:
        _STATE["error"] = f"{type(exc).__name__}: {exc}"
        logger.exception("OmniVoice failed to load from %s", args.model_dir)
        raise SystemExit(3) from exc
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
