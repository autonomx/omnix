"""The storyteller down or too slow (RQ-8.8): failed model calls are counted apart, and a call kind's limit holds."""
from __future__ import annotations

import pytest

from app.apps.rpg.foundation.llm_app_gateway import AppLLMGateway
from app.apps.rpg.foundation.model_calls import (
    CountedProvider,
    counting_model_calls,
    current_model_calls,
    current_model_failures,
)


class _Down:
    def __init__(self) -> None:
        self.kwargs: dict = {}

    def chat_completion(self, *args, **kwargs):
        self.kwargs = kwargs
        raise TimeoutError("too slow")


def test_a_failed_call_is_counted_as_a_failure_not_only_as_a_call() -> None:
    with counting_model_calls():
        with pytest.raises(TimeoutError):
            CountedProvider(_Down()).chat_completion(messages=[])
        assert current_model_calls() == {"provider": 1}
        assert current_model_failures() == {"provider": 1}
    assert current_model_failures() == {}  # outside a turn nothing is kept


def test_the_gateway_gives_the_provider_the_call_kinds_limit() -> None:
    provider = _Down()
    with pytest.raises(TimeoutError):
        AppLLMGateway(provider).generate("hello", timeout_s=20.0, provider_options={"max_tokens": 9})
    assert provider.kwargs["request_timeout_seconds"] == 20.0 and provider.kwargs["max_tokens"] == 9
