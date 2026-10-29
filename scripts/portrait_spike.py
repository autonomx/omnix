"""Live portrait Phase 0 spike: FLOAT streamed through a hop scheduler (docs/architecture/OMNIX_LIVE_PORTRAIT_ROADMAP.md).

Standalone research script. It imports upstream FLOAT from a local clone, never from the Omnix tree, and
changes no product code. It measures, on the GPU it runs on:

- quality: how far streamed motion latents land from upstream's whole-clip output, per R/H/normalization,
  next to the noise floor (whole clip vs whole clip with another seed);
- timing: one pass (wav2vec2 + FMT) per nfe, decode per micro-batch size in fp32/fp16, VRAM peak;
- first frame: when the first frames could be ready against the browser's 0.4 s start buffer, per TTS speed.

It refuses to start while the GPU is busy or a model gate appears to be running, so it can't disturb
another session's measurements (pass --allow-busy to override).

    venv/Scripts/python.exe scripts/portrait_spike.py --upstream <float clone> --image <512 portrait> \
        --audio a.wav b.wav --out <dir>
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

FPS = 25
SAMPLE_RATE = 16_000
SAMPLES_PER_FRAME = SAMPLE_RATE // FPS  # 640
WINDOW = 50
CARRY = 10
NEUTRAL = 4  # upstream label2id["neutral"]
START_BUFFER_S = 0.4  # browser START_BUFFER_SECONDS
BUSY_VRAM_BYTES = 3 * 1024**3
GATE_MARKERS = ("pytest", "release_gate", "benchmark", "playthrough", "eval", "latency", "narration", "intent")


# --------------------------------------------------------------------------- guard


def busy_reasons(allow_busy: bool) -> list[str]:
    """Why running now could disturb another session's measurements."""
    if allow_busy:
        return []
    import psutil
    import torch

    reasons: list[str] = []
    free, total = torch.cuda.mem_get_info()
    if total - free > BUSY_VRAM_BYTES:
        reasons.append(f"GPU has {(total - free) / 1024**3:.1f} GB in use by other processes")
    me = os.getpid()
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (proc.info["name"] or "").lower()
            if proc.info["pid"] == me or not name.startswith("python"):
                continue
            cmd = " ".join(proc.info["cmdline"] or []).lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if "portrait_spike" in cmd:
            continue
        hits = [m for m in GATE_MARKERS if m in cmd]
        if hits or "services.tts" in cmd or "services.stt" in cmd:
            reasons.append(f"pid {proc.info['pid']} looks like a gate or model service: {cmd[:140]}")
    return reasons


def lower_priority() -> None:
    import psutil

    try:
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt" else 10)
    except Exception:  # noqa: BLE001 - best effort only
        pass


# --------------------------------------------------------------------------- model


class NoEmotionEncoder:
    """Stands in for upstream's 1.2 GB Audio2Emotion when the emotion is given as a label."""

    label2id = {"angry": 0, "disgust": 1, "fear": 2, "happy": 3, "neutral": 4, "sad": 5, "surprise": 6}

    def __init__(self, opt):  # noqa: ARG002 - same signature as upstream
        pass

    def predict_emotion(self, *_args, **_kwargs):
        raise RuntimeError("speech-to-emotion is disabled in this spike")


def load_float(upstream: Path, checkpoints: Path, *, with_emotion_model: bool, nfe: int):
    import torch

    sys.path.insert(0, str(upstream))
    import models.float.FLOAT as float_module  # upstream, unmodified
    from models.wav2vec2 import Wav2VecModel
    from options.base_options import BaseOptions

    # Upstream's forward sets config.output_attentions, which current transformers refuses under SDPA.
    load = Wav2VecModel.from_pretrained.__func__
    Wav2VecModel.from_pretrained = classmethod(lambda cls, *a, **k: load(cls, *a, attn_implementation="eager", **k))
    if not with_emotion_model:
        float_module.Audio2Emotion = NoEmotionEncoder
    parser = BaseOptions().initialize(argparse.ArgumentParser())
    opt = parser.parse_args([])
    opt.rank, opt.ngpus = 0, 1
    opt.nfe = nfe
    opt.wav2vec_model_path = str(checkpoints / "wav2vec2-base-960h")
    opt.audio2emotion_path = str(checkpoints / "wav2vec-english-speech-emotion-recognition")
    model = float_module.FLOAT(opt)
    state = torch.load(checkpoints / "float.pth", map_location="cpu", weights_only=True)
    with torch.no_grad():
        for name, param in model.named_parameters():
            if name in state:
                param.copy_(state[name])
    del state
    return model.to("cuda").eval(), opt


