from __future__ import annotations

from types import SimpleNamespace

from app.audiobook.classifier import local_classifier, with_classification_rules


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
    assert classify({"span_id": "span-1"})["span_id"] == "span-1"
    assert calls and calls[0]["stream"] is False
    system_prompt = calls[0]["messages"][0].content
    assert "copy each requested span_id verbatim" in system_prompt
    assert "never invent, shorten, truncate, or alter an ID" in system_prompt
    assert "Each span object must contain exactly span_id, speaker, confidence, ambiguity" in system_prompt
    assert "Do not return role, delivery, emotion, tone" in system_prompt
    assert "Do not put explanations such as 'pronoun-resolved to X' in ambiguity" in system_prompt
    assert calls[0]["request_timeout_seconds"] == 180.0
    assert calls[0]["reasoning_effort"] == "xhigh"


def test_custom_rules_follow_analysis_verification_and_repair_calls() -> None:
    calls = []
    rules = "Character quotes can also be in speaker: quote format."
    def classifier(context):
        calls.append(context)
        return {"spans": []}

    classify = with_classification_rules(classifier, rules)
    for task in ("discover_dialogue_style", "analyze_story_dialogue_full_context",
                 "verify_story_dialogue_full_context", "repair_story_dialogue_missing_spans"):
        context = {"task": task}
        classify(context)
        assert "custom_rules" not in context
        assert calls[-1] == {"task": task, "custom_rules": rules}


def test_style_discovery_uses_low_reasoning_without_downgrading_speaker_analysis(monkeypatch) -> None:
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
                content='{"styles":[]}',
            )

    monkeypatch.setattr("app.audiobook.classifier.get_provider", lambda: Provider())
    classifier = local_classifier()
    assert classifier is not None
    classify, _details = classifier

    classify({
        "task": "discover_dialogue_style",
        "allowed_styles": [],
        "samples": [],
    })

    assert calls[0]["reasoning_effort"] == "low"
    assert "Identify dialogue punctuation conventions" in calls[0]["messages"][0].content


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
    assert classify({"span_id": "span-1"})["span_id"] == "span-1"


def _provider_returning(*contents, finish_reason=None):
    calls = []
    responses = list(contents)

    class Provider:
        provider_name = "lmstudio"
        config = SimpleNamespace(model="local-model")

        def chat_completion(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(model="local-model", content=responses.pop(0), finish_reason=finish_reason)

    return Provider(), calls


def test_the_structured_gateway_sends_the_request_unchanged(monkeypatch) -> None:
    provider, calls = _provider_returning('{"characters":[],"spans":[]}')
    monkeypatch.setattr("app.audiobook.classifier.get_provider", lambda: provider)
    classify, details = local_classifier()

    assert classify({"task": "analyze_story_dialogue_full_context"}) == {"characters": [], "spans": []}
    assert set(calls[0]) == {"messages", "stream", "request_timeout_seconds"}
    assert calls[0]["request_timeout_seconds"] == 180.0
    assert details["model"] == "local-model"


def test_unusable_classifier_output_is_a_parse_failure(monkeypatch) -> None:
    import pytest

    for content in ('```json\n{"spans":[]}\n```', '["not", "an", "object"]', "   "):
        provider, _calls = _provider_returning(content)
        monkeypatch.setattr("app.audiobook.classifier.get_provider", lambda provider=provider: provider)
        classify, _details = local_classifier()
        with pytest.raises(ValueError):
            classify({"task": "analyze_story_dialogue_full_context"})

    provider, _calls = _provider_returning('{"spans":[', finish_reason="length")
    monkeypatch.setattr("app.audiobook.classifier.get_provider", lambda: provider)
    classify, _details = local_classifier()
    with pytest.raises(ValueError, match="unusable"):
        classify({"task": "analyze_story_dialogue_full_context"})


def test_the_document_structure_classifier_sends_its_request_unchanged(monkeypatch) -> None:
    from app.audiobook.document_structure_classifier import local_structure_classifier

    provider, calls = _provider_returning('{"blocks":[]}')
    monkeypatch.setattr("app.audiobook.document_structure_classifier.get_provider", lambda: provider)
    classify, details = local_structure_classifier()

    assert classify({"task": "classify_document_regions"}) == {"blocks": []}
    assert set(calls[0]) == {"messages", "stream", "reasoning_effort", "request_timeout_seconds"}
    assert calls[0]["reasoning_effort"] == "low"
    assert details["model"] == "local-model"
