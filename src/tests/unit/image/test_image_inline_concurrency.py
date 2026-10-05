from __future__ import annotations

from contextlib import contextmanager

import pytest

from app.platform.image import service
from app.platform.image import jobs


@pytest.mark.parametrize("priority", ["interactive", "batch"])
def test_local_image_provider_uses_shared_device_admission(monkeypatch, priority):
    calls = []

    @contextmanager
    def device_slot(model_class, *, priority, timeout_seconds):
        calls.append(("admit", model_class, priority, timeout_seconds))
        yield None

    class Provider:
        def generate(self, payload):
            calls.append(("generate", payload))
            return "result"

    monkeypatch.setattr(service, "device_permit_slot", device_slot)

    result = service._generate_with_device_permit(
        Provider(),
        {"prompt": "a test image"},
        priority=priority,
    )

    assert result == "result"
    assert calls == [
        ("admit", "image", priority, 30.0),
        ("generate", {"prompt": "a test image"}),
    ]
    assert not hasattr(jobs, "_IMAGE_GENERATION_SLOTS")
