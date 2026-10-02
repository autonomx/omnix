"""Image progress travels with the generation; residency is owned through device permits (WP-8.8)."""
import io
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import image_http_client
from app.image import lifecycle, service
from app.persistence import device_permits


@pytest.fixture
def image_service(monkeypatch):
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", secrets.token_urlsafe(32))
    monkeypatch.setenv("OMNIX_IMAGE_ENABLED", "1")
    monkeypatch.setenv("OMNIX_IMAGE_URL", "http://127.0.0.1:5301")
    requests = []

    def serve(*lines):
        body = b"".join(json.dumps(line).encode("utf-8") + b"\n" for line in lines)

        def open_request(request, timeout):
            requests.append(request)
            return io.BytesIO(body)

        monkeypatch.setattr(image_http_client.urllib.request, "build_opener",
                            lambda *_handlers: SimpleNamespace(open=open_request))

    return serve, requests


def test_streamed_generation_reports_steps_then_returns_the_result(image_service):
    serve, requests = image_service
    serve(
        {"event": "progress", "current": 1, "total": 4, "message": "Generating image"},
        {"event": "progress", "current": 4, "total": 4, "message": "Generating image"},
        {"event": "result", "ok": True, "provider": "flux_klein", "seed": 7},
    )
    steps = []

    result = image_http_client.generate_image_via_service(
        {"prompt": "harbor"}, on_progress=lambda *step: steps.append(step),
    )

    assert result == {"ok": True, "provider": "flux_klein", "seed": 7}
    assert steps == [(1, 4, "Generating image"), (4, 4, "Generating image")]
    assert requests[0].get_header("Accept") == "application/x-ndjson"


def test_a_failing_progress_report_does_not_abandon_the_generation(image_service):
    serve, _requests = image_service
    serve({"event": "progress", "current": 1, "total": 2}, {"event": "result", "ok": True})

    def broken(*_step):
        raise RuntimeError("job store unavailable")

    assert image_http_client.generate_image_via_service({}, on_progress=broken) == {"ok": True}


def test_a_streamed_error_raises(image_service):
    serve, _requests = image_service
    serve({"event": "progress", "current": 1, "total": 2}, {"event": "error", "error": "model_service_error"})

    with pytest.raises(RuntimeError, match="image_service_http_500:model_service_error"):
        image_http_client.generate_image_via_service({}, on_progress=lambda *_step: None)


def test_the_job_callback_is_handed_to_the_service_not_serialized(monkeypatch):
    monkeypatch.setattr(service, "is_image_service_enabled", lambda: True)
    monkeypatch.setenv("OMNIX_IMAGE_SERVICE_MODE", "0")
    calls = []

    def generate_via_service(payload, *, on_progress=None):
        calls.append((payload, on_progress))
        return {"ok": True, "provider": "flux_klein"}

    monkeypatch.setattr(service, "generate_image_via_service", generate_via_service)

    def report(*_step):
        return None

    service.generate_image({"prompt": "harbor", "_progress_callback": report})

    assert calls == [({"prompt": "harbor"}, report)]


class _Guard:
    def __init__(self, on_lost):
        self.on_lost = on_lost
        self.closed = False

    def close(self):
        self.closed = True


class _Permits:
    def __init__(self, *, owned_elsewhere=False):
        self.owned_elsewhere = owned_elsewhere
        self.guards = []

    def hold_model_owner(self, model_class, *, holder_id, process_role, on_lost=None):
        assert (model_class, process_role) == ("image", "image")
        if self.owned_elsewhere:
            raise device_permits.DevicePermitError("model image is already loaded by image:4242")
        self.guards.append(_Guard(on_lost))
        return self.guards[-1]


@pytest.fixture
def permits(monkeypatch):
    lifecycle.unload_all_image_providers()
    holder = {}
    monkeypatch.setattr(device_permits, "default_device_permit_service", lambda: holder.get("service"))
    yield holder
    lifecycle.unload_all_image_providers()


def test_residency_is_held_while_a_provider_is_cached(permits):
    permits["service"] = _Permits()

    lifecycle.get_or_create_image_provider("mock")
    lifecycle.get_or_create_image_provider("mock")
    guards = permits["service"].guards
    assert len(guards) == 1 and not guards[0].closed

    lifecycle.unload_image_provider("mock")
    assert guards[0].closed


def test_a_second_process_is_refused_instead_of_loading_a_competing_copy(permits):
    permits["service"] = _Permits(owned_elsewhere=True)

    with pytest.raises(RuntimeError, match="image_model_owned_elsewhere"):
        lifecycle.get_or_create_image_provider("mock")
    assert lifecycle.get_cached_provider("mock") is None


def test_losing_the_lease_unloads_local_providers(permits):
    permits["service"] = _Permits()
    lifecycle.get_or_create_image_provider("mock")
    guard = permits["service"].guards[0]

    guard.on_lost()

    assert lifecycle.get_cached_provider("mock") is None
    assert not guard.closed  # the renewal thread already stopped; nothing to join
    lifecycle.get_or_create_image_provider("mock")
    assert len(permits["service"].guards) == 2  # a later load claims afresh


def test_only_the_launched_service_process_coordinates_permits():
    # A subprocess: importing the launcher entrypoint registers the hook on
    # the shared app, which must not leak into this test session.
    script = (
        "import json\n"
        "from app import image_service_runtime as runtime\n"
        "before = [hook.__name__ for hook in runtime.app.router.on_startup]\n"
        "from app import image_service_app\n"
        "after = [hook.__name__ for hook in image_service_app.app.router.on_startup]\n"
        "print(json.dumps([before, after]))\n"
    )
    output = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[3])},
    ).stdout
    before, after = json.loads(output.strip().splitlines()[-1])

    assert "_coordinate_device_permits" not in before
    assert after[0] == "_coordinate_device_permits"
