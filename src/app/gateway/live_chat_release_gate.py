"""Content-free target-runtime release evidence for Live Chat phases 1-8."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field

GateStatus = Literal["pass", "fail", "insufficient"]
MetricKind = Literal["latency", "rate", "score"]

REQUIRED_LIVE_CHAT_SCENARIOS = (
    "headphones-quiet",
    "speakers-quiet",
    "speakers-background-noise",
    "near-microphone",
    "distant-microphone",
    "normal-user-turn",
    "immediate-hard-stop",
    "correction-during-playback",
    "question-during-playback",
    "user-continuer",
    "laughter-nonspeech",
    "pure-assistant-echo",
    "speech-during-greeting",
    "speech-during-proactive-prompt",
    "long-thoughtful-pause",
    "explicit-thinking-suppression",
    "accepted-proactive-follow-up",
    "ignored-proactive-follow-up",
    "listener-backchannel",
    "sensitive-dictation",
    "provider-reconnect",
    "stt-failure",
    "tts-failure",
    "browser-reload-partial-delivery",
    "rapid-interruption-soak",
    "sustained-20-minute-conversation",
)


class LiveChatEvidenceMetadata(BaseModel):
    """Runtime identity without transcript, prompt, memory, or audio content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    exact_commit_sha: str = Field(min_length=7, max_length=64)
    browser_version: str = Field(min_length=1, max_length=160)
    os_version: str = Field(min_length=1, max_length=160)
    input_device_hash: str = Field(min_length=8, max_length=128)
    output_device_hash: str = Field(min_length=8, max_length=128)
    character_id: str = Field(default="system-assistant", min_length=1, max_length=160)
    profile_version: int = Field(default=1, ge=1)
    presence_preset: str = Field(default="natural", min_length=1, max_length=40)
    configured_duplex_mode: str = Field(default="automatic", min_length=1, max_length=40)
    resolved_duplex_mode: str = Field(default="half_duplex", min_length=1, max_length=40)
    calibration_version: str | None = Field(default=None, max_length=80)


