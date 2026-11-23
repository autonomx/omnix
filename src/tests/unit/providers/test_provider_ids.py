from __future__ import annotations

import pytest

from app.platform.agent_runtime.planning_review import _provider_key as review_provider
from app.platform.chat.store import _provider_key as chat_provider
from app.providers.catalog import provider_id_of


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("lmstudio", "lmstudio"), (" llm:LMStudio ", "lmstudio"), ("LLM:claude_cli", "claude_cli"), ("", ""), (None, "")],
)
def test_every_feature_reads_a_provider_id_the_catalog_way(raw, expected) -> None:
    assert provider_id_of(raw) == expected
    assert chat_provider(raw) == (expected or None)


def test_a_review_route_names_its_provider_without_the_model() -> None:
    assert review_provider("llm:claude_cli:sonnet") == "claude_cli"
    assert review_provider("openrouter") == "openrouter"
