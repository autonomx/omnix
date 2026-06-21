from __future__ import annotations

from copy import deepcopy

from app.rpg.session.environment_survival_context import derive_survival_exposure_context


def _snapshot(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "temperature_c": 12,
        "wind": "light",
        "terrain_condition": "dry",
        "weather": {"condition": "clear", "intensity": "light"},
        "context": {"exposure": "outdoor", "shelter": "exposed"},
    }
    base.update(overrides)
    return base


def test_survival_context_represents_cold_exposure() -> None:
    snapshot = _snapshot(
        temperature_c=-12,
        wind="strong",
        terrain_condition="deep_snow",
        weather={"condition": "snow", "intensity": "heavy"},
    )

    context = derive_survival_exposure_context(snapshot)

    assert context["cold_risk"] in {"high", "severe"}
    assert context["wet_exposure"] in {"low", "moderate"}
    assert context["terrain_exposure"] == "low"
    assert context["overall_exposure"] == "severe"


def test_indoor_shelter_reduces_outdoor_exposure_inputs() -> None:
    snapshot = _snapshot(
        temperature_c=-12,
        wind="strong",
        terrain_condition="deep_snow",
        weather={"condition": "snow", "intensity": "heavy"},
        context={"exposure": "indoor", "shelter": "sheltered"},
    )

    context = derive_survival_exposure_context(snapshot)

    assert context["cold_risk"] in {"none", "low"}
    assert context["wet_exposure"] == "none"
    assert context["shelter_quality"] == "protected"
    assert context["rest_context"] == "rest_friendly"


def test_survival_context_represents_heat_exposure() -> None:
    context = derive_survival_exposure_context(_snapshot(temperature_c=38))

    assert context["heat_risk"] == "high"
    assert context["overall_exposure"] == "high"


def test_survival_context_is_snapshot_only() -> None:
    snapshot = _snapshot(temperature_c=-6, context={"exposure": "outdoor", "shelter": "partial"})
    original = deepcopy(snapshot)

    context = derive_survival_exposure_context(snapshot)

    assert context["shelter_quality"] == "partial"
    assert context["rest_context"] in {"rest_friendly", "rest_watchful"}
    assert snapshot == original
