"""Provider and model ids, and a provider's reasoning level, are read in one place (deep-modules wave 2)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.providers.base import configured_reasoning_effort
from app.providers.model_route import ModelRoute, model_name_of, model_provider_of


@pytest.mark.parametrize(
    ("value", "name", "provider"),
    [
        ("llm:lmstudio:qwen3", "qwen3", "lmstudio"),
        ("llm:chatgpt_codex:gpt-5.6", "gpt-5.6", "chatgpt_codex"),
        ("LLM:Claude_CLI:haiku", "haiku", "claude_cli"),
        ("llm:lmstudio:org/model:q4", "org/model:q4", "lmstudio"),  # a model name may hold colons
        ("qwen3", "qwen3", ""),
        ("  gemma-4 ", "gemma-4", ""),
        ("llm:lmstudio:", "", "lmstudio"),
        ("llm:lmstudio", "", ""),  # names a provider, not a model
        ("", "", ""),
        (None, "", ""),
    ],
)
def test_a_model_reference_gives_its_name_and_provider(value, name, provider) -> None:
    assert (model_name_of(value), model_provider_of(value)) == (name, provider)


def test_a_route_keeps_only_its_own_providers_model() -> None:
    own = ModelRoute.parse("llm:claude_cli", "llm:claude_cli:haiku")
    foreign = ModelRoute.parse("llm:claude_cli", "llm:lmstudio:gemma")
    bare = ModelRoute.parse("lmstudio", "gemma-4")

    assert (own.provider, own.model, own.matched, own.own_model) == ("claude_cli", "haiku", True, "haiku")
    assert (foreign.provider, foreign.matched, foreign.own_model) == ("claude_cli", False, "")
    assert (bare.provider, bare.own_model) == ("lmstudio", "gemma-4")


def test_a_selected_model_leads_the_route_to_its_provider() -> None:
    assert ModelRoute.parse("lmstudio", "llm:chatgpt_codex:gpt-5.6").model_led() == ModelRoute(
        "chatgpt_codex", "gpt-5.6", "chatgpt_codex")
    assert ModelRoute.parse("lmstudio", "qwen3").model_led() == ModelRoute("lmstudio", "qwen3")
    assert ModelRoute.parse("lmstudio", "llm:claude_cli:").model_led().provider == "lmstudio"


def test_a_providers_reasoning_level_comes_from_itself_then_its_extra_params() -> None:
    codex = SimpleNamespace(reasoning_effort="medium", config=SimpleNamespace(extra_params={"reasoning_effort": "low"}))
    local = SimpleNamespace(config=SimpleNamespace(extra_params={"reasoning_effort": " high "}))
    plain = SimpleNamespace(config=SimpleNamespace(extra_params=None))

    assert [configured_reasoning_effort(p) for p in (codex, local, plain, None)] == ["medium", "high", "", ""]
