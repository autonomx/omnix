"""Measure the installed FasterQwen audiobook baseline on the local GPU.

This records the provider's current ordered fallback, not a native GPU batch.
Run from the repository root with its CUDA-enabled Python environment.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import sys
import time
import wave
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.providers.faster_qwen3_tts_provider import FasterQwen3TTSProvider  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--voice", default="default_ref")
    parser.add_argument("--other-voice", default="Anaka")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--shape", help="Run only one named workload shape")
    args = parser.parse_args()
    if not torch.cuda.is_available():
        raise SystemExit("CUDA is unavailable")
    model_dir = args.model_dir.resolve(strict=True)
    if not (model_dir / "model.safetensors").is_file():
        raise SystemExit("model weights are missing")
    provider = FasterQwen3TTSProvider({"model_dir": str(model_dir), "device": "cuda"})
    cases = [
        ("warmup", [("The room was quiet.", args.voice)]),
        ("short_dialogue", [
            ("Are you coming with us?", args.voice),
            ("Yes. I will be there soon.", args.voice),
        ]),
        ("long_narration", [
            ("The afternoon light crossed the library floor. Beyond the window, "
             "the garden moved slowly in the wind, and every page seemed to hold "
             "another small discovery waiting to be read aloud.", args.voice),
            ("At the end of the road, the travelers found an old stone bridge. "
             "They stopped to listen to the river before continuing toward the town.",
             args.voice),
        ]),
        ("mixed_length_speaker", [
            ("Wait!", args.other_voice),
            ("The narrator paused, then explained why the letter had remained "
             "unopened for so many years, even after everyone had forgotten its sender.",
             args.voice),
            ("I understand.", args.other_voice),
        ]),
        ("consistency_repeat", [
            ("The room was quiet.", args.voice),
            ("The room was quiet.", args.voice),
        ]),
    ]
    if args.shape:
        cases = [case for case in cases if case[0] == args.shape]
        if not cases:
            raise SystemExit(f"unknown workload shape: {args.shape}")
    results = []
    for name, prompts in cases:
        torch.cuda.reset_peak_memory_stats()
        free_before, total = torch.cuda.mem_get_info()
        requests = [{"text": text, "speaker": speaker, "language": "en",
                     "parameters": {"max_new_tokens": 512,
                                    "do_sample": name != "consistency_repeat"}}
                    for text, speaker in prompts]
        start = time.perf_counter()
        responses = provider.generate_audio_batch(requests)
        seconds = time.perf_counter() - start
        items = []
        for (text, speaker), response in zip(prompts, responses, strict=True):
            item = {"text_chars": len(text), "speaker": speaker,
                    "success": bool(response.get("success")) and not response.get("is_fallback")}
            if item["success"]:
                audio = base64.b64decode(response["audio"], validate=True)
                with wave.open(io.BytesIO(audio), "rb") as wav:
                    item["duration_seconds"] = round(wav.getnframes() / wav.getframerate(), 3)
                    item["sample_rate"] = wav.getframerate()
                item["sha256"] = hashlib.sha256(audio).hexdigest()
            else:
                item["error"] = str(response.get("error") or "unknown")
            items.append(item)
        duration = sum(item.get("duration_seconds", 0) for item in items)
        hashes = [item.get("sha256") for item in items]
        results.append({"shape": name, "items_per_call": len(requests),
                        "audio_consistent": len(set(hashes)) == 1 if name == "consistency_repeat" else None,
                        "elapsed_seconds": round(seconds, 3),
                        "audio_seconds": round(duration, 3),
                        "wall_seconds_per_audio_second": round(seconds / duration, 3) if duration else None,
                        "free_vram_before_gb": round(free_before / 1e9, 3),
                        "total_vram_gb": round(total / 1e9, 3),
                        "peak_allocated_gb": round(torch.cuda.max_memory_allocated() / 1e9, 3),
                        "failure_count": sum(not item["success"] for item in items),
                        "items": items})
    report = {"device": torch.cuda.get_device_name(0), "torch": torch.__version__,
              "model_dir": str(model_dir), "batch_contract": "ordered sequential fallback",
              "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "results": [
        {key: row[key] for key in ("shape", "items_per_call", "elapsed_seconds",
                                  "audio_seconds", "wall_seconds_per_audio_second",
                                  "peak_allocated_gb", "failure_count")}
        for row in results]}, indent=2))


if __name__ == "__main__":
    main()
