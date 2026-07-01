from __future__ import annotations

from app.assist_core.result_shape import result_shape_payload


def test_result_shape_flags() -> None:
    payload = result_shape_payload("p1", "summary")

    assert payload["ok"] is True
    assert payload["review"] is True
