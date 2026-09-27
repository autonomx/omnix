"""Thin FastAPI gateway foundation for the Omnix web app redesign."""

from __future__ import annotations

from functools import wraps
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import tts_live_call_websocket as _tts_live_call_websocket
from .live_chat_companion_context import install_live_chat_companion_context_hook
from .live_chat_live_voice_profile import install_live_chat_live_voice_profile_hook
from .live_chat_lmstudio_diagnostics import (
    install_live_chat_lmstudio_diagnostics_hook,
)
from .live_chat_lmstudio_responses import install_live_chat_lmstudio_responses_hook
from .live_chat_low_latency_stream import install_live_chat_low_latency_stream_hook
from .live_chat_postgres_fast_path import install_live_chat_postgres_fast_path
from .live_chat_prompt_cache import install_live_chat_prompt_cache_hook
from .live_chat_prompt_dependency_stages import (
    install_live_chat_prompt_dependency_stage_hook,
)
from .live_chat_prompt_window import install_live_chat_prompt_window_hook
from .live_chat_provider_metrics import install_live_chat_provider_metrics_hook
from .live_chat_provider_routing import install_live_chat_provider_routing_hook
from .live_chat_stream_retry import install_live_chat_stream_retry_hook
from .live_sse_transport import install_live_sse_transport_hook
from .live_voice_runtime_offload import (
    get_cached_live_tts_provider,
    install_live_voice_runtime_offload_hook,
)
from .live_voice_spoken_style import install_live_voice_spoken_style_hook
from .lmstudio_loaded_model_resolution import (
    install_lmstudio_loaded_model_resolution_hook,
)
from .memory_job_offload import install_memory_job_offload_hook
from .rpg_turn_job_mirror import install_rpg_turn_job_mirror_hook
from .tts_live_call_pcm_diagnostics import (
    install_tts_live_call_pcm_diagnostics_hook,
)
from .tts_live_call_startup_frame_policy import (
    install_tts_live_call_startup_frame_policy,
)


_LOCAL_BROWSER_CORS_HOOK = "_omnix_local_browser_cors_hook_installed"
_LOCAL_BROWSER_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
)


def _install_local_browser_cors_hook() -> None:
    """Allow the local Vite UI to reach the gateway without the dev proxy."""
    if getattr(FastAPI, _LOCAL_BROWSER_CORS_HOOK, False):
        return
    original_init = FastAPI.__init__

    @wraps(original_init)
    def patched_init(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        title = kwargs.get("title")
        if title is None and args:
            title = args[0]
        if title != "Omnix Web Gateway":
            return
        self.add_middleware(
            CORSMiddleware,
            allow_origins=list(_LOCAL_BROWSER_ORIGINS),
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
            max_age=86_400,
        )

    FastAPI.__init__ = patched_init  # type: ignore[method-assign]
    setattr(FastAPI, _LOCAL_BROWSER_CORS_HOOK, True)


def _install_required_rpg_turn_hooks() -> None:
    from app.rpg.session import interactive_first_call_runtime
    from app.rpg.session.dialogue_quality_hook import install_dialogue_quality_hook
    from app.rpg.session.fast_visible_dialogue_hook import (
        install_fast_visible_dialogue_hook,
    )
    from app.rpg.session.interaction_lifecycle_hook import (
        install_interaction_lifecycle_hook,
    )
    from app.rpg.session.interaction_timeline_hook import (
        install_interaction_timeline_hook,
    )

    install_fast_visible_dialogue_hook()
    install_dialogue_quality_hook()
    install_interaction_timeline_hook()
    install_interaction_lifecycle_hook()
    if not getattr(
        interactive_first_call_runtime,
        "_omnix_fast_visible_dialogue_hook_installed",
        False,
    ):
        raise RuntimeError("RPG fast visible dialogue hook failed to install")
    if not getattr(
        interactive_first_call_runtime, "_omnix_dialogue_quality_hook_installed", False
    ):
        raise RuntimeError("RPG dialogue quality hook failed to install")
    if not getattr(
        interactive_first_call_runtime,
        "_omnix_interaction_timeline_hook_installed",
        False,
    ):
        raise RuntimeError("RPG interaction timeline hook failed to install")
    if not getattr(
        interactive_first_call_runtime,
        "_omnix_interaction_lifecycle_runtime_hook_installed",
        False,
    ):
        raise RuntimeError("RPG interaction lifecycle runtime hook failed to install")
    install_rpg_turn_job_mirror_hook(constructor_hook=False)


def initialize_gateway_runtime_hooks():
    from .companion_activity_user_turn import install_companion_activity_user_turn_hook

    install_companion_activity_user_turn_hook()
    install_live_sse_transport_hook(constructor_hook=False)
    install_live_chat_postgres_fast_path()
    install_live_chat_low_latency_stream_hook()
    install_live_chat_provider_metrics_hook()
    install_live_chat_stream_retry_hook()
    install_live_chat_provider_routing_hook()
    install_live_chat_prompt_window_hook()
    install_live_chat_live_voice_profile_hook()
    install_lmstudio_loaded_model_resolution_hook()
    install_live_chat_lmstudio_responses_hook()
    install_live_voice_spoken_style_hook()
    install_live_chat_companion_context_hook()
    install_live_chat_prompt_cache_hook()
    install_live_chat_prompt_dependency_stage_hook()
    install_live_chat_lmstudio_diagnostics_hook()
    install_memory_job_offload_hook()
    install_live_voice_runtime_offload_hook(constructor_hook=False)
    if _tts_live_call_websocket.get_tts_provider is _tts_live_call_websocket.shared.get_tts_provider:
        # Preserve the explicit dependency seam used by alternate compositions.
        _tts_live_call_websocket.get_tts_provider = get_cached_live_tts_provider
    install_tts_live_call_pcm_diagnostics_hook()
    install_tts_live_call_startup_frame_policy()
