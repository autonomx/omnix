"""Phase 10.7 — LLM orchestration layer.

This package owns explicit LLM request orchestration above runtime dialogue
state. It never mutates simulation truth directly; it only writes through
runtime/orchestration state helpers.
"""

from .state import (
    ensure_llm_orchestration_state,
    get_llm_orchestration_state,
    build_llm_request_id,
    begin_llm_request,
    append_llm_stream_event,
    finalize_llm_request,
    fail_llm_request,
    trim_llm_orchestration_state,
)
from .request_builder import (
    build_llm_request_payload,
)
from .provider_interface import (
    get_llm_provider_mode,
    set_llm_provider_mode,
    build_disabled_provider_result,
    build_replay_provider_result,
)
from .replay import (
    find_replayable_llm_request,
    require_replayable_llm_request,
)
from .fallback import (
    build_llm_fallback_result,
    should_allow_llm_fallback,
)
from .stream_adapter import (
    apply_provider_result_to_runtime_turn,
)
from .controller import (
    execute_llm_request_for_turn,
)
from .live_provider import (
    ensure_live_provider_state,
    get_live_provider_state,
    build_provider_execution_id,
    begin_provider_execution,
    append_provider_execution_event,
    finalize_provider_execution,
    fail_provider_execution,
    trim_live_provider_state,
)
from .provider_adapter import (
    BaseLLMProviderAdapter,
    DeterministicMockProviderAdapter,
    LiveLLMProviderAdapter,
    get_provider_adapter,
)
from .capture import (
    persist_captured_provider_result,
)

__all__ = [
    "ensure_llm_orchestration_state",
    "get_llm_orchestration_state",
    "build_llm_request_id",
    "begin_llm_request",
    "append_llm_stream_event",
    "finalize_llm_request",
    "fail_llm_request",
    "trim_llm_orchestration_state",
    "build_llm_request_payload",
    "get_llm_provider_mode",
    "set_llm_provider_mode",
    "build_disabled_provider_result",
    "build_replay_provider_result",
    "find_replayable_llm_request",
    "require_replayable_llm_request",
    "build_llm_fallback_result",
    "should_allow_llm_fallback",
    "apply_provider_result_to_runtime_turn",
    "execute_llm_request_for_turn",
    "ensure_live_provider_state",
    "get_live_provider_state",
    "build_provider_execution_id",
    "begin_provider_execution",
    "append_provider_execution_event",
    "finalize_provider_execution",
    "fail_provider_execution",
    "trim_live_provider_state",
    "BaseLLMProviderAdapter",
    "DeterministicMockProviderAdapter",
    "LiveLLMProviderAdapter",
    "get_provider_adapter",
    "persist_captured_provider_result",
]
