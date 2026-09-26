from __future__ import annotations

from types import SimpleNamespace

from app.audiobook.document_structure_classifier import (
    DOCUMENT_STRUCTURE_CLASSIFIER_VERSION,
    local_structure_classifier,
)


def test_structure_classifier_is_low_cost_and_allows_unknown(monkeypatch) -> None:
    calls = []

    class Provider:
        provider_name = "chatgpt_codex"
        config = SimpleNamespace(model="gpt-5.6-luna")

        def chat_completion(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                model="gpt-5.6-luna",
                content=(
                    '{"blocks":[{"block_id":"b1","content_role":"unknown",'
                    '"confidence":0.5}]}'
                ),
            )

    monkeypatch.setattr(
        "app.audiobook.document_structure_classifier.get_provider",
        lambda: Provider(),
    )
    classifier = local_structure_classifier()
    assert classifier is not None
    classify, details = classifier

    response = classify({
        "allowed_roles": ["story_text", "unknown"],
        "region": [{"block_id": "b1", "text": "North Gate"}],
    })

    assert '"content_role":"unknown"' in response
    assert details["version"] == DOCUMENT_STRUCTURE_CLASSIFIER_VERSION
    assert details["reasoning_effort"] == "low"
    assert details["model"] == "gpt-5.6-luna"
    assert calls[0]["stream"] is False
    assert calls[0]["reasoning_effort"] == "low"
    assert calls[0]["request_timeout_seconds"] == 60.0
    system_prompt = calls[0]["messages"][0].content
    assert "UNKNOWN is always valid" in system_prompt
    assert "NOT speaker attribution" in system_prompt
    assert "Do not rewrite" in system_prompt


def test_structure_classifier_absence_is_nonfatal(monkeypatch) -> None:
    def unavailable():
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        "app.audiobook.document_structure_classifier.get_provider",
        unavailable,
    )
    assert local_structure_classifier() is None