class LiveChatEvidenceEvent(BaseModel):
    """One bounded content-free observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    timestamp_utc: str | None = None
    trace_id: str = Field(default="live-chat-unscoped", min_length=1, max_length=160)
    scenario: str = Field(min_length=1, max_length=160)
    metric_name: str = Field(min_length=1, max_length=120)
    value: float


class LiveChatMetricPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: MetricKind
    limit: float
    comparison: Literal["maximum", "minimum"] = "maximum"
    minimum_samples: int = Field(default=10, ge=1, le=100_000)


DEFAULT_LIVE_CHAT_METRIC_POLICIES: dict[str, LiveChatMetricPolicy] = {
    "natural_eos_rate": LiveChatMetricPolicy(kind="rate", limit=0.90, comparison="minimum"),
    "forced_eos_rate": LiveChatMetricPolicy(kind="rate", limit=0.05),
    "token_limit_rate": LiveChatMetricPolicy(kind="rate", limit=0.01),
    "false_barge_in_rate": LiveChatMetricPolicy(kind="rate", limit=0.05),
    "missed_barge_in_rate": LiveChatMetricPolicy(kind="rate", limit=0.10),
    "playback_echo_submission_rate": LiveChatMetricPolicy(kind="rate", limit=0.0),
    "duck_to_cancel_ms": LiveChatMetricPolicy(kind="latency", limit=500.0, minimum_samples=5),
    "rejected_candidate_restore_ms": LiveChatMetricPolicy(kind="latency", limit=500.0, minimum_samples=5),
    "proactive_prompt_acceptance_rate": LiveChatMetricPolicy(kind="rate", limit=0.50, comparison="minimum"),
    "proactive_prompt_regret_rate": LiveChatMetricPolicy(kind="rate", limit=0.10),
    "listener_backchannel_collision_rate": LiveChatMetricPolicy(kind="rate", limit=0.05),
    "conversation_repair_success_rate": LiveChatMetricPolicy(kind="rate", limit=0.90, comparison="minimum"),
    "repeated_proactive_topic_rate": LiveChatMetricPolicy(kind="rate", limit=0.05),
    "unanswered_obligation_rate": LiveChatMetricPolicy(kind="rate", limit=0.10),
    "perceived_listening_score": LiveChatMetricPolicy(kind="score", limit=3.5, comparison="minimum", minimum_samples=5),
    "perceived_pressure_score": LiveChatMetricPolicy(kind="score", limit=2.5, comparison="maximum", minimum_samples=5),
}


class LiveChatReleaseThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    required_scenarios: tuple[str, ...] = REQUIRED_LIVE_CHAT_SCENARIOS
    metric_policies: dict[str, LiveChatMetricPolicy] = Field(
        default_factory=lambda: dict(DEFAULT_LIVE_CHAT_METRIC_POLICIES)
    )
    require_system_and_character: bool = True


class LiveChatMetricResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    kind: MetricKind
    status: GateStatus
    samples: int
    observed: float | None
    limit: float
    comparison: Literal["maximum", "minimum"]


class LiveChatReleaseGateReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: GateStatus
    generated_at: str
    metadata: LiveChatEvidenceMetadata
    records_scanned: int
    traces: int
    scenarios: list[str]
    missing_scenarios: list[str]
    character_modes: list[str]
    metrics: list[LiveChatMetricResult]
    failures: list[str]
    insufficient: list[str]


class LiveChatReleaseGateEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: LiveChatEvidenceMetadata
    events: list[LiveChatEvidenceEvent] = Field(min_length=1, max_length=100_000)
    thresholds: LiveChatReleaseThresholds = Field(default_factory=LiveChatReleaseThresholds)


def evaluate_live_chat_release_gate(
    metadata: LiveChatEvidenceMetadata,
    events: Iterable[LiveChatEvidenceEvent | dict[str, Any]],
    *,
    thresholds: LiveChatReleaseThresholds | None = None,
) -> LiveChatReleaseGateReport:
    limits = thresholds or LiveChatReleaseThresholds()
    values: dict[str, list[float]] = defaultdict(list)
    traces: set[str] = set()
    scenarios: set[str] = set()
    character_modes: set[str] = set()
    scanned = 0

    for raw in events:
        try:
            event = raw if isinstance(raw, LiveChatEvidenceEvent) else LiveChatEvidenceEvent.model_validate(raw)
        except Exception:
            continue
        if not math.isfinite(event.value):
            continue
        scanned += 1
        traces.add(event.trace_id)
        scenarios.add(event.scenario)
        character_modes.add("system" if metadata.character_id == "system-assistant" else "character")
        if event.metric_name in limits.metric_policies:
            values[event.metric_name].append(float(event.value))

    failures: list[str] = []
    insufficient: list[str] = []
    missing_scenarios = sorted(set(limits.required_scenarios) - scenarios)
    if missing_scenarios:
        insufficient.append("missing scenarios: " + ", ".join(missing_scenarios))

    if limits.require_system_and_character and character_modes != {"system", "character"}:
        # A single request represents one runtime identity. Combined evidence can disable
        # this check, while production aggregation must provide both identity classes.
        insufficient.append("system and character evidence must be aggregated")

    results: list[LiveChatMetricResult] = []
    for name, policy in limits.metric_policies.items():
        samples = values[name]
        observed = _observed(policy.kind, samples) if samples else None
        if len(samples) < policy.minimum_samples:
            status: GateStatus = "insufficient"
            insufficient.append(f"{name}: {len(samples)}/{policy.minimum_samples} samples")
        else:
            passed = observed is not None and (
                observed <= policy.limit if policy.comparison == "maximum" else observed >= policy.limit
            )
            status = "pass" if passed else "fail"
            if status == "fail":
                failures.append(
                    f"{name} {observed:.3f} violates {policy.comparison} {policy.limit:.3f}"
                )
        results.append(LiveChatMetricResult(
            name=name,
            kind=policy.kind,
            status=status,
            samples=len(samples),
            observed=observed,
            limit=policy.limit,
            comparison=policy.comparison,
        ))

    overall: GateStatus = "fail" if failures else "insufficient" if insufficient else "pass"
    return LiveChatReleaseGateReport(
        status=overall,
        generated_at=datetime.now(timezone.utc).isoformat(),
        metadata=metadata,
        records_scanned=scanned,
        traces=len(traces),
        scenarios=sorted(scenarios),
        missing_scenarios=missing_scenarios,
        character_modes=sorted(character_modes),
        metrics=results,
        failures=failures,
        insufficient=insufficient,
    )


def _observed(kind: MetricKind, values: list[float]) -> float:
    if kind == "latency":
        ordered = sorted(values)
        return ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1))]
    return sum(values) / len(values)
