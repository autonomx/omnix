"""Story and podcast feature declaration."""
from __future__ import annotations

from fastapi import APIRouter

from app.jobs.handlers import JobHandlerSpec
from app.jobs.models import CreateJobRequest, ResourceClass
from app.settings.effective_defaults import apply_job_defaults
from app.runtime.features import FeatureContext, FeatureModule
from app.security.permissions import requires

from .jobs import PodcastGenerateInput, StoryGenerateInput, run_story_job
from .prompts import PREMISE_MAX_CHARS
from .routes import router as _project_router
from .podcast_research import PodcastResearchRequest, PodcastResearchResponse, research_podcast_topic


def _story_project_router(_context: FeatureContext) -> APIRouter:
    return _project_router


def _podcast_research_router(_context: FeatureContext) -> APIRouter:
    router = APIRouter()

    # A web search can spend a paid provider's quota: research's run permission, which guests do not hold.
    @router.post("/api/podcast/research", response_model=PodcastResearchResponse, openapi_extra=requires("research:run"))
    def podcast_research_endpoint(request: PodcastResearchRequest) -> PodcastResearchResponse:
        """Source notes for an episode from one web search; the producer edits them before the script is written."""
        return research_podcast_topic(request)

    return router


def _submission_defaults(request: CreateJobRequest) -> CreateJobRequest:
    return CreateJobRequest.model_validate(
        apply_job_defaults(request.model_dump(mode="python"))
    )


def _story_submission(request: CreateJobRequest) -> CreateJobRequest:
    """A new draft keeps its premise short. A follow-up on an older story (continue, a rewrite, a move)
    trims a longer premise instead of failing, so stories written before the cap can still go on."""
    payload = dict(request.input_payload or {})
    premise = str(payload.get("premise") or "").strip()
    if len(premise) > PREMISE_MAX_CHARS:
        drafting = (str(payload.get("action") or "draft") == "draft" and str(payload.get("interaction_mode") or
                    "writing") != "story" and not payload.get("project_id") and not payload.get("source_text"))
        if drafting:
            raise ValueError(f"The premise is longer than {PREMISE_MAX_CHARS} characters; shorten it and try again.")
        payload["premise"] = premise[:PREMISE_MAX_CHARS].rstrip()
        request = request.model_copy(update={"input_payload": payload})
    return _submission_defaults(request)


FEATURE = FeatureModule(
    id="story",
    title="Storyteller and Podcast",
    tier="app",
    # Podcast research reads research's contracts; with research off it answers "unavailable" (podcast_research.py).
    # A story's voices are cast and spoken through voice's contracts (voices.py); with voice off, speech is a 503.
    uses=("research", "voice"),
    routers=(_story_project_router, _podcast_research_router),
    job_handlers=(
        JobHandlerSpec(
            type="story.generate",
            run=run_story_job,
            failure_code="story_job_failed",
            input_model=StoryGenerateInput,
            resource_class=ResourceClass.GPU_LLM,
            timeout_seconds=900,
            submission_policy=_story_submission,
        ),
        JobHandlerSpec(
            type="podcast.generate",
            run=run_story_job,
            failure_code="story_job_failed",
            input_model=PodcastGenerateInput,
            resource_class=ResourceClass.GPU_LLM,
            # A long episode is a plan and up to eight parts, one model reply each (story/podcast_script.py).
            timeout_seconds=1800,
            submission_policy=_submission_defaults,
        ),
    ),
)