def load_portrait(path: Path):
    import numpy as np
    import torch
    from PIL import Image

    img = Image.open(path).convert("RGB").resize((512, 512), Image.LANCZOS)
    arr = (np.asarray(img).astype("float32") / 255.0 - 0.5) / 0.5
    return torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).cuda()


def load_audio(path: Path):
    import librosa

    audio, _ = librosa.load(str(path), sr=SAMPLE_RATE)
    return audio.astype("float32")


def normalize(audio):
    import numpy as np

    return (audio - audio.mean()) / np.sqrt(audio.var() + 1e-7)


@dataclass
class Portrait:
    s_r: object
    s_r_feats: list
    r_s: object
    we: object


def encode_portrait(model, image) -> Portrait:
    import torch
    import torch.nn.functional as F

    s_r, r_s_lambda, s_r_feats = model.encode_image_into_latent(image)
    r_s = model.motion_autoencoder.dec.direction(r_s_lambda)
    we = F.one_hot(torch.tensor(NEUTRAL, device="cuda"), num_classes=7).float().view(1, 1, 7)
    return Portrait(s_r, s_r_feats, r_s, we)


# --------------------------------------------------------------------------- motion


def audio_features(model, audio_norm, frames: int):
    """Projected wav2vec2 features, one per video frame, for exactly ``frames`` frames of audio."""
    import torch

    a = torch.from_numpy(audio_norm[: frames * SAMPLES_PER_FRAME]).unsqueeze(0).cuda()
    return model.audio_encoder.audio_projection(model.audio_encoder.get_wav2vec2_feature(a, seq_len=frames))


def solve_window(model, opt, portrait: Portrait, wa_t, prev_x, prev_wa, seed: int):
    import torch
    from torchdiffeq import odeint

    g = torch.Generator("cuda").manual_seed(seed)
    x0 = torch.randn(1, WINDOW, opt.dim_w, device="cuda", generator=g)
    time_points = torch.linspace(0, 1, opt.nfe, device="cuda")

    def field_fn(tt, zt):
        out = model.fmt.forward_with_cfv(
            t=tt.unsqueeze(0), x=zt, wa=wa_t, wr=portrait.r_s, we=portrait.we,
            prev_x=prev_x, prev_wa=prev_wa,
            a_cfg_scale=opt.a_cfg_scale, r_cfg_scale=opt.r_cfg_scale, e_cfg_scale=opt.e_cfg_scale,
        )
        return out[:, CARRY:]

    return odeint(field_fn, x0, time_points, method="euler")[-1]


def whole_clip_latents(model, opt, portrait: Portrait, audio, seed: int):
    """Upstream's method: whole-clip features, non-overlapping windows, zero first carry."""
    import torch
    import torch.nn.functional as F

    import numpy as np

    frames = math.ceil(len(audio) / SAMPLES_PER_FRAME)
    padded = np.pad(normalize(audio), (0, frames * SAMPLES_PER_FRAME - len(audio)), mode="edge")
    wa = audio_features(model, padded, frames)
    out, prev_x, prev_wa = [], torch.zeros(1, CARRY, opt.dim_w, device="cuda"), torch.zeros(1, CARRY, opt.dim_w, device="cuda")
    for index in range(math.ceil(frames / WINDOW)):
        wa_t = wa[:, index * WINDOW:(index + 1) * WINDOW]
        if wa_t.shape[1] < WINDOW:
            wa_t = F.pad(wa_t.transpose(1, 2), (0, WINDOW - wa_t.shape[1]), mode="replicate").transpose(1, 2)
        sample = solve_window(model, opt, portrait, wa_t, prev_x, prev_wa, seed + index)
        out.append(sample)
        prev_x, prev_wa = sample[:, -CARRY:], wa_t[:, -CARRY:]
    return torch.cat(out, dim=1)[:, :frames]


