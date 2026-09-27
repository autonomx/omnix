"""Voice/TTS feature declaration."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.jobs.handlers import JobExecutionContext, JobHandlerSpec
from app.jobs.models import ResourceClass
from app.runtime.features import FeatureModule

from .jobs import execute_voice_studio_job


class VoiceJobInput(BaseModel):
    model_config = ConfigDict(extra="allow")


def _execute(context: JobExecutionContext, job):
    return execute_voice_studio_job(context.job_store, job)


FEATURE = FeatureModule(
    id="voice",
    title="Voice",
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
        )
        for job_type in (
            "tts.synthesize",
            "tts.multi_speaker_synthesize",
            "voice-cloning.create-profile",
            "voice-cloning.transcribe-sample",
        )
    ),
)
