"""Fail-closed promotion gates for authoritative Kyutai live STT."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping


class KyutaiAuthorityMode(StrEnum):
    OBSERVATIONAL = "observational"
    TEST = "test"
    AUTO = "auto"


@dataclass(frozen=True)
class KyutaiReleaseThresholds:
    median_end_to_audio_ms: float = 750.0
    p95_end_to_audio_ms: float = 1_000.0
    false_endpoint_rate: float = 0.03
    missed_endpoint_rate: float = 0.05
    interruption_to_silence_ms: float = 250.0
    underrun_turn_rate: float = 0.02
    downstream_p95_regression: float = 0.15

    def payload(self) -> dict[str, float]:
        return {
            "median_end_to_audio_ms": self.median_end_to_audio_ms,
            "p95_end_to_audio_ms": self.p95_end_to_audio_ms,
            "false_endpoint_rate": self.false_endpoint_rate,
            "missed_endpoint_rate": self.missed_endpoint_rate,
            "interruption_to_silence_ms": self.interruption_to_silence_ms,
            "underrun_turn_rate": self.underrun_turn_rate,
            "downstream_p95_regression": self.downstream_p95_regression,
        }


@dataclass(frozen=True)
class KyutaiAuthorityDecision:
    mode: KyutaiAuthorityMode
    eligible: bool
    upstream_ready: bool
    model_warm: bool
    language_supported: bool
    quality_gate_passed: bool
    contention_gate_passed: bool
    reasons: tuple[str, ...]
    evaluated_at: float
    thresholds: KyutaiReleaseThresholds

    def payload(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "eligible": self.eligible,
            "upstream_ready": self.upstream_ready,
            "model_warm": self.model_warm,
            "language_supported": self.language_supported,
            "quality_gate_passed": self.quality_gate_passed,
            "contention_gate_passed": self.contention_gate_passed,
            "reasons": list(self.reasons),
            "evaluated_at": self.evaluated_at,
            "thresholds": self.thresholds.payload(),
        }


def parse_authority_mode(value: str | None) -> KyutaiAuthorityMode:
    normalized = (value or KyutaiAuthorityMode.OBSERVATIONAL.value).strip().lower()
    try:
        return KyutaiAuthorityMode(normalized)
    except ValueError as exc:
        raise ValueError(f"unsupported Kyutai authority mode: {normalized}") from exc


def environment_gate(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "passed"}


def evaluate_kyutai_authority(
    health: Mapping[str, Any],
    *,
    language: str,
    mode: KyutaiAuthorityMode | str,
    now: float | None = None,
    warm_max_age_seconds: float | None = None,
    quality_gate_passed: bool | None = None,
    contention_gate_passed: bool | None = None,
    thresholds: KyutaiReleaseThresholds | None = None,
) -> KyutaiAuthorityDecision:
    resolved_mode = mode if isinstance(mode, KyutaiAuthorityMode) else parse_authority_mode(mode)
    evaluated_at = time.time() if now is None else now
    warm_age = warm_max_age_seconds
    if warm_age is None:
        warm_age = float(os.environ.get("KYUTAI_STT_WARM_MAX_AGE_SECONDS", "120"))
    quality_passed = (
        environment_gate("KYUTAI_STT_QUALITY_GATE_PASSED")
        if quality_gate_passed is None
        else quality_gate_passed
    )
    contention_passed = (
        environment_gate("KYUTAI_STT_CONTENTION_GATE_PASSED")
        if contention_gate_passed is None
        else contention_gate_passed
    )
    supported = {
        str(item).strip().lower()
        for item in health.get("supported_languages", [])
        if str(item).strip()
    }
    normalized_language = language.strip().lower().replace("_", "-")
    language_supported = normalized_language in supported
    upstream_ready = bool(health.get("upstream_ready")) and health.get("state") == "closed"
    last_ready_at = health.get("last_ready_at")
    try:
        ready_age = evaluated_at - float(last_ready_at)
    except (TypeError, ValueError):
        ready_age = float("inf")
    model_warm = upstream_ready and 0.0 <= ready_age <= max(0.0, warm_age)

    reasons: list[str] = []
    if not language_supported:
        reasons.append("language_not_supported")
    if not upstream_ready:
        reasons.append("upstream_not_ready")
    if not model_warm:
        reasons.append("model_not_warm")
    if resolved_mode is KyutaiAuthorityMode.AUTO:
        if not quality_passed:
            reasons.append("quality_gate_not_passed")
        if not contention_passed:
            reasons.append("contention_gate_not_passed")
    if resolved_mode is KyutaiAuthorityMode.OBSERVATIONAL:
        reasons.append("observational_mode")

    base_ready = language_supported and upstream_ready and model_warm
    eligible = base_ready and (
        resolved_mode is KyutaiAuthorityMode.TEST
        or (
            resolved_mode is KyutaiAuthorityMode.AUTO
            and quality_passed
            and contention_passed
        )
    )
    return KyutaiAuthorityDecision(
        mode=resolved_mode,
        eligible=eligible,
        upstream_ready=upstream_ready,
        model_warm=model_warm,
        language_supported=language_supported,
        quality_gate_passed=quality_passed,
        contention_gate_passed=contention_passed,
        reasons=tuple(reasons),
        evaluated_at=evaluated_at,
        thresholds=thresholds or KyutaiReleaseThresholds(),
    )
