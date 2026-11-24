"""Story and podcast feature declaration."""
from __future__ import annotations

from fastapi import APIRouter

from app.jobs.handlers import JobHandlerSpec
from app.jobs.models import CreateJobRequest, ResourceClass
from app.settings.effective_defaults import apply_job_defaults
from app.runtime.features import FeatureContext, FeatureModule
from app.security.permissions import requires

from .jobs import PodcastGenerateInput, StoryGenerateInput, run_story_job
from .podcast_research import PodcastResearchRequest, PodcastResearchResponse, research_podcast_topic
from .asset_save import (
    SaveStoryAssetRequest,
    SavedStoryAssetResponse,
    save_story_asset,
)


def _story_asset_router(context: FeatureContext) -> APIRouter:
    router = APIRouter()
    assets = context.services.assets
    if assets is None:
        raise RuntimeError("story feature requires the asset service")

    @router.post("/api/assets/story", response_model=SavedStoryAssetResponse)
    def save_story_asset_endpoint(
        request: SaveStoryAssetRequest,
    ) -> SavedStoryAssetResponse:
        return save_story_asset(assets, request)

    return router


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


FEATURE = FeatureModule(
    id="story",
    title="Storyteller and Podcast",
    tier="app",
    # Podcast research reads research's contracts; with research off it answers "unavailable" (podcast_research.py).
    uses=("research",),
    routers=(_story_asset_router, _podcast_research_router),
    job_handlers=(
        JobHandlerSpec(
            type="story.generate",
            run=run_story_job,
            failure_code="story_job_failed",
            input_model=StoryGenerateInput,
            resource_class=ResourceClass.GPU_LLM,
            timeout_seconds=900,
            submission_policy=_submission_defaults,
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
