"""Phase 12.11 — OpenAI image provider unit tests."""
import base64
import json
import urllib.error

from app.rpg.visual.providers.openai_provider import OpenAIImageProvider


def test_openai_provider_returns_missing_key_without_env(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = OpenAIImageProvider()

    result = provider.generate(
        prompt="Test portrait",
        seed=123,
        style="rpg-portrait",
        model="gpt-image-1",
        kind="character_portrait",
        target_id="npc:test",
    )

    assert result.ok is False
    assert result.status == "failed"
    assert result.error == "openai_api_key_missing"


def test_openai_provider_parses_success_response(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            payload = {
                "data": [
                    {
                        "b64_json": base64.b64encode(b"pngbytes").decode("utf-8"),
                        "revised_prompt": "Revised by provider",
                    }
                ]
            }
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=120: _Response())

    provider = OpenAIImageProvider()
    result = provider.generate(
        prompt="Test portrait",
        seed=123,
        style="rpg-portrait",
        model="gpt-image-1",
        kind="character_portrait",
        target_id="npc:test",
    )

    assert result.ok is True
    assert result.status == "complete"
    assert result.image_bytes == b"pngbytes"
    assert result.revised_prompt == "Revised by provider"
    assert result.mime_type == "image/png"


def test_openai_provider_returns_invalid_json_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"{not valid json"

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=120: _Response())

    provider = OpenAIImageProvider()
    result = provider.generate(
        prompt="Test portrait",
        seed=None,
        style="rpg-portrait",
        model="gpt-image-1",
        kind="character_portrait",
        target_id="npc:test",
    )

    assert result.ok is False
    assert result.status == "failed"
    assert result.error == "openai_invalid_json"


def test_openai_provider_returns_missing_b64_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            payload = {"data": [{"revised_prompt": "Adjusted prompt"}]}
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout=120: _Response())

    provider = OpenAIImageProvider()
    result = provider.generate(
        prompt="Test portrait",
        seed=None,
        style="rpg-portrait",
        model="gpt-image-1",
        kind="character_portrait",
        target_id="npc:test",
    )

    assert result.ok is False
    assert result.status == "failed"
    assert result.error == "openai_missing_b64_json"
    assert result.revised_prompt == "Adjusted prompt"


def test_openai_provider_marks_moderation_like_http_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class _HTTPError(urllib.error.HTTPError):
        def __init__(self):
            super().__init__(
                url="https://api.openai.com/v1/images/generations",
                code=400,
                msg="Bad Request",
                hdrs=None,
                fp=None,
            )

        def read(self):
            return b'{"error":{"message":"Rejected by safety policy"}}'

    def _raise_http_error(request, timeout=120):
        raise _HTTPError()

    monkeypatch.setattr("urllib.request.urlopen", _raise_http_error)

    provider = OpenAIImageProvider()
    result = provider.generate(
        prompt="Test portrait",
        seed=None,
        style="rpg-portrait",
        model="gpt-image-1",
        kind="character_portrait",
        target_id="npc:test",
    )

    assert result.ok is False
    assert result.status == "blocked"
    assert result.error == "openai_http_400"
    assert result.moderation_status == "blocked"
    assert "safety" in result.moderation_reason.lower() or "policy" in result.moderation_reason.lower()