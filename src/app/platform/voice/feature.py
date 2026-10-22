"""Voice/TTS feature declaration."""
from __future__ import annotations

from fastapi import APIRouter
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from app.jobs.handlers import JobExecutionContext, JobHandlerSpec
from app.jobs.models import CreateJobRequest, ResourceClass
from app.settings.effective_defaults import apply_job_defaults
from app.platform.voice.voice_cloning_defaults import apply_voice_cloning_defaults
from app.runtime.features import FeatureModule
from app.runtime.ports import ContributionSpec

from .client_tools import VOICE_CLIENT_TOOLS
from .jobs import execute_voice_studio_job, store_inline_clone_sample


class VoiceJobInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    @model_validator(mode="before")
    @classmethod
    def _effect_ids(cls, value: Any) -> Any:
        # Stable effect ids only; old display labels are off (see ``effects``).
        if isinstance(value, dict) and "audio_effects" in value:
            from .effects import effect_ids

            effects = value["audio_effects"]
            value = {**value, "audio_effects": effect_ids(effects if isinstance(effects, (list, tuple)) else [])}
        return value


def _execute(context: JobExecutionContext, job):
    return execute_voice_studio_job(context.job_store, job)


TTS_JOB_TYPES = ("tts.synthesize", "tts.multi_speaker_synthesize")


def voice_submission_defaults(request: CreateJobRequest) -> CreateJobRequest:
    value = request.model_dump(mode="python")
    if request.type in {"models.install", "models.remove", "models.verify"}:
        # Installs download from the internet into the shared models folder: workspace admins only.
        from app.models import packs
        from app.runtime.tenant_context import current_tenant

        current_tenant().require_role("owner", "admin")
        if packs.desktop_mode():
            payload = dict(request.input_payload or {})
            payload.pop("authorized_runtimes", None)
            if request.type != "models.verify":
                from .model_packs import AUTHORIZED_RUNTIMES, check_submission

                payload[AUTHORIZED_RUNTIMES] = check_submission(request.type, payload)
            value["input_payload"] = payload
            return CreateJobRequest.model_validate(value)
        if request.type == "models.install":
            _record_voice_studio_acceptance(dict(request.input_payload or {}))
        return request
    if request.type in {"voice.export", "voice.restitch", "voice.design", "voice.design.save", "voice.blend",
                        "voice.subtitles",
                        "audio.isolate", "audio.enhance", "audio.watermark-detect"}:
        return request  # These take their inputs from the request alone (design names its own engine).
    named_engine = str((request.input_payload or {}).get("provider_id") or "").strip()
    if request.module == "voice-cloning":
        value = apply_voice_cloning_defaults(value)
        value["input_payload"] = store_inline_clone_sample(dict(value.get("input_payload") or {}))
    else:
        value = apply_job_defaults(value)
    if request.type in TTS_JOB_TYPES and not named_engine:
        # A job that names no engine renders on the selected one: the engine
        # setting, which the profile's provider default can lag behind.
        from app.providers.service import selected_tts_provider_id

        value["input_payload"] = {**dict(value.get("input_payload") or {}),
                                  "provider_id": selected_tts_provider_id()}
    return CreateJobRequest.model_validate(value)



def _record_voice_studio_acceptance(payload: dict[str, Any]) -> None:
    """Voice Studio outside the desktop app: an accepted install is recorded like the setup screen's (D-4)."""
    from app.models import catalog as model_catalog

    from . import licence_acceptances

    if not payload.get("accept_terms") or not licence_acceptances.available():
        return
    try:
        entry = model_catalog.load().model(str(payload.get("model_id") or ""))
    except KeyError:
        return
    if entry.pinned:
        licence_acceptances.record([entry])


def _voice_router(context):
    from .automation_routes import register_automation_routes
    from .model_pack_routes import register_model_pack_routes
    from .stt_proxy_routes import register_stt_proxy_routes
    from .tts_pcm_websocket import register_tts_pcm_websocket
    from .tts_runtime_routes import register_tts_runtime_routes
    from .voice_job_summary_routes import register_voice_job_summary_routes
    from .voice_library_routes import register_voice_library_route
    from .voice_studio_routes import register_voice_studio_routes

    router = APIRouter()
    state = context.runtime_state
    register_tts_runtime_routes(router, state)
    register_stt_proxy_routes(router, state)
    register_tts_pcm_websocket(router, state)
    register_voice_job_summary_routes(router, state)
    register_voice_library_route(router, state)
    register_voice_studio_routes(router, state)
    register_automation_routes(router, state)
    register_model_pack_routes(router, state)
    return router

def _swap_controller_worker(_context):
    from .swap_controller import create_swap_controller_worker

    return create_swap_controller_worker()


def _automation_worker(context):
    from .automation import create_automation_worker

    return create_automation_worker(context.runtime_state)


# Kept in step with ``client_api.VOICE_TOOL_NAMES`` and ``automation_routes.CLIENT_API_PATHS`` (tested).
_CLIENT_TOOL_NAMES = ("speak", "transcribe", "list_voices", "design_voice", "isolate", "job_status")
_CLIENT_API_PATHS = frozenset({
    "/api/voice/v1/tools", "/api/voice/v1/tools/{name}", "/api/voice/v1/audio", "/api/voice/v1/speak",
    "/api/voice/v1/transcribe", "/api/voice/v1/voices", "/api/voice/v1/design", "/api/voice/v1/isolate",
    "/api/voice/v1/jobs/{job_id}", "/mcp/voice",
})


def _client_tool(name: str):
    def build(_context):
        from .client_api import voice_tool

        return voice_tool(name)

    return build


_JOB_RESOURCE_CLASSES = {
    "voice.subtitles": ResourceClass.CPU,
    "audio.isolate": ResourceClass.GPU_AUDIO,
    "audio.enhance": ResourceClass.GPU_AUDIO,
    "audio.watermark-detect": ResourceClass.GPU_AUDIO,
    "voice-cloning.transcribe-sample": ResourceClass.GPU_STT,
    "stt.transcribe": ResourceClass.GPU_STT,
    "voice.export": ResourceClass.CPU,
    "voice.restitch": ResourceClass.CPU,
    "models.install": ResourceClass.CPU,
    "models.remove": ResourceClass.CPU,
    "models.verify": ResourceClass.CPU,
}

FEATURE = FeatureModule(
    id="voice",
    title="Voice",
    tier="platform",
    routers=(_voice_router,),
    background_workers=(_swap_controller_worker, _automation_worker),
    # The client facade and MCP authenticate with a voice client credential, not a session.
    public_paths=_CLIENT_API_PATHS,
    contributions=tuple(ContributionSpec(VOICE_CLIENT_TOOLS, _client_tool(name)) for name in _CLIENT_TOOL_NAMES),
    job_handlers=tuple(
        JobHandlerSpec(
            type=job_type,
            handler=_execute,
            input_model=VoiceJobInput,
            resource_class=_JOB_RESOURCE_CLASSES.get(job_type, ResourceClass.GPU_TTS),
            timeout_seconds=900,
            max_attempts=3,
            submission_policy=voice_submission_defaults,
        )
        for job_type in (
            "tts.synthesize",
            "tts.multi_speaker_synthesize",
            "voice-cloning.create-profile",
            "voice-cloning.transcribe-sample",
            "voice.export",
            "voice.restitch",
            "voice.design",
            "voice.design.save",
            "voice.blend",
            "audio.isolate",
            "audio.enhance",
            "audio.watermark-detect",
            "voice.subtitles",
            "stt.transcribe",
            "models.install",
            "models.remove",
            "models.verify",
        )
    ),
)
