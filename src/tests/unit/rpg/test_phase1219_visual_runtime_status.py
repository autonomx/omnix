from app.rpg.visual.runtime_status import validate_visual_runtime


def test_validate_visual_runtime_disabled_mode():
    payload = validate_visual_runtime("disabled")
    assert payload["provider"] == "disabled"
    assert payload["ready"] is True
    assert payload["status"] == "disabled"
    assert payload["error"] == ""


def test_validate_visual_runtime_unknown_provider():
    payload = validate_visual_runtime("missing_provider")
    assert payload["provider"] == "missing_provider"
    assert payload["ready"] is False
    assert payload["error"] == "unknown_visual_provider"