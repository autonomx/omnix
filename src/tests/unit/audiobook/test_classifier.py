from __future__ import annotations

from types import SimpleNamespace

from app.audiobook.classifier import local_classifier


def test_classifier_uses_configured_provider_and_model(monkeypatch) -> None:
    calls = []

    class Provider:
        provider_name = "chatgpt_codex"
        reasoning_effort = "xhigh"
        config = SimpleNamespace(
            model="gpt-5.6-luna",
            extra_params={"reasoning_effort": "xhigh"},
        )

        def chat_completion(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                model="gpt-5.6-luna",
                content='{"span_id":"span-1","speaker":"Narrator",'
                        '"role":"narration","delivery":""}',
            )

    monkeypatch.setattr("app.audiobook.classifier.get_provider", lambda: Provider())
    classifier = local_classifier()
    assert classifier is not None
    classify, details = classifier
    assert details == {
        "mode": "configured_llm_classifier",
        "provider_id": "chatgpt_codex",
        "model": "gpt-5.6-luna",
        "version": "audiobook-classifier-v8",
        "reasoning_effort": "xhigh",
    }
    assert '"span_id":"span-1"' in classify({"span_id": "span-1"})
    assert calls and calls[0]["stream"] is False
    system_prompt = calls[0]["messages"][0].content
    assert "copy each requested span_id verbatim" in system_prompt
    assert "never invent, shorten, truncate, or alter an ID" in system_prompt
    assert "Each span object must contain exactly span_id, speaker, confidence, ambiguity" in system_prompt
    assert "Do not return role, delivery, emotion, tone" in system_prompt
    assert "Do not put explanations such as 'pronoun-resolved to X' in ambiguity" in system_prompt
    assert calls[0]["request_timeout_seconds"] == 180.0
    assert calls[0]["reasoning_effort"] == "xhigh"


def test_classifier_allows_annotation_retry_after_transient_provider_error(monkeypatch) -> None:
    responses = [
        RuntimeError("temporary Codex connection failure"),
        SimpleNamespace(
            model="gpt-5.6-luna",
            content='{"span_id":"span-1","speaker":"Narrator",'
                    '"role":"narration","delivery":""}',
        ),
    ]

    class Provider:
        provider_name = "chatgpt_codex"
        config = SimpleNamespace(model="gpt-5.6-luna")

        def chat_completion(self, **kwargs):
            result = responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

    monkeypatch.setattr("app.audiobook.classifier.get_provider", lambda: Provider())
    classifier = local_classifier()
    assert classifier is not None
    classify, _details = classifier
    try:
        classify({"span_id": "span-1"})
    except RuntimeError:
        pass
    else:
        raise AssertionError("the first provider call should fail")
    assert '"span_id":"span-1"' in classify({"span_id": "span-1"})
