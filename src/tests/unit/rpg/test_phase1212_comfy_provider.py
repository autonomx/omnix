"""Phase 12.12 — ComfyUI provider unit tests."""
import json

from app.rpg.visual.providers.comfy_provider import ComfyImageProvider


def test_comfy_provider_returns_missing_prompt_id_as_failure(monkeypatch):
    monkeypatch.setenv("COMFY_BASE_URL", "http://comfy.local")

    def _fake_urlopen(request_or_url, timeout=180):
        class _Response:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
            def read(self):
                return json.dumps({}).encode("utf-8")
        return _Response()

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)

    provider = ComfyImageProvider()
    result = provider.generate(
        prompt="portrait",
        seed=123,
        style="rpg-portrait",
        model="local",
        kind="character_portrait",
        target_id="npc:test",
    )

    assert result.ok is False
    assert result.error == "comfy_missing_prompt_id"


def test_comfy_provider_successfully_polls_and_fetches_image(monkeypatch):
    monkeypatch.setenv("COMFY_BASE_URL", "http://comfy.local")
    calls = []

    def _fake_urlopen(request_or_url, timeout=180):
        target = getattr(request_or_url, "full_url", request_or_url)
        calls.append(target)

        class _Response:
            def __init__(self, payload=None, raw_bytes=None):
                self._payload = payload
                self._raw_bytes = raw_bytes
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
            def read(self):
                if self._raw_bytes is not None:
                    return self._raw_bytes
                return json.dumps(self._payload).encode("utf-8")

        if str(target).endswith("/prompt"):
            return _Response(payload={"prompt_id": "abc123"})
        if str(target).endswith("/history/abc123"):
            return _Response(
                payload={
                    "abc123": {
                        "outputs": {
                            "9": {
                                "images": [
                                    {"filename": "rpg_0001.png", "subfolder": "", "type": "output"}
                                ]
                            }
                        }
                    }
                }
            )
        if "/view?" in str(target):
            return _Response(raw_bytes=b"pngbytes")
        raise AssertionError(f"Unexpected URL: {target}")

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda *_args, **_kwargs: None)

    provider = ComfyImageProvider()
    result = provider.generate(
        prompt="portrait",
        seed=123,
        style="rpg-portrait",
        model="local",
        kind="character_portrait",
        target_id="npc:test",
    )

    assert result.ok is True
    assert result.status == "complete"
    assert result.image_bytes == b"pngbytes"
    assert result.revised_prompt != ""


def test_comfy_provider_invalid_graph_override_fails(monkeypatch):
    monkeypatch.setenv("COMFY_PROMPT_GRAPH_JSON", "{bad json")
    provider = ComfyImageProvider()

    result = provider.generate(
        prompt="portrait",
        seed=123,
        style="rpg-portrait",
        model="local",
        kind="character_portrait",
        target_id="npc:test",
    )

    assert result.ok is False
    assert result.error == "comfy_invalid_prompt_graph_json"


def test_comfy_provider_network_error_on_submit(monkeypatch):
    import urllib.error

    monkeypatch.setenv("COMFY_BASE_URL", "http://comfy.local")

    def _fake_urlopen(request_or_url, timeout=180):
        raise urllib.error.URLError("Network error")

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)

    provider = ComfyImageProvider()
    result = provider.generate(
        prompt="portrait",
        seed=123,
        style="rpg-portrait",
        model="local",
        kind="character_portrait",
        target_id="npc:test",
    )

    assert result.ok is False
    assert result.error == "comfy_network_error"


def test_comfy_provider_uses_custom_graph(monkeypatch):
    import urllib.error

    custom_graph = {"custom": True}
    monkeypatch.setenv("COMFY_PROMPT_GRAPH_JSON", json.dumps(custom_graph))
    monkeypatch.setenv("COMFY_BASE_URL", "http://comfy.local")

    def _fake_urlopen(request_or_url, timeout=180):
        target = getattr(request_or_url, "full_url", request_or_url)

        class _Response:
            def __init__(self, payload=None, raw_bytes=None):
                self._payload = payload
                self._raw_bytes = raw_bytes
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
            def read(self):
                if self._raw_bytes is not None:
                    return self._raw_bytes
                return json.dumps(self._payload).encode("utf-8")

        if str(target).endswith("/prompt"):
            return _Response(payload={})
        raise urllib.error.URLError("nope")

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)

    provider = ComfyImageProvider()
    result = provider.generate(
        prompt="test",
        seed=1,
        style="test",
        model="test",
        kind="character_portrait",
        target_id="test",
    )

    assert result.ok is False
    assert result.error == "comfy_missing_prompt_id"