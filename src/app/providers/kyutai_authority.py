"""Fail-closed promotion gates for authoritative Kyutai live STT."""
from __future__ import annotations

import math
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any


class KyutaiAuthorityMode(str, Enum):
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
class KyutaiReleaseMeasurements:
    median_end_to_audio_ms: float | None = None
    p95_end_to_audio_ms: float | None = None
    false_endpoint_rate: float | None = None
    missed_endpoint_rate: float | None = None
    interruption_to_silence_ms: float | None = None
    underrun_turn_rate: float | None = None
    downstream_p95_regression: float | None = None

    @classmethod
    def from_environment(cls) -> KyutaiReleaseMeasurements:
        return cls(
            median_end_to_audio_ms=_environment_float("KYUTAI_STT_MEDIAN_END_TO_AUDIO_MS"),
            p95_end_to_audio_ms=_environment_float("KYUTAI_STT_P95_END_TO_AUDIO_MS"),
            false_endpoint_rate=_environment_float("KYUTAI_STT_FALSE_ENDPOINT_RATE"),
            missed_endpoint_rate=_environment_float("KYUTAI_STT_MISSED_ENDPOINT_RATE"),
            interruption_to_silence_ms=_environment_float(
                "KYUTAI_STT_INTERRUPTION_TO_SILENCE_MS"
            ),
            underrun_turn_rate=_environment_float("KYUTAI_STT_UNDERRUN_TURN_RATE"),
            downstream_p95_regression=_environment_float(
                "KYUTAI_STT_DOWNSTREAM_P95_REGRESSION"
            ),
        )

    def payload(self) -> dict[str, float | None]:
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
    quality_metric_failures: tuple[str, ...]
    contention_metric_failures: tuple[str, ...]
    reasons: tuple[str, ...]
    evaluated_at: float
    thresholds: KyutaiReleaseThresholds
    measurements: KyutaiReleaseMeasurements

    def payload(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "eligible": self.eligible,
            "upstream_ready": self.upstream_ready,
            "model_warm": self.model_warm,
            "language_supported": self.language_supported,
            "quality_gate_passed": self.quality_gate_passed,
            "contention_gate_passed": self.contention_gate_passed,
            "quality_metric_failures": list(self.quality_metric_failures),
            "contention_metric_failures": list(self.contention_metric_failures),
            "reasons": list(self.reasons),
            "evaluated_at": self.evaluated_at,
            "thresholds": self.thresholds.payload(),
            "measurements": self.measurements.payload(),
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
    measurements: KyutaiReleaseMeasurements | None = None,
) -> KyutaiAuthorityDecision:
    resolved_mode = mode if isinstance(mode, KyutaiAuthorityMode) else parse_authority_mode(mode)
    evaluated_at = time.time() if now is None else now
    resolved_thresholds = thresholds or KyutaiReleaseThresholds()
    resolved_measurements = measurements or KyutaiReleaseMeasurements.from_environment()
    warm_age = warm_max_age_seconds
    if warm_age is None:
        warm_age = float(os.environ.get("KYUTAI_STT_WARM_MAX_AGE_SECONDS", "120"))

    quality_failures = _quality_metric_failures(resolved_measurements, resolved_thresholds)
    contention_failures = _contention_metric_failures(
        resolved_measurements,
        resolved_thresholds,
    )
    if quality_gate_passed is None:
        quality_passed = (
            environment_gate("KYUTAI_STT_QUALITY_GATE_PASSED")
            and not quality_failures
        )
    else:
        quality_passed = quality_gate_passed
    if contention_gate_passed is None:
        contention_passed = (
            environment_gate("KYUTAI_STT_CONTENTION_GATE_PASSED")
            and not contention_failures
        )
    else:
        contention_passed = contention_gate_passed

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
        if quality_failures:
            reasons.append("quality_metrics_not_satisfied")
        if contention_failures:
            reasons.append("contention_metrics_not_satisfied")
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
        quality_metric_failures=quality_failures,
        contention_metric_failures=contention_failures,
        reasons=tuple(reasons),
        evaluated_at=evaluated_at,
        thresholds=resolved_thresholds,
        measurements=resolved_measurements,
    )


def _quality_metric_failures(
    measurements: KyutaiReleaseMeasurements,
    thresholds: KyutaiReleaseThresholds,
) -> tuple[str, ...]:
    checks = (
        ("median_end_to_audio_ms", measurements.median_end_to_audio_ms, thresholds.median_end_to_audio_ms),
        ("p95_end_to_audio_ms", measurements.p95_end_to_audio_ms, thresholds.p95_end_to_audio_ms),
        ("false_endpoint_rate", measurements.false_endpoint_rate, thresholds.false_endpoint_rate),
        ("missed_endpoint_rate", measurements.missed_endpoint_rate, thresholds.missed_endpoint_rate),
        (
            "interruption_to_silence_ms",
            measurements.interruption_to_silence_ms,
            thresholds.interruption_to_silence_ms,
        ),
        ("underrun_turn_rate", measurements.underrun_turn_rate, thresholds.underrun_turn_rate),
    )
    return tuple(_failed_metric(name, value, maximum) for name, value, maximum in checks if _metric_failed(value, maximum))


def _contention_metric_failures(
    measurements: KyutaiReleaseMeasurements,
    thresholds: KyutaiReleaseThresholds,
) -> tuple[str, ...]:
    if _metric_failed(
        measurements.downstream_p95_regression,
        thresholds.downstream_p95_regression,
    ):
        return (
            _failed_metric(
                "downstream_p95_regression",
                measurements.downstream_p95_regression,
                thresholds.downstream_p95_regression,
            ),
        )
    return ()


def _metric_failed(value: float | None, maximum: float) -> bool:
    return value is None or not math.isfinite(value) or value < 0 or value > maximum


def _failed_metric(name: str, value: float | None, maximum: float) -> str:
    if value is None or not math.isfinite(value):
        return f"{name}:missing"
    if value < 0:
        return f"{name}:invalid"
    return f"{name}:above_{maximum:g}"


def _environment_float(name: str) -> float | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None
