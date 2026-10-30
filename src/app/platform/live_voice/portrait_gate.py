"""The live portrait's paired release gate (docs/architecture/OMNIX_LIVE_PORTRAIT_ROADMAP.md, Phase 5).

The same scenarios run twice, with the portrait off and on; every release metric the browser records says which
(``portrait``). The gate compares the two runs:

- ``start_hold_ms`` p50 at most 150 ms on the on run (D-5; the 250 ms cap holds by design, p95 is reported);
- ``av_offset_ms`` (each drawn frame against what is heard) within ±40 ms at p95;
- every latency metric, ``first_audible_ms`` among them, has its on-run p50 within 10% of the off run's, and
  ``llm_tokens_per_second`` its p50 at least 90% of the off run's, each with a bootstrap 95% interval of the ratio;
- ``underrun_count`` per reply no higher on than off;
- at least ``minimum_replies`` replies per required scenario in each run.

The portrait's fallbacks and refusals are counted and reported. Nothing here is random at run time: the bootstrap
uses a fixed seed.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

GateStatus = Literal["pass", "fail", "insufficient"]

PAIRED_LATENCY_METRICS = (
    "stt_finalize_ms",
    "final_to_first_token_ms",
    "first_token_to_first_audio_ms",
    "final_to_first_playback_ms",
    "speech_end_to_first_playback_ms",
    "first_audible_ms",
    "interruption_to_silence_ms",
)
# The reply count per scenario: one first-audible measurement per reply.
REPLY_METRIC = "first_audible_ms"
PORTRAIT_SCENARIOS = (
    "character-normal",
    "hard-stop",
    "correction-overlap",
    "sustained-overlap",
    "tts-failure",
    "provider-reconnect",
    "browser-reload",
    "rapid-interruption-soak",
)
BOOTSTRAP_ROUNDS = 1_000
BOOTSTRAP_SEED = 20_261_030


class PortraitGateThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum_replies: int = Field(default=40, ge=1, le=100_000)
    required_scenarios: tuple[str, ...] = PORTRAIT_SCENARIOS
    start_hold_p50_ms: float = Field(default=150.0, gt=0)
    av_offset_p95_ms: float = Field(default=40.0, gt=0)
    latency_p50_ratio: float = Field(default=1.10, gt=1)
    tokens_p50_ratio: float = Field(default=0.90, gt=0, lt=1)


class PortraitGateCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    status: GateStatus
    detail: str
    off: float | None = None
    on: float | None = None
    interval: tuple[float, float] | None = None


class PortraitGateReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: GateStatus
    replies: dict[str, dict[str, int]] = Field(default_factory=dict)
    checks: list[PortraitGateCheck] = Field(default_factory=list)
    counters: dict[str, int] = Field(default_factory=dict)
    recorded: dict[str, float | None] = Field(default_factory=dict)


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * quantile) - 1))
    return ordered[index]


def _bootstrap_ratio(off: list[float], on: list[float]) -> tuple[float, float]:
    """A 95% interval of p50(on) / p50(off), resampling both runs."""
    rng = random.Random(BOOTSTRAP_SEED)
    ratios = []
    for _ in range(BOOTSTRAP_ROUNDS):
        off_p50 = _percentile([rng.choice(off) for _ in off], 0.5)
        on_p50 = _percentile([rng.choice(on) for _ in on], 0.5)
        if off_p50 > 0:
            ratios.append(on_p50 / off_p50)
    if not ratios:
        return (math.nan, math.nan)
    return (round(_percentile(ratios, 0.025), 4), round(_percentile(ratios, 0.975), 4))


def evaluate_portrait_pairing(events: Iterable[dict[str, Any]],
                              thresholds: PortraitGateThresholds | None = None) -> PortraitGateReport:
    limits = thresholds or PortraitGateThresholds()
    samples: dict[tuple[bool, str], list[float]] = defaultdict(list)
    replies: dict[bool, dict[str, int]] = {False: defaultdict(int), True: defaultdict(int)}
    counters: dict[str, int] = defaultdict(int)
    for event in events:
        kind = event.get("event")
        portrait = bool(event.get("portrait"))
        name = str(event.get("metric_name") or "")
        if kind == "release_metric" and isinstance(event.get("value_ms"), (int, float)):
            value = float(event["value_ms"])
            if math.isfinite(value):
                samples[(portrait, name)].append(value)
                if name == REPLY_METRIC:
                    replies[portrait][str(event.get("scenario") or "unlabeled")] += 1
        elif kind == "release_metric_batch" and isinstance(event.get("values"), list):
            samples[(portrait, name)].extend(float(value) for value in event["values"]
                                             if isinstance(value, (int, float)) and math.isfinite(value))
        elif kind == "release_counter" and event.get("counter_name"):
            counters[f"{event['counter_name']}{'' if portrait else ':off'}"] += 1

    checks: list[PortraitGateCheck] = []

    def add(name: str, status: GateStatus, detail: str, **values: Any) -> None:
        checks.append(PortraitGateCheck(name=name, status=status, detail=detail, **values))

    for scenario in limits.required_scenarios:
        for portrait, label in ((False, "off"), (True, "on")):
            count = replies[portrait].get(scenario, 0)
            if count < limits.minimum_replies:
                add(f"replies:{scenario}:{label}", "insufficient", f"{count}/{limits.minimum_replies} replies")

    holds = samples[(True, "start_hold_ms")]
    recorded: dict[str, float | None] = {"start_hold_p95_ms": _percentile(holds, 0.95) if holds else None}
    if holds:
        p50 = _percentile(holds, 0.5)
        add("start_hold_ms", "pass" if p50 <= limits.start_hold_p50_ms else "fail",
            f"p50 {p50:.1f} ms (limit {limits.start_hold_p50_ms:.0f})", on=p50)
    else:
        add("start_hold_ms", "insufficient", "no start holds recorded")

    offsets = [abs(value) for value in samples[(True, "av_offset_ms")]]
    if offsets:
        p95 = _percentile(offsets, 0.95)
        add("av_offset_ms", "pass" if p95 <= limits.av_offset_p95_ms else "fail",
            f"|offset| p95 {p95:.1f} ms over {len(offsets)} frames (limit {limits.av_offset_p95_ms:.0f})", on=p95)
    else:
        add("av_offset_ms", "insufficient", "no drawn frames measured")

    for name in (*PAIRED_LATENCY_METRICS, "llm_tokens_per_second"):
        off, on = samples[(False, name)], samples[(True, name)]
        if len(off) < 2 or len(on) < 2:
            add(name, "insufficient", f"{len(off)} off and {len(on)} on samples")
            continue
        off_p50, on_p50 = _percentile(off, 0.5), _percentile(on, 0.5)
        recorded[f"{name}:p95:off"], recorded[f"{name}:p95:on"] = _percentile(off, 0.95), _percentile(on, 0.95)
        interval = _bootstrap_ratio(off, on)
        if name == "llm_tokens_per_second":
            ok = on_p50 >= off_p50 * limits.tokens_p50_ratio
            detail = f"on p50 {on_p50:.1f}/s, off {off_p50:.1f}/s (at least {limits.tokens_p50_ratio:.0%})"
        else:
            ok = on_p50 <= off_p50 * limits.latency_p50_ratio
            detail = f"on p50 {on_p50:.1f} ms, off {off_p50:.1f} ms (at most {limits.latency_p50_ratio:.0%})"
        add(name, "pass" if ok else "fail", detail, off=off_p50, on=on_p50, interval=interval)

    off_runs, on_runs = samples[(False, "underrun_count")], samples[(True, "underrun_count")]
    if off_runs and on_runs:
        off_mean, on_mean = sum(off_runs) / len(off_runs), sum(on_runs) / len(on_runs)
        add("underrun_count", "pass" if on_mean <= off_mean else "fail",
            f"per reply: on {on_mean:.3f}, off {off_mean:.3f}", off=off_mean, on=on_mean)
    else:
        add("underrun_count", "insufficient", "no replies with playback in one of the runs")

    statuses = {check.status for check in checks}
    status: GateStatus = "fail" if "fail" in statuses else "insufficient" if "insufficient" in statuses else "pass"
    return PortraitGateReport(status=status, checks=checks, counters=dict(counters), recorded=recorded,
                              replies={"off": dict(replies[False]), "on": dict(replies[True])})


__all__ = ["PAIRED_LATENCY_METRICS", "PORTRAIT_SCENARIOS", "PortraitGateCheck", "PortraitGateReport",
           "PortraitGateThresholds", "evaluate_portrait_pairing"]