@dataclass
class PassRecord:
    start: int
    committed: int
    audio_frames_needed: int
    features_ms: float
    fmt_ms: float


@dataclass
class StreamConfig:
    lookahead_frames: int  # R
    first_hop: int  # H1
    min_hop: int  # smallest H for later passes
    context_frames: int  # audio context before s for wav2vec2
    norm: str  # "buffer" or "running"


def streamed_latents(model, opt, portrait: Portrait, audio, cfg: StreamConfig, seed: int):
    """The roadmap's hop scheduler, fed as if audio arrived progressively; returns latents and passes."""
    import numpy as np
    import torch
    import torch.nn.functional as F

    total = math.ceil(len(audio) / SAMPLES_PER_FRAME)
    audio = np.pad(audio, (0, total * SAMPLES_PER_FRAME - len(audio)), mode="edge")
    latents = torch.zeros(1, 0, opt.dim_w, device="cuda")
    feats = torch.zeros(1, 0, opt.dim_w, device="cuda")
    passes: list[PassRecord] = []
    s = 0
    while s < total:
        hop = cfg.first_hop if s == 0 else cfg.min_hop
        avail = min(total, s + hop + cfg.lookahead_frames)  # the pass runs as soon as this much audio exists
        final = avail >= total
        b0, b1 = max(0, s - cfg.context_frames), min(avail, s + WINDOW)
        buffer = audio[b0 * SAMPLES_PER_FRAME:b1 * SAMPLES_PER_FRAME]
        stats = audio[: avail * SAMPLES_PER_FRAME] if cfg.norm == "running" else buffer
        buffer = (buffer - stats.mean()) / np.sqrt(stats.var() + 1e-7)

        torch.cuda.synchronize()
        t0 = time.perf_counter()
        wa_buf = audio_features(model, buffer, b1 - b0)
        torch.cuda.synchronize()
        t1 = time.perf_counter()
        wa_t = wa_buf[:, s - b0:]
        if wa_t.shape[1] < WINDOW:
            wa_t = F.pad(wa_t.transpose(1, 2), (0, WINDOW - wa_t.shape[1]), mode="replicate").transpose(1, 2)
        prev_x, prev_wa = latents[:, -CARRY:], feats[:, -CARRY:]
        if prev_x.shape[1] < CARRY:  # the first carry is zeros, as upstream's
            pad = CARRY - prev_x.shape[1]
            prev_x = torch.cat([torch.zeros(1, pad, opt.dim_w, device="cuda"), prev_x], dim=1)
            prev_wa = torch.cat([torch.zeros(1, pad, opt.dim_w, device="cuda"), prev_wa], dim=1)
        sample = solve_window(model, opt, portrait, wa_t, prev_x, prev_wa, seed + len(passes))
        torch.cuda.synchronize()
        t2 = time.perf_counter()

        commit = min(WINDOW, total - s) if final else max(1, min(WINDOW, avail - cfg.lookahead_frames - s))
        latents = torch.cat([latents, sample[:, :commit]], dim=1)
        feats = torch.cat([feats, wa_t[:, :commit]], dim=1)
        passes.append(PassRecord(s, commit, avail, (t1 - t0) * 1000, (t2 - t1) * 1000))
        s += commit
    return latents, passes


def latent_distance(a, b) -> float:
    """Mean per-frame L2 distance, relative to the mean norm of ``b``'s frames."""
    frames = min(a.shape[1], b.shape[1])
    a, b = a[:, :frames], b[:, :frames]
    return float((a - b).norm(dim=-1).mean() / b.norm(dim=-1).mean())


# --------------------------------------------------------------------------- decode


def decode(model, portrait: Portrait, latents, batch: int, fp16: bool):
    import torch

    frames = []
    for start in range(0, latents.shape[1], batch):
        chunk = latents[0, start:start + batch]
        size = chunk.shape[0]
        feats = [f.expand(size, *f.shape[1:]) for f in portrait.s_r_feats]
        with torch.autocast("cuda", dtype=torch.float16, enabled=fp16):
            img, _ = model.motion_autoencoder.dec(portrait.s_r + chunk, alpha=None, feats=feats)
        frames.append(img.float())
    return torch.cat(frames, dim=0)


