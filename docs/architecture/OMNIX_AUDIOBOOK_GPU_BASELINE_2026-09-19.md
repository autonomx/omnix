# Omnix audiobook TTS GPU baseline — 2026-09-19

Measured with `venv/Scripts/python.exe scripts/benchmark_audiobook_tts.py` on the
local NVIDIA GeForce RTX 4090, PyTorch 2.5.1+cu124, FasterQwen3 TTS, and the
local `Qwen3-TTS-12Hz-0.6B-Base` weights. The `model.safetensors` SHA-256 was
`180b3b10eb1c9f1b4db7806d5475bae3071c0243c299d49926bab1da3b6946f6`.
Each request used `max_new_tokens=512`; voices were existing local reference
clips. The output passed PCM WAV decoding. Flash Attention and SoX were absent
in this environment; inference still completed.

| Workload | Items per call | Wall time | Audio time | Wall/audio | Peak allocated VRAM | Failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Cold warmup, short passage | 1 | 21.78 s | 1.76 s | 12.37 | 2.38 GB | 0 |
| Short homogeneous dialogue | 2 | 6.44 s | 4.64 s | 1.39 | 2.31 GB | 0 |
| Long narrator passages | 2 | 24.87 s | 18.72 s | 1.33 | 2.54 GB | 0 |
| Mixed length, mixed speaker | 3 | 14.18 s | 10.24 s | 1.39 | 2.46 GB | 0 |

Free VRAM before each shape ranged from 21.38 to 24.16 GB. Two identical
short passages with `do_sample=False` each produced 6.4 seconds of audio and
the same WAV SHA-256 in one process. This checks repeatability for that prompt
and setting only; sampled generation was not tested for reproducibility.

The installed `generate_audio_batch` implementation calls `generate_audio`
once per request in order. These items per call are **not** a native GPU batch,
and the measurements show no batch speedup. Keep the audiobook scheduler at
one synthesized span per checkpoint until the underlying FasterQwen runtime
exposes and passes a true multi-input path. The current model method accepts
one text and one reference audio per call. A larger job-side list would only
delay preview and realtime work without improving GPU throughput.

`model_revision` remains a provenance limitation: the audiobook API currently
accepts a caller supplied revision string. The FasterQwen provider does not
apply a generation seed, so audiobook render and preview requests now reject
non-null seeds rather than recording an ineffective value. Resolve both
contracts before claiming reproducible sampled renders or using a caller
supplied string as proof of the installed model weights.
