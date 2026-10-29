"""Live portrait Phase 1: where the service's one-off and after-idle latency comes from.

1. One-off setup: the first decode at a new batch size, with cuDNN on and off, and steady decode cost each way.
2. After idle: a pass after the GPU has idled for a few seconds, back to back, and after a tiny "wake" kernel.

Refuses to start while the machine is busy (as the spike does).

    <spike venv>/Scripts/python.exe scripts/portrait_latency_probe.py --image <512 portrait> --out <dir>
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import portrait_spike as spike  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--idle-seconds", type=float, default=3.0)
    parser.add_argument("--allow-busy", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    import numpy as np
    import torch
    from PIL import Image

    reasons = spike.busy_reasons(args.allow_busy)
    if reasons:
        print("Not starting; the machine looks busy:\n  " + "\n  ".join(reasons))
        return 2
    spike.lower_priority()

    from services.portrait.float_runtime import FloatRuntime, required_folders
    from services.portrait.scheduler import PassPlan

    def timed(function) -> float:
        torch.cuda.synchronize()
        begin = time.perf_counter()
        function()
        torch.cuda.synchronize()
        return round((time.perf_counter() - begin) * 1000, 1)

    results: dict = {}
    begin = time.perf_counter()
    runtime = FloatRuntime(required_folders(), nfe=7)
    results["load_s"] = round(time.perf_counter() - begin, 1)
    pixels = np.asarray(Image.open(args.image).convert("RGB").resize((512, 512), Image.LANCZOS))
    portrait = runtime.encode("probe", pixels)
    dim = runtime.opt.dim_w

    # 1. A new decoder batch size: cuDNN on (as loaded), then cuDNN off for further new sizes.
    def decode(size: int) -> None:
        latents = torch.zeros(size, dim, device="cuda")
        feats = [item.expand(size, *item.shape[1:]) for item in portrait.s_r_feats]
        runtime.model.motion_autoencoder.dec(portrait.s_r + latents, alpha=None, feats=feats)

    results["cudnn_on"] = {"first_decode_b5_ms": timed(lambda: decode(5)),
                           "steady_decode_b4_ms": min(timed(lambda: decode(4)) for _ in range(5))}
    with torch.backends.cudnn.flags(enabled=False):
        results["cudnn_off"] = {"first_decode_b6_ms": timed(lambda: decode(6)),
                                "second_decode_b6_ms": timed(lambda: decode(6)),
                                "steady_decode_b4_ms": min(timed(lambda: decode(4)) for _ in range(5))}

    # 2. A pass after idle.
    session = runtime.session(portrait)
    audio = (np.sin(np.arange(16_000 * 3) / 9.0) * 0.3).astype(np.float32)
    plan = PassPlan(start=50, commit=20, buffer_start=0, buffer_end=75, carry_start=40, padded=False)
    session.latents = torch.zeros(50, dim, device="cuda")
    session.feats = torch.zeros(50, dim, device="cuda")

    def one_pass() -> None:
        session.run_pass(audio[: 75 * 640], plan, 25)

    warm = [timed(one_pass) for _ in range(5)]
    time.sleep(args.idle_seconds)
    after_idle = [timed(one_pass) for _ in range(3)]
    time.sleep(args.idle_seconds)
    wake = timed(lambda: torch.ones(1024, 1024, device="cuda").matmul(torch.ones(1024, 1024, device="cuda")))
    after_wake = [timed(one_pass) for _ in range(2)]
    time.sleep(args.idle_seconds)
    begin = time.perf_counter()
    while time.perf_counter() - begin < 0.15:  # 150 ms of busy GPU, as a phrase_start wake could give
        torch.ones(1024, 1024, device="cuda").matmul(torch.ones(1024, 1024, device="cuda"))
    torch.cuda.synchronize()
    after_busy_wake = [timed(one_pass) for _ in range(2)]
    results["passes_ms"] = {"warm": warm, f"after_{args.idle_seconds}s_idle": after_idle,
                            "tiny_wake_kernel": wake, "after_tiny_wake": after_wake,
                            "after_150ms_busy_wake": after_busy_wake}

    out = args.out / "portrait-latency-probe.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
