"""Scoring for the rich-reply evaluation (GUI-3.3).

The harness (``src/tests/evaluation/test_generative_ui_eval.py``) samples each
prompt several times per model; this module turns the samples into the gate
metrics. A model's ``rich_ui`` level is set only from a dated report whose
metrics pass the gate for that level.
"""
from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from .catalog import CATALOG
from .parser import scan_fences
from .prompting import BASIC_BLOCKS

PromptLabel = Literal["block", "markdown", "plain"]

# The gate (roadmap §8, GUI-3.3).
MIN_VALID_LOWER_BOUND = 0.93
MIN_PRECISION = 0.80
MAX_LEAKAGE = 0.05


@dataclass(frozen=True)
class EvalPrompt:
    id: str
    label: PromptLabel
    style: str
    prompt: str
    expected_blocks: tuple[str, ...] = ()
    context_items: tuple[dict[str, Any], ...] = ()

    @property
    def basic_eligible(self) -> bool:
        """In the basic subset: Markdown and plain prompts, and block prompts that stats or charts answer."""
        return self.label != "block" or set(self.expected_blocks) <= set(BASIC_BLOCKS)


@dataclass(frozen=True)
class EvalSample:
    prompt: EvalPrompt
    content: str
    ui: dict[str, Any] | None
    latency_seconds: float
    output_tokens: int | None = None
    error: str | None = None
    # The model the provider answered with; aliases such as "haiku" can move between versions.
    resolved_model: str | None = None


@dataclass
class EvalMetrics:
    samples: int
    errors: int
    fences: int
    valid_blocks: int
    valid_rate: float
    valid_lower_bound: float
    valid_upper_bound: float
    # Replies with at least one fence, and those where every fence rendered: a per-reply view,
    # since blocks in one reply are not independent trials.
    replies_with_blocks: int
    replies_all_valid: int
    precision: float
    recall: float
    leakage: float
    diagnostics: dict[str, int]
    latency_mean_seconds: float
    latency_p95_seconds: float
    output_tokens_mean: float | None
    instruction_tokens: int
    passed: bool
    resolved_models: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def wilson_interval(successes: int, trials: int, z: float = 1.959964) -> tuple[float, float]:
    """The 95% Wilson score interval for a proportion; (0, 0) without trials."""
    if trials <= 0:
        return 0.0, 0.0
    phat = successes / trials
    denominator = 1 + z * z / trials
    centre = (phat + z * z / (2 * trials)) / denominator
    margin = z * math.sqrt(phat * (1 - phat) / trials + z * z / (4 * trials * trials)) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def score_samples(samples: Iterable[EvalSample], *, instruction_tokens: int, level: str = "full") -> EvalMetrics:
    """Gate metrics over samples; for ``basic`` only the basic subset counts."""
    chosen = [sample for sample in samples if level != "basic" or sample.prompt.basic_eligible]
    answered = [sample for sample in chosen if sample.error is None]
    fences = 0
    valid = 0
    diagnostics: Counter[str] = Counter()
    used_block: list[bool] = []
    replies_all_valid = 0
    for sample in answered:
        count = len(scan_fences(sample.content))
        fences += count
        used_block.append(count > 0)
        rendered = len((sample.ui or {}).get("blocks") or {})
        if count and rendered == count:
            replies_all_valid += 1
        if sample.ui:
            valid += rendered
            diagnostics.update(str(item.get("code")) for item in sample.ui.get("diagnostics") or [] if isinstance(item, dict))
    labels = [sample.prompt.label for sample in answered]
    true_positive = sum(1 for used, label in zip(used_block, labels) if used and label == "block")
    predicted = sum(used_block)
    actual = sum(1 for label in labels if label == "block")
    plain = [used for used, label in zip(used_block, labels) if label == "plain"]
    lower, upper = wilson_interval(valid, fences)
    latencies = [sample.latency_seconds for sample in answered]
    tokens = [sample.output_tokens for sample in answered if sample.output_tokens is not None]
    metrics = EvalMetrics(
        samples=len(chosen),
        errors=len(chosen) - len(answered),
        fences=fences,
        valid_blocks=valid,
        valid_rate=valid / fences if fences else 0.0,
        valid_lower_bound=lower,
        valid_upper_bound=upper,
        replies_with_blocks=sum(used_block),
        replies_all_valid=replies_all_valid,
        precision=true_positive / predicted if predicted else 0.0,
        recall=true_positive / actual if actual else 0.0,
        leakage=sum(plain) / len(plain) if plain else 0.0,
        diagnostics=dict(sorted(diagnostics.items())),
        latency_mean_seconds=sum(latencies) / len(latencies) if latencies else 0.0,
        latency_p95_seconds=_percentile(latencies, 0.95),
        output_tokens_mean=sum(tokens) / len(tokens) if tokens else None,
        instruction_tokens=instruction_tokens,
        passed=False,
        resolved_models=sorted({sample.resolved_model for sample in answered if sample.resolved_model}),
    )
    if metrics.valid_lower_bound < MIN_VALID_LOWER_BOUND:
        metrics.failures.append(f"valid-block lower bound {metrics.valid_lower_bound:.3f} < {MIN_VALID_LOWER_BOUND}")
    if metrics.precision < MIN_PRECISION:
        metrics.failures.append(f"precision {metrics.precision:.3f} < {MIN_PRECISION}")
    if metrics.leakage > MAX_LEAKAGE:
        metrics.failures.append(f"leakage {metrics.leakage:.3f} > {MAX_LEAKAGE}")
    metrics.passed = not metrics.failures
    return metrics


