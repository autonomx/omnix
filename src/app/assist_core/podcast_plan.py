from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PodcastSpeakerPlan:
    name: str
    role: str
    goal: str = ""


@dataclass
class PodcastPlan:
    topic: str
    title: str
    outline: list[str] = field(default_factory=list)
    speakers: list[PodcastSpeakerPlan] = field(default_factory=list)
    script_guidance: list[str] = field(default_factory=list)
    handoff: str = "existing_podcast_tts_pipeline"


def build_podcast_plan(topic: str, speakers: list[dict[str, Any]] | None = None, length: str = "medium") -> PodcastPlan:
    clean_topic = (topic or "Untitled episode").strip()
    speaker_rows = speakers or [
        {"name": "Host", "role": "host", "goal": "Guide the discussion clearly."},
        {"name": "Guest", "role": "guest", "goal": "Add examples and contrast."},
    ]
    speaker_plan = [
        PodcastSpeakerPlan(
            name=str(row.get("name") or f"Speaker {index + 1}"),
            role=str(row.get("role") or "speaker"),
            goal=str(row.get("goal") or row.get("instructions") or ""),
        )
        for index, row in enumerate(speaker_rows)
    ]
    return PodcastPlan(
        topic=clean_topic,
        title=f"Podcast: {clean_topic}"[:80],
        outline=[
            "Open with the listener promise.",
            "Frame the topic and stakes.",
            "Develop two or three concrete examples.",
            "Include a short challenge or counterpoint.",
            "Close with a practical takeaway.",
        ],
        speakers=speaker_plan,
        script_guidance=[
            "Return speaker-tagged dialogue for the existing parser.",
            "Keep turns concise and natural.",
            f"Target length profile: {length}.",
        ],
    )


def plan_to_payload(plan: PodcastPlan) -> dict[str, Any]:
    return {
        "topic": plan.topic,
        "title": plan.title,
        "outline": list(plan.outline),
        "speakers": [speaker.__dict__ for speaker in plan.speakers],
        "script_guidance": list(plan.script_guidance),
        "handoff": plan.handoff,
    }
