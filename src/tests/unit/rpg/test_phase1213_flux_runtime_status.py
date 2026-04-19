from app.rpg.visual.runtime_status import validate_flux_klein_runtime


def test_validate_flux_klein_runtime_returns_structured_payload():
    payload = validate_flux_klein_runtime()

    assert isinstance(payload, dict)
    assert payload.get("provider") == "flux_klein"
    assert payload.get("status") in {"ready", "not_ready"}
    assert isinstance(payload.get("ready"), bool)
    assert "summary" in payload
    assert "error" in payload
    assert isinstance(payload.get("details"), dict)