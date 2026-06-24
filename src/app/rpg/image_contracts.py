"""Grounded image prompt contracts and non-blocking queue helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Mapping, Sequence

ImageKind = Literal["portrait", "scene", "combat", "quest_beat", "faction_event"]
ImageJobStatus = Literal["queued", "running", "completed", "failed"]


@dataclass(frozen=True)
class ImagePromptFacts:
    location_id: str
    time_of_day: str = "unknown"
    weather: str = "unknown"
    mood: str = "neutral"
    npc_ids: tuple[str, ...] = ()
    object_ids: tuple[str, ...] = ()
    style_tags: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "location_id": self.location_id,
            "time_of_day": self.time_of_day,
            "weather": self.weather,
            "mood": self.mood,
            "npc_ids": list(self.npc_ids),
            "object_ids": list(self.object_ids),
            "style_tags": list(self.style_tags),
        }


@dataclass(frozen=True)
class ImagePromptContract:
    job_id: str
    kind: ImageKind
    facts: ImagePromptFacts
    prompt: str
    blocking: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "facts": self.facts.as_dict(),
            "prompt": self.prompt,
            "blocking": self.blocking,
        }


@dataclass(frozen=True)
class ImageJob:
    contract: ImagePromptContract
    status: ImageJobStatus = "queued"
    result_asset_id: str | None = None
    error: str = ""

    def as_dict(self) -> dict[str, object]:
        return {**self.contract.as_dict(), "status": self.status, "result_asset_id": self.result_asset_id, "error": self.error}


@dataclass(frozen=True)
class ImageQueueState:
    jobs: Mapping[str, ImageJob]

    def enqueue(self, contract: ImagePromptContract) -> "ImageQueueState":
        updated = dict(self.jobs)
        updated[contract.job_id] = ImageJob(contract)
        return ImageQueueState(updated)

    def mark(self, job_id: str, status: ImageJobStatus, *, result_asset_id: str | None = None, error: str = "") -> "ImageQueueState":
        job = self.jobs[job_id]
        updated = dict(self.jobs)
        updated[job_id] = replace(job, status=status, result_asset_id=result_asset_id, error=error)
        return ImageQueueState(updated)

    def pending_jobs(self) -> tuple[ImageJob, ...]:
        return tuple(job for job in self.jobs.values() if job.status in ("queued", "running"))


def build_image_prompt_contract(job_id: str, kind: ImageKind, facts: ImagePromptFacts) -> ImagePromptContract:
    prompt = _prompt_from_facts(kind, facts)
    return ImagePromptContract(job_id, kind, facts, prompt, blocking=False)


def _prompt_from_facts(kind: ImageKind, facts: ImagePromptFacts) -> str:
    parts = [f"{kind} image", f"location:{facts.location_id}"]
    if facts.npc_ids:
        parts.append("npcs:" + ",".join(facts.npc_ids))
    if facts.object_ids:
        parts.append("objects:" + ",".join(facts.object_ids))
    parts.extend([f"time:{facts.time_of_day}", f"weather:{facts.weather}", f"mood:{facts.mood}"])
    if facts.style_tags:
        parts.append("style:" + ",".join(facts.style_tags))
    return "; ".join(parts)


def validate_image_contract(contract: ImagePromptContract) -> tuple[str, ...]:
    issues: list[str] = []
    if contract.blocking:
        issues.append("image_job_must_not_block_turn")
    if not contract.facts.location_id:
        issues.append("missing_location")
    if "unknown npc" in contract.prompt.lower():
        issues.append("unsupported_npc_reference")
    return tuple(issues)


def image_queue_report(queue: ImageQueueState) -> dict[str, object]:
    return {
        "job_count": len(queue.jobs),
        "pending_count": len(queue.pending_jobs()),
        "jobs": [job.as_dict() for job in sorted(queue.jobs.values(), key=lambda item: item.contract.job_id)],
    }


def empty_image_queue() -> ImageQueueState:
    return ImageQueueState({})