def load_prompts(payload: dict[str, Any]) -> list[EvalPrompt]:
    """Prompts from the checked-in prompt set; unknown block types are rejected."""
    prompts: list[EvalPrompt] = []
    for item in payload["prompts"]:
        expected = tuple(item.get("expected_blocks") or ())
        unknown = set(expected) - set(CATALOG)
        if unknown:
            raise ValueError(f"{item['id']}: unknown block types {sorted(unknown)}")
        prompts.append(EvalPrompt(
            id=item["id"], label=item["label"], style=item["style"], prompt=item["prompt"],
            expected_blocks=expected, context_items=tuple(item.get("context_items") or ()),
        ))
    return prompts


def report_markdown(model: str, level: str, metrics: EvalMetrics, *, date: str, samples_per_prompt: int, prompts: int) -> str:
    """A dated report for docs/roadmap/; capability values are set only from such a report."""
    verdict = "PASSED" if metrics.passed else "FAILED"
    lines = [
        f"# Rich-reply evaluation: {model} ({level}) — {date}",
        "",
        f"Gate: {verdict}. {prompts} prompts × {samples_per_prompt} samples = {metrics.samples} samples ({metrics.errors} errors).",
        "",
        "| Metric | Value | Gate |",
        "|---|---|---|",
        f"| Valid-block rate | {metrics.valid_rate:.3f} ({metrics.valid_blocks}/{metrics.fences}); 95% Wilson [{metrics.valid_lower_bound:.3f}, {metrics.valid_upper_bound:.3f}] | lower bound ≥ {MIN_VALID_LOWER_BOUND} |",
        f"| Replies whose blocks all rendered | {metrics.replies_all_valid}/{metrics.replies_with_blocks} | — |",
        f"| Precision (block usage) | {metrics.precision:.3f} | ≥ {MIN_PRECISION} |",
        f"| Recall (block usage) | {metrics.recall:.3f} | — |",
        f"| Leakage (fences on plain prompts) | {metrics.leakage:.3f} | ≤ {MAX_LEAKAGE} |",
        f"| Added instruction tokens | {metrics.instruction_tokens} | — |",
        f"| Latency mean / p95 | {metrics.latency_mean_seconds:.2f} s / {metrics.latency_p95_seconds:.2f} s | — |",
        f"| Output tokens (mean) | {metrics.output_tokens_mean if metrics.output_tokens_mean is not None else 'n/a'} | — |",
        "",
        "Diagnostics by code: " + (", ".join(f"`{code}` {count}" for code, count in metrics.diagnostics.items()) or "none") + ".",
        "",
        "Resolved models: " + (", ".join(f"`{name}`" for name in metrics.resolved_models) or "not reported by the provider") + ".",
    ]
    if metrics.failures:
        lines.extend(["", "Gate failures:", *(f"- {failure}" for failure in metrics.failures)])
    return "\n".join(lines) + "\n"
