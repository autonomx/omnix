"""Live portrait Phase 0: lip-sync scores (SyncNet LSE-D / LSE-C) for streamed vs whole-clip FLOAT.

Renders each variant of each clip to a video with its audio, then scores it with joonson/syncnet_python's
standard pipeline (S3FD face tracks cropped to 224 px, then SyncNet). Lower LSE-D and higher LSE-C are better.
A mismatched control (one clip's video with another clip's audio) shows what "out of sync" scores look like.

Uses the helpers in scripts/portrait_spike.py and the same busy-machine guard.

    venv/Scripts/python.exe scripts/portrait_lipsync.py --upstream <float clone> --syncnet <syncnet clone> \
        --image <512 portrait> --audio a.wav b.wav --out <dir>
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import portrait_spike as spike  # noqa: E402

# (name, method, nfe, stream config key)
VARIANTS = (
    ("whole_nfe10", "whole", 10, None),
    ("whole_nfe7", "whole", 7, None),
    ("stream_R5_H20_nfe10", "stream", 10, (5, 20)),
    ("stream_R8_H20_nfe10", "stream", 10, (8, 20)),
    ("stream_R5_H20_nfe7", "stream", 7, (5, 20)),
    ("stream_R5_H20_nfe5", "stream", 5, (5, 20)),
)


_SYNCNET = {}


def syncnet(syncnet_dir: Path):
    if "model" not in _SYNCNET:
        sys.path.insert(0, str(syncnet_dir))
        from SyncNetInstance import SyncNetInstance

        model = SyncNetInstance()
        model.loadParameters(str(syncnet_dir / "data" / "syncnet_v2.model"))
        _SYNCNET["model"] = model
    return _SYNCNET["model"]


def score(syncnet_dir: Path, video: Path, work: Path, reference: str) -> dict:
    """LSE-D and LSE-C over every face track SyncNet's pipeline finds in ``video``."""
    import glob

    import numpy as np

    subprocess.run([sys.executable, "run_pipeline.py", "--videofile", str(video), "--reference", reference,
                    "--data_dir", str(work), "--overwrite", "--min_track", "50"],
                   cwd=syncnet_dir, check=True, capture_output=True)
    opt = argparse.Namespace(tmp_dir=str(work / "pytmp"), reference=reference, batch_size=20, vshift=15)
    dists, confs, offsets = [], [], []
    for track in sorted(glob.glob(str(work / "pycrop" / reference / "*.avi"))):
        offset, conf, framewise = syncnet(syncnet_dir).evaluate(opt, videofile=track)
        dists.append(float(framewise.mean(axis=0).min()))  # LSE-D: mean distance at the best shift
        confs.append(float(conf))
        offsets.append(int(offset))
    if not dists:
        return {"tracks": 0}
    return {"tracks": len(dists), "lse_d": round(float(np.mean(dists)), 3),
            "lse_c": round(float(np.mean(confs)), 3), "offset_frames": offsets}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--syncnet", type=Path, required=True, help="clone of joonson/syncnet_python with weights")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--audio", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=25)
    parser.add_argument("--allow-busy", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("OMNIX_FFMPEG", "ffmpeg")

    import torch

    reasons = spike.busy_reasons(args.allow_busy)
    if reasons:
        print("Not starting; the machine looks busy:\n  " + "\n  ".join(reasons))
        return 2
    spike.lower_priority()

    videos: dict[str, dict[str, Path]] = {}
    with torch.no_grad():
        model, opt = spike.load_float(args.upstream, args.upstream / "checkpoints", with_emotion_model=False, nfe=10)
        portrait = spike.encode_portrait(model, spike.load_portrait(args.image))
        for path in args.audio:
            audio = spike.load_audio(path)
            videos[path.name] = {}
            for name, method, nfe, stream in VARIANTS:
                opt.nfe = nfe
                if method == "whole":
                    latents = spike.whole_clip_latents(model, opt, portrait, audio, args.seed)
                else:
                    cfg = spike.StreamConfig(lookahead_frames=stream[0], first_hop=8, min_hop=stream[1],
                                             context_frames=50, norm="buffer")
                    latents, _ = spike.streamed_latents(model, opt, portrait, audio, cfg, args.seed)
                frames = spike.decode(model, portrait, latents, 8, False)
                videos[path.name][name] = spike.write_video(frames, path, args.out / f"{path.stem}-{name}.mp4")
        del model
        torch.cuda.empty_cache()

    # Mismatched control: each clip's whole-clip video with the next clip's audio.
    names = list(videos)
    for index, clip in enumerate(names):
        other = args.audio[(index + 1) % len(args.audio)]
        silent = args.out / f"{Path(clip).stem}-control.silent.mp4"
        subprocess.run([os.environ["OMNIX_FFMPEG"], "-y", "-loglevel", "error", "-i", str(videos[clip]["whole_nfe10"]),
                        "-an", "-c:v", "copy", str(silent)], check=True)
        control = args.out / f"{Path(clip).stem}-control_mismatched_audio.mp4"
        subprocess.run([os.environ["OMNIX_FFMPEG"], "-y", "-loglevel", "error", "-i", str(silent), "-i", str(other),
                        "-c:v", "copy", "-c:a", "aac", "-shortest", str(control)], check=True)
        silent.unlink()
        videos[clip]["control_mismatched_audio"] = control

    results: dict = {"clips": {}, "mean": {}}
    work = args.out / "syncnet-work"
    for clip, variants in videos.items():
        results["clips"][clip] = {}
        for name, video in variants.items():
            reference = f"{Path(clip).stem}-{name}".replace(" ", "_")
            results["clips"][clip][name] = score(args.syncnet.resolve(), video.resolve(), work.resolve(), reference)
            print(clip, name, results["clips"][clip][name], flush=True)
    for name in [v[0] for v in VARIANTS] + ["control_mismatched_audio"]:
        rows = [c[name] for c in results["clips"].values() if c.get(name, {}).get("tracks")]
        if rows:
            results["mean"][name] = {"lse_d": round(sum(r["lse_d"] for r in rows) / len(rows), 3),
                                     "lse_c": round(sum(r["lse_c"] for r in rows) / len(rows), 3),
                                     "clips": len(rows)}
    out = args.out / "portrait-lipsync-results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results["mean"], indent=2))
    print(f"\nwritten {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
