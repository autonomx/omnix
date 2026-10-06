from __future__ import annotations

from contextlib import contextmanager

import pytest

from app.providers import tts_priority


@pytest.mark.parametrize(
    ("tts_priority_name", "device_priority"),
    [("realtime", "realtime"), ("preview", "interactive"), ("offline", "batch")],
)
def test_generation_slot_uses_process_independent_priority(
    monkeypatch,
    tts_priority_name: str,
    device_priority: str,
) -> None:
    acquired = []

    @contextmanager
    def permit_slot(model_class, *, priority, timeout_seconds):
        acquired.append((model_class, priority, timeout_seconds))
        yield None

    monkeypatch.setattr(tts_priority, "device_permit_slot", permit_slot)
    with tts_priority.generation_class(tts_priority_name):
        with tts_priority.generation_slot():
            pass

    assert acquired == [("tts", device_priority, 30.0)]


def test_batch_yield_detects_higher_priority_database_requests(monkeypatch) -> None:
    class Service:
        def __init__(self) -> None:
            self.request = None

        def has_higher_priority_request(self, model_class, *, priority):
            self.request = (model_class, priority)
            return True

    service = Service()
    monkeypatch.setattr(tts_priority, "default_device_permit_service", lambda: service)

    assert tts_priority.other_process_priority_pending()
    assert service.request == ("tts", "batch")