def time_decode(model, portrait: Portrait, latents, batch: int, fp16: bool, repeats: int = 3) -> float:
    import torch

    decode(model, portrait, latents[:, :batch], batch, fp16)  # warm-up
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(repeats):
        decode(model, portrait, latents[:, :batch * 4], batch, fp16)
    torch.cuda.synchronize()
    return (time.perf_counter() - t0) * 1000 / (repeats * batch * 4)


def write_video(frames, audio_path: Path, out_path: Path) -> Path:
    import torch
    import torchvision

    video = ((frames.clamp(-1, 1) + 1) / 2 * 255).to(torch.uint8).permute(0, 2, 3, 1).cpu()
    silent = out_path.with_suffix(".silent.mp4")
    torchvision.io.write_video(str(silent), video, fps=FPS)
    ffmpeg = shutil.which("ffmpeg") or os.environ.get("OMNIX_FFMPEG")
    if not ffmpeg:
        return silent
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(silent), "-i", str(audio_path),
                    "-c:v", "copy", "-c:a", "aac", "-shortest", str(out_path)], check=True)
    silent.unlink()
    return out_path


# --------------------------------------------------------------------------- main


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--upstream", type=Path, required=True, help="clone of deepbrainai-research/float")
    parser.add_argument("--checkpoints", type=Path, help="defaults to <upstream>/checkpoints")
    parser.add_argument("--image", type=Path, required=True, help="a face portrait, already cropped")
    parser.add_argument("--audio", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--videos", type=int, default=2, help="side-by-side videos to write (first N clips)")
    parser.add_argument("--seed", type=int, default=25)
    parser.add_argument("--allow-busy", action="store_true")
    args = parser.parse_args()
    checkpoints = args.checkpoints or args.upstream / "checkpoints"
    args.out.mkdir(parents=True, exist_ok=True)

    import torch

    reasons = busy_reasons(args.allow_busy)
    if reasons:
        print("Not starting; the machine looks busy:\n  " + "\n  ".join(reasons))
        return 2
    lower_priority()
    torch.backends.cudnn.benchmark = True
    results: dict = {"gpu": torch.cuda.get_device_name(0), "torch": torch.__version__, "clips": {}}

    with torch.no_grad():
        # VRAM: with and without upstream's emotion model.
        base = torch.cuda.memory_allocated()
        model, opt = load_float(args.upstream, checkpoints, with_emotion_model=True, nfe=10)
        results["weights_mb_with_emotion_model"] = round((torch.cuda.memory_allocated() - base) / 2**20)
        del model
        torch.cuda.empty_cache()
        for name in [m for m in sys.modules if m == "models" or m.startswith("models.") or m.startswith("options")]:
            del sys.modules[name]
        base = torch.cuda.memory_allocated()
        model, opt = load_float(args.upstream, checkpoints, with_emotion_model=False, nfe=10)
        results["weights_mb_without_emotion_model"] = round((torch.cuda.memory_allocated() - base) / 2**20)
        torch.cuda.reset_peak_memory_stats()

        portrait = encode_portrait(model, load_portrait(args.image))
        configs = {
            f"R{r}_H{h}_{norm}": StreamConfig(lookahead_frames=r, first_hop=8, min_hop=h, context_frames=50, norm=norm)
            for r in (3, 5, 8) for h in (10, 20, 40) for norm in ("buffer", "running")
        }
        all_pass_ms: list[float] = []
        features_ms: list[float] = []
        fmt_ms: list[float] = []
        for index, path in enumerate(args.audio):
            audio = load_audio(path)
            reference = whole_clip_latents(model, opt, portrait, audio, args.seed)
            other_seed = whole_clip_latents(model, opt, portrait, audio, args.seed + 1000)
            clip = {
                "seconds": round(len(audio) / SAMPLE_RATE, 2),
                "noise_floor": round(latent_distance(other_seed, reference), 4),
                "streamed": {},
            }
            for key, cfg in configs.items():
                streamed, passes = streamed_latents(model, opt, portrait, audio, cfg, args.seed)
                all_pass_ms += [p.features_ms + p.fmt_ms for p in passes[1:]]  # pass 0 includes warm-up
                features_ms += [p.features_ms for p in passes[1:]]
                fmt_ms += [p.fmt_ms for p in passes[1:]]
                clip["streamed"][key] = {
                    "distance": round(latent_distance(streamed, reference), 4),
                    "passes": len(passes),
                }
            if index < args.videos:
                best = min(clip["streamed"], key=lambda k: clip["streamed"][k]["distance"])
                streamed, _ = streamed_latents(model, opt, portrait, audio, configs[best], args.seed)
                side = torch.cat([decode(model, portrait, reference, 8, False),
                                  decode(model, portrait, streamed, 8, False)], dim=3)
                clip["video"] = str(write_video(side, path, args.out / f"{path.stem}-reference-vs-{best}.mp4"))
            results["clips"][path.name] = clip

        # Timing: one pass per nfe, decode per micro-batch.
        audio = load_audio(args.audio[0])
        timing: dict = {"pass_ms_p50_nfe10": round(percentile(all_pass_ms, 0.5), 2),
                        "pass_ms_p95_nfe10": round(percentile(all_pass_ms, 0.95), 2),
                        "features_ms_p50": round(percentile(features_ms, 0.5), 2),
                        "fmt_ms_p50_nfe10": round(percentile(fmt_ms, 0.5), 2)}
        for nfe in (7, 5):
            opt.nfe = nfe
            _, passes = streamed_latents(model, opt, portrait, audio, configs["R5_H20_buffer"], args.seed)
            ms = [p.features_ms + p.fmt_ms for p in passes[1:]]
            timing[f"pass_ms_p50_nfe{nfe}"] = round(percentile(ms, 0.5), 2)
        opt.nfe = 10
        reference = whole_clip_latents(model, opt, portrait, audio, args.seed)
        for fp16 in (False, True):
            for batch in (1, 4, 8, 16):
                timing[f"decode_ms_per_frame_b{batch}_{'fp16' if fp16 else 'fp32'}"] = round(
                    time_decode(model, portrait, reference, batch, fp16), 2)
        fp32 = decode(model, portrait, reference[:, :16], 8, False)
        fp16 = decode(model, portrait, reference[:, :16], 8, True)
        mse = float(((fp32 - fp16) / 2).pow(2).mean())
        timing["fp16_vs_fp32_psnr_db"] = round(10 * math.log10(1 / max(mse, 1e-12)), 1)
        results["timing"] = timing
        results["vram_peak_mb_whole_run"] = round(torch.cuda.max_memory_allocated() / 2**20)

        # VRAM of the streaming path alone: one streamed clip, decoded in micro-batches of 8.
        del reference, fp32, fp16
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        streamed, _ = streamed_latents(model, opt, portrait, audio, configs["R5_H20_buffer"], args.seed)
        for start in range(0, streamed.shape[1], 8):
            decode(model, portrait, streamed[:, start:start + 8], 8, False)
        results["vram_peak_mb_streaming"] = round(torch.cuda.max_memory_allocated() / 2**20)
        results["vram_reserved_mb_streaming"] = round(torch.cuda.max_memory_reserved() / 2**20)

        # First frame: when frames for the first H1 frames could be ready, against the browser start.
        h1, r = 8, 5
        first_pass_ms = percentile(all_pass_ms, 0.95)
        first_decode_ms = timing["decode_ms_per_frame_b8_fp16"] * 8
        results["first_frame"] = {}
        for rtf in (0.25, 0.5, 0.8):  # TTS seconds of work per second of audio
            audio_ready_s = (h1 + r) / FPS * rtf
            frame_ready_s = audio_ready_s + (first_pass_ms + first_decode_ms) / 1000
            playback_start_s = START_BUFFER_S * rtf
            results["first_frame"][f"tts_rtf_{rtf}"] = {
                "first_frame_ready_ms": round(frame_ready_s * 1000),
                "browser_start_ms": round(playback_start_s * 1000),
                "extra_hold_ms": round(max(0.0, frame_ready_s - playback_start_s) * 1000),
            }

    out = args.out / "portrait-spike-results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    print(f"\nwritten {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
