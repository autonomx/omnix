"""Story and podcast feature declaration."""
from __future__ import annotations

from app.jobs.handlers import JobExecutionContext, JobHandlerSpec
from app.jobs.models import ResourceClass
from app.runtime.features import FeatureModule

from .jobs import PodcastGenerateInput, StoryGenerateInput, execute_story_job


def _execute(context: JobExecutionContext, job):
    return execute_story_job(context.job_store, job)


FEATURE = FeatureModule(
    id="story",
    title="Storyteller and Podcast",
    job_handlers=(
        JobHandlerSpec(
            type="story.generate",
            handler=_execute,
            input_model=StoryGenerateInput,
            resource_class=ResourceClass.GPU_LLM,
            timeout_seconds=900,
        ),
        JobHandlerSpec(
            type="podcast.generate",
            handler=_execute,
            input_model=PodcastGenerateInput,
            resource_class=ResourceClass.GPU_LLM,
            timeout_seconds=900,
        ),
    ),
)
