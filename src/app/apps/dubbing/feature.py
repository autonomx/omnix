"""Dubbing feature declaration."""
from __future__ import annotations

from fastapi import APIRouter

from app.jobs.handlers import JobHandlerSpec
from app.platform.voice.contracts import VOICE_CLIENT_TOOLS
from app.runtime.features import FeatureContext, FeatureModule
from app.runtime.ports import ContributionSpec

from .jobs import JOB_TYPES, RESOURCE_CLASSES, DubStepInput, execute_dub_step
from .routes import router

# Long recordings make separation, transcription and synthesis the slow steps.
_TIMEOUTS = {"ingest": 900, "separate": 3600, "transcribe": 3600, "translate": 3600, "cast": 900,
             "synthesize": 7200, "mux": 1800}


def _router(_context: FeatureContext) -> APIRouter:
    return router


def _dub_status(_context: FeatureContext):
    from .client_tool import DubStatusTool

    return DubStatusTool()


FEATURE = FeatureModule(
    id="dubbing",
    title="Dubbing",
    tier="app",
    # Separation, transcription, voices and synthesis come through Voice Studio's contract.
    uses=("voice",),
    routers=(_router,),
    # dub_status for voice API clients and MCP, through Voice Studio's tool port.
    contributions=(ContributionSpec(VOICE_CLIENT_TOOLS, _dub_status),),
    job_handlers=tuple(
        JobHandlerSpec(
            type=job_type,
            handler=execute_dub_step,
            input_model=DubStepInput,
            resource_class=RESOURCE_CLASSES[step],
            timeout_seconds=_TIMEOUTS[step],
            max_attempts=2,
        )
        for job_type, step in JOB_TYPES.items()
    ),
)
