from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from app.providers import llm_admission


@pytest.fixture
def permits(monkeypatch):
    taken: list[dict] = []

    def slot(model_class, **kwargs):
        taken.append({"model_class": model_class, **kwargs})
        return nullcontext("lease")

    monkeypatch.setattr(llm_admission, "device_permit_slot", slot)
    return taken


@pytest.mark.parametrize("provider", ["lmstudio", "llamacpp", "llm:llamacpp", " LMStudio "])
def test_a_local_gpu_provider_holds_the_llm_permit(permits, provider) -> None:
    with llm_admission.llm_admission(provider) as lease:
        assert lease == "lease"
    assert permits == [{"model_class": "llm-local", "priority": "batch", "timeout_seconds": 30.0}]


def test_a_provider_instance_is_judged_by_its_declared_id(permits) -> None:
    with llm_admission.llm_admission(SimpleNamespace(provider_name="llamacpp"), priority="interactive", timeout_seconds=5.0):
        pass
    assert permits == [{"model_class": "llm-local", "priority": "interactive", "timeout_seconds": 5.0}]


@pytest.mark.parametrize("provider", ["claude_cli", "openrouter", "", None, "ollama"])
def test_a_hosted_or_unknown_provider_needs_no_permit(permits, provider) -> None:
    with llm_admission.llm_admission(provider) as lease:
        assert lease is None
    assert permits == []
