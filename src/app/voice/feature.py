"""Voice/TTS feature declaration."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.jobs.handlers import JobExecutionContext, JobHandlerSpec
from app.jobs.models import CreateJobRequest, ResourceClass
from app.platform.effective_defaults import apply_job_defaults
from app.platform.voice_cloning_defaults import apply_voice_cloning_defaults
from app.runtime.features import FeatureModule
from app.runtime.router_composition import compose_registrar_router

from .jobs import execute_voice_studio_job


class VoiceJobInput(BaseModel):
    model_config = ConfigDict(extra="allow")


def _execute(context: JobExecutionContext, job):
    return execute_voice_studio_job(context.job_store, job)


def voice_submission_defaults(request: CreateJobRequest) -> CreateJobRequest:
    value = request.model_dump(mode="python")
    if request.module == "voice-cloning":
        value = apply_voice_cloning_defaults(value)
    else:
        value = apply_job_defaults(value)
    return CreateJobRequest.model_validate(value)



def _voice_router(context):
    return compose_registrar_router(
        (
            ("app.gateway.live_voice_runtime_offload", "register_live_voice_runtime_offload"),
            ("app.gateway.live_voice_diagnostics_routes", "register_live_voice_diagnostics_routes"),
            ("app.gateway.live_voice_cue_asset_routes", "register_live_voice_cue_asset_routes"),
            ("app.gateway.tts_runtime_routes", "register_tts_runtime_routes"),
            ("app.gateway.stt_proxy_routes", "register_stt_proxy_routes"),
            ("app.gateway.tts_pcm_websocket", "register_tts_pcm_websocket"),
            ("app.gateway.tts_live_call_websocket", "register_tts_live_call_websocket"),
            ("app.gateway.live_voice_speculative_tts", "register_live_voice_execution_lane_routes"),
            ("app.gateway.voice_job_summary_routes", "register_voice_job_summary_routes"),
            ("app.gateway.voice_library_routes", "register_voice_library_route"),
        ),
        state=context.runtime_state,
    )

FEATURE = FeatureModule(
    id="voice",
    title="Voice",
    routers=(_voice_router,),
    job_handlers=tuple(
        JobHandlerSpec(
            type=job_type,
            handler=_execute,
            input_model=VoiceJobInput,
            resource_class=(
                ResourceClass.GPU_STT
                if job_type == "voice-cloning.transcribe-sample"
                else ResourceClass.GPU_TTS
            ),
            timeout_seconds=900,
            max_attempts=3,
            submission_policy=voice_submission_defaults,
        )
        for job_type in (
            "tts.synthesize",
            "tts.multi_speaker_synthesize",
            "voice-cloning.create-profile",
            "voice-cloning.transcribe-sample",
        )
    ),
)
