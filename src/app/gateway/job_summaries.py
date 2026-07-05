"""Bounded job projections for browser list views.

Job details may contain multi-megabyte inline media payloads. List views only need
metadata, so this module recursively replaces large strings with size markers.
The full job remains available through ``GET /api/jobs/{job_id}``.
"""
from __future__ import annotations

from typing import Any

from app.jobs import JobRecord

MAX_SUMMARY_STRING_CHARS = 2_048
MAX_VOICE_INLINE_AUDIO_CHARS = 12_000_000
MAX_VOICE_INLINE_OUTPUT_JOBS = 2
INLINE_PAYLOAD_KEYS = {
    "audio",
    "audio_base64",
    "data_url",
    "image_base64",
    "sample_audio_base64",
    "video_base64",
}


def summarize_job(job: JobRecord, *, keep_output_refs: bool = False) -> JobRecord:
    """Return a browser-safe job projection with optional bounded playback data."""
    return job.model_copy(
        update={
            "input_payload": summarize_value(job.input_payload),
            "output_refs": job.output_refs if keep_output_refs else [summarize_mapping(ref) for ref in job.output_refs],
            "logs": [summarize_mapping(log) for log in job.logs[-20:]],
            "stages": [
                stage.model_copy(
                    update={
                        "checkpoint_ref": summarize_value(stage.checkpoint_ref),
                        "output_refs": [summarize_mapping(ref) for ref in stage.output_refs],
                    }
                )
                for stage in job.stages
            ],
        }
    )


def voice_job_projections(jobs: list[JobRecord]) -> list[JobRecord]:
    """Keep only a small recent inline-audio window for the Voice Studio list."""
    projected: list[JobRecord] = []
    remaining_chars = MAX_VOICE_INLINE_AUDIO_CHARS
    retained_output_jobs = 0
    for job in jobs:
        inline_chars = inline_payload_chars(job.output_refs)
        keep_output_refs = bool(
            inline_chars
            and retained_output_jobs < MAX_VOICE_INLINE_OUTPUT_JOBS
            and inline_chars <= remaining_chars
        )
        projected.append(summarize_job(job, keep_output_refs=keep_output_refs))
        if keep_output_refs:
            retained_output_jobs += 1
            remaining_chars -= inline_chars
    return projected


def inline_payload_chars(value: Any) -> int:
    if isinstance(value, dict):
        return sum(
            len(item) if isinstance(item, str) and _should_omit_string(key, item) else inline_payload_chars(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return sum(inline_payload_chars(item) for item in value)
    return 0


def summarize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return summarize_mapping(value)
    if isinstance(value, list):
        return [summarize_value(item) for item in value]
    if isinstance(value, tuple):
        return [summarize_value(item) for item in value]
    if isinstance(value, str) and len(value) > MAX_SUMMARY_STRING_CHARS:
        return _omitted_string_marker(value)
    return value


def summarize_mapping(value: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, str) and _should_omit_string(key, item):
            summary[f"{key}_omitted"] = True
            summary[f"{key}_chars"] = len(item)
            summary[f"{key}_bytes_estimate"] = _decoded_bytes_estimate(item)
            continue
        summary[key] = summarize_value(item)
    return summary


def _should_omit_string(key: str, value: str) -> bool:
    normalized_key = key.lower()
    return (
        normalized_key in INLINE_PAYLOAD_KEYS
        or normalized_key.endswith("_base64")
        or value.startswith("data:")
        or len(value) > MAX_SUMMARY_STRING_CHARS
    )


def _omitted_string_marker(value: str) -> dict[str, Any]:
    return {
        "omitted": True,
        "chars": len(value),
        "bytes_estimate": _decoded_bytes_estimate(value),
    }


def _decoded_bytes_estimate(value: str) -> int:
    payload = value.split(",", 1)[1] if value.startswith("data:") and "," in value else value
    return max(0, len(payload) * 3 // 4)
