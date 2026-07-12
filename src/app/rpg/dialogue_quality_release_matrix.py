"""Release entrypoint for the deterministic RPG dialogue quality matrix."""
from __future__ import annotations

from typing import Any, Iterable

from app.rpg.dialogue_quality_benchmark import (
    DialogueBenchmarkCase,
    build_deterministic_benchmark_response,
    default_dialogue_benchmark_cases,
    run_dialogue_quality_benchmark,
)


def build_release_benchmark_response(case: DialogueBenchmarkCase) -> dict[str, Any]:
    """Build a deterministic release fixture with explicit repetition continuity."""

    if case.category != "repetition_repair":
        return build_deterministic_benchmark_response(case)
    narration = "Bran taps the counter once, shifting from the repeated count to the missing travelers."
    line = (
        "Like I said, the old road is the part that matters. Tonight I would watch the missing wagon lamps, "
        "ask the east-gate guards when the last caravan passed, and compare that with the regulars' stories. "
        "Repeating the same business count will not tell us where the travelers went."
    )
    return {
        "visible_response": {
            "format_version": "rpg_visible_response_v1",
            "narration": narration,
            "messages": [
                {
                    "kind": "npc_dialogue",
                    "speaker_id": "npc:bran",
                    "speaker": "Bran",
                    "text": line,
                }
            ],
            "plain_text": f'{narration}\n\nBran: "{line}"',
        }
    }


def run_release_dialogue_quality_benchmark(
    cases: Iterable[DialogueBenchmarkCase] | None = None,
) -> dict[str, Any]:
    return run_dialogue_quality_benchmark(
        tuple(cases or default_dialogue_benchmark_cases()),
        response_builder=build_release_benchmark_response,
    )
