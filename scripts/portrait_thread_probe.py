"""Live portrait Phase 1: is cuDNN's one-off setup per thread? (A decode on the warmed thread, then on new ones.)

    <spike venv>/Scripts/python.exe scripts/portrait_thread_probe.py --image <512 portrait>
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import portrait_spike as spike  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--allow-busy", action="store_true")
    args = parser.parse_args()

    import numpy as np
    import torch
    from PIL import Image

    reasons = spike.busy_reasons(args.allow_busy)
    if reasons:
        print("Not starting; the machine looks busy:\n  " + "\n  ".join(reasons))
        return 2
    from services.portrait.float_runtime import FloatRuntime, required_folders

    runtime = FloatRuntime(required_folders(), nfe=7)
    pixels = np.asarray(Image.open(args.image).convert("RGB").resize((512, 512)))
    portrait = runtime.encode("probe", pixels)
    latents = torch.zeros(4, runtime.opt.dim_w, device="cuda")

    def decode_ms() -> float:
        torch.cuda.synchronize()
        begin = time.perf_counter()
        runtime.render_pixels(portrait, latents)
        torch.cuda.synchronize()
        return round((time.perf_counter() - begin) * 1000, 1)

    results = {"warmed_thread": [decode_ms(), decode_ms()]}
    for name in ("new_thread_1", "new_thread_2"):
        timings: list[float] = []
        thread = threading.Thread(target=lambda out=timings: out.extend([decode_ms(), decode_ms()]))
        thread.start()
        thread.join()
        results[name] = timings
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
