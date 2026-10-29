"""Live portrait Phase 1 check: the service's runtime and scheduler on the GPU, against the Phase 0 spike.

Feeds each clip through ``services.portrait`` (PortraitStream + FloatSession) one video frame of audio at a
time, so its passes fall where the spike's did, and writes the frames the service sends as a video (for
``portrait_lipsync.py --videos``). For the first clip it compares the committed motion latents with the
spike's optimized path on the same portrait. It also times loading, the passes, and cropping an uncropped
photo with S3FD. Refuses to start while the machine is busy (as the spike does).

    <spike venv>/Scripts/python.exe scripts/portrait_runtime_check.py --upstream <float clone> \
        --image <512 portrait> --photo <uncropped photo> --audio a.wav b.wav --out <dir>
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import portrait_spike as spike  # noqa: E402


def stream_clip(runtime, portrait, path: Path, *, float_pcm: bool):
    """Stream one clip through the service's scheduler; returns its JPEGs, committed latents and pass times."""
    import numpy as np
    import torch

    from services.portrait.scheduler import SAMPLES_PER_FRAME, PortraitStream

    session = runtime.session(portrait)
    pass_ms: list[float] = []
    run_pass = session.run_pass

    def timed_pass(audio, plan, seed):
        torch.cuda.synchronize()
        begin = time.perf_counter()
        run_pass(audio, plan, seed)
        torch.cuda.synchronize()
        pass_ms.append((time.perf_counter() - begin) * 1000)

    session.run_pass = timed_pass  # type: ignore[method-assign]
    jpegs: list[bytes] = []
    frozen = time.monotonic()
    stream = PortraitStream(session, lambda frame: jpegs.append(frame.jpeg), clock=lambda: frozen)
    audio = spike.load_audio(path)
    # The TTS stream sends 16-bit PCM; float input isolates the scheduler and runtime from that quantization.
    pcm = audio if float_pcm else np.clip(audio * 32767, -32768, 32767).astype(np.int16)
    stream.phrase_start(path.stem, 1, "seg", 16_000)
    for offset in range(0, len(pcm), SAMPLES_PER_FRAME):
        stream.pcm("seg", offset, pcm[offset:offset + SAMPLES_PER_FRAME])
        stream.pump()
    before_end = session.latents.shape[0]
    stream.phrase_done("seg")
    stream.output_end(path.stem, 1)
    stream.pump()
    return jpegs, session.latents[:before_end].detach().cpu(), pass_ms, audio, session


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--upstream", type=Path, required=True, help="the spike's upstream clone (for its comparison)")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--photo", type=Path, required=True)
    parser.add_argument("--audio", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--allow-busy", action="store_true")
    parser.add_argument("--float-pcm", action="store_true", help="send float samples instead of 16-bit PCM")
    parser.add_argument("--buffer-frames", type=int, default=100, help="wav2vec2's fixed input length (0: none)")
    parser.add_argument("--no-spike", action="store_true", help="skip the comparison with the spike")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    import numpy as np
    import torch

    reasons = spike.busy_reasons(args.allow_busy)
    if reasons:
        print("Not starting; the machine looks busy:\n  " + "\n  ".join(reasons))
        return 2
    spike.lower_priority()

    from PIL import Image

    from services.portrait.float_runtime import FloatRuntime, required_folders
    from services.portrait.portrait_image import portrait_pixels

    results: dict = {"pcm": "float32" if args.float_pcm else "int16", "clips": {}}
    started = time.perf_counter()
    runtime = FloatRuntime(required_folders(), nfe=7, buffer_frames=args.buffer_frames)
    results["buffer_frames"] = args.buffer_frames
    results["load_s"] = round(time.perf_counter() - started, 2)

    started = time.perf_counter()
    runtime.prepare("photo", args.photo.read_bytes())
    results["prepare_photo_ms"] = round((time.perf_counter() - started) * 1000)
    Image.fromarray(portrait_pixels(args.photo.read_bytes(), runtime.detect)).save(args.out / "photo-crop.png")

    pixels = np.asarray(Image.open(args.image).convert("RGB").resize((512, 512), Image.LANCZOS))
    started = time.perf_counter()
    portrait = runtime.encode("check", pixels)
    results["encode_ms"] = round((time.perf_counter() - started) * 1000)
    all_pass_ms: list[float] = []
    first_latents = first_audio = None
    for index, path in enumerate(args.audio):
        jpegs, latents, pass_ms, audio, session = stream_clip(runtime, portrait, path, float_pcm=args.float_pcm)
        # The same frames before JPEG, to tell the encoding's effect apart from the motion's.
        raw = runtime.render_pixels(portrait, session.latents).float() / 127.5 - 1.0
        spike.write_video(raw.cpu(), path, args.out / f"{path.stem}-raw.mp4")
        sent = torch.stack([torch.from_numpy(np.asarray(Image.open(io.BytesIO(jpeg)).convert("RGB"))).permute(2, 0, 1)
                            for jpeg in jpegs]).float() / 127.5 - 1.0
        mse = ((sent - raw.cpu()[: len(jpegs)]) / 2).pow(2).flatten(1).mean(dim=1).clamp_min(1e-12)
        jpeg_psnr = (10 * torch.log10(1 / mse))
        jpeg_min_psnr = round(float(jpeg_psnr.min()), 1)
        all_pass_ms += pass_ms
        frames = [torch.from_numpy(np.asarray(Image.open(io.BytesIO(jpeg)).convert("RGB"))).permute(2, 0, 1)
                  for jpeg in jpegs]
        video = spike.write_video(torch.stack(frames).float() / 127.5 - 1.0, path, args.out / f"{path.stem}-service.mp4")
        results["clips"][path.name] = {"frames_sent": len(jpegs), "first_pass_ms": round(pass_ms[0], 1),
                                       "jpeg_min_psnr_db": jpeg_min_psnr, "video": str(video)}
        if jpeg_min_psnr < 30:
            print(f"FAIL {path.name}: a sent frame is {jpeg_min_psnr} dB from its decoded frame (corrupt JPEG)")
        if index == 0:
            first_latents, first_audio = latents, audio
    results["pass_ms_p50"] = round(spike.percentile(all_pass_ms, 0.5), 2)
    results["pass_ms_p95"] = round(spike.percentile(all_pass_ms, 0.95), 2)
    results["pass_ms_max"] = round(max(all_pass_ms), 2)
    results["passes"] = len(all_pass_ms)

    out = args.out / "portrait-runtime-check.json"
    if args.no_spike:
        out.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results, indent=2))
        return 0

    # The spike's optimized path on the same portrait and the first clip.
    with torch.no_grad():
        model, opt = spike.load_float(args.upstream, args.upstream / "checkpoints", with_emotion_model=False, nfe=7)
        spike.install_flow_grid_cache()
        spike_portrait = spike.encode_portrait(model, spike.load_portrait(args.image))
        spike.GRAPHED[7] = spike.GraphedWindowSolver(model, opt, spike_portrait, 7)
        cfg = spike.StreamConfig(lookahead_frames=5, first_hop=8, min_hop=20, context_frames=50, norm="buffer")
        spike_latents, _ = spike.streamed_latents(model, opt, spike_portrait, first_audio, cfg, 25)
    compared = spike_latents[0, :first_latents.shape[0]].cpu()
    results["first_clip_latent_relative_diff_vs_spike"] = float(
        (first_latents - compared).norm(dim=-1).mean() / compared.norm(dim=-1).mean())
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
