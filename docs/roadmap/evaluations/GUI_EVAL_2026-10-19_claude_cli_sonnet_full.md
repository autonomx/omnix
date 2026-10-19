# Rich-reply evaluation: claude_cli:sonnet (full) — 2026-10-19

Gate: PASSED. 40 prompts × 5 samples = 200 samples (0 errors).

| Metric | Value | Gate |
|---|---|---|
| Valid-block rate | 0.990 (95/96); 95% Wilson [0.943, 0.998] | lower bound ≥ 0.93 |
| Precision (block usage) | 1.000 | ≥ 0.8 |
| Recall (block usage) | 1.000 | — |
| Leakage (fences on plain prompts) | 0.000 | ≤ 0.05 |
| Added instruction tokens | 428 | — |
| Latency mean / p95 | 5.83 s / 10.26 s | — |
| Output tokens (mean) | 440.23 | — |

Diagnostics by code: `unknown_type` 1.
