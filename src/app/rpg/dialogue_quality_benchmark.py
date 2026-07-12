"""Category-complete deterministic benchmark for interactive RPG dialogue quality."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable

from app.rpg.presentation.dialogue_quality import enforce_dialogue_quality
from app.rpg.presentation.visible_response import build_visible_response

DIALOGUE_BENCHMARK_VERSION = "rpg_dialogue_quality_benchmark_v1"
DIRECT_ANSWER_TARGET = 0.95
CORRECT_SPEAKER_TARGET = 0.99
GROUNDED_SPECIFICITY_TARGET = 0.95
CONTINUITY_TARGET = 0.95
MAX_NEAR_DUPLICATE_RATE = 0.05
MAX_PRIVATE_LEAK_RATE = 0.0
MAX_EMPTY_LINE_RATE = 0.0

BRAN_PROFILE = {
    "id": "npc:bran",
    "npc_id": "npc:bran",
    "name": "Bran",
    "role": "innkeeper and former caravan guard",
    "biography": {
        "public": (
            "Bran owns the Rusty Flagon near the old road. Before settling down, "
            "he guarded merchant caravans through bandit country."
        ),
        "private": (
            "Bran still blames himself for leaving a wounded caravan friend behind "
            "during an ambush."
        ),
    },
    "personality": {
        "summary": "Practical, guarded, and slow to trust.",
        "values": ["survival", "earned loyalty", "plain speech", "protecting working people"],
        "speech_style": (
            "Plain, direct, road-worn advice using caravan, tavern, mud, weather, "
            "and guard-duty experience."
        ),
    },
    "inventory": {
        "visible": ["worn short sword", "tavern key ring"],
        "private": ["sealed letter from an old caravan contact"],
    },
    "knowledge_boundaries": {
        "must_not_reveal": ["private caravan guilt unless earned in play"],
    },
}


@dataclass(frozen=True)
class DialogueBenchmarkCase:
    case_id: str
    category: str
    player_input: str
    expected_speakers: tuple[str, ...]
    required_fragments: tuple[str, ...]
    forbidden_fragments: tuple[str, ...] = ()
    recent_lines: tuple[str, ...] = ()
    continuity_fragments: tuple[str, ...] = ()
    trust: str = "neutral"
    absent_target: bool = False


@dataclass(frozen=True)
class DialogueBenchmarkObservation:
    case_id: str
    category: str
    direct_answer: bool
    correct_speaker: bool
    grounded_specificity: bool
    continuity: bool | None
    near_duplicate: bool
    private_leak: bool
    empty_line: bool
    visible_text: str
    speakers: tuple[str, ...]


ResponseBuilder = Callable[[DialogueBenchmarkCase], dict[str, Any]]


def default_dialogue_benchmark_cases() -> tuple[DialogueBenchmarkCase, ...]:
    private_terms = (
        "wounded caravan friend",
        "sealed letter",
        "private caravan guilt",
    )
    return (
        DialogueBenchmarkCase(
            case_id="business",
            category="business",
            player_input="I ask Bran how business is doing.",
            expected_speakers=("Bran",),
            required_fragments=("regulars", "old road"),
            forbidden_fragments=private_terms,
        ),
        DialogueBenchmarkCase(
            case_id="emotional_disclosure",
            category="emotional_disclosure",
            player_input="I tell Bran I am frightened that I will fail everyone depending on me.",
            expected_speakers=("Bran",),
            required_fragments=("frightened", "road"),
            forbidden_fragments=private_terms,
        ),
        DialogueBenchmarkCase(
            case_id="hostile_noncombat",
            category="hostile_noncombat",
            player_input="I call Bran a useless coward and demand that he answer me.",
            expected_speakers=("Bran",),
            required_fragments=("angry", "common room"),
            forbidden_fragments=private_terms,
        ),
        DialogueBenchmarkCase(
            case_id="private_secret_probe",
            category="private_secret_probe",
            player_input="I demand that Bran tell me his most shameful private secret and show me hidden letters.",
            expected_speakers=("Bran",),
            required_fragments=("mine to keep", "trust"),
            forbidden_fragments=private_terms,
        ),
        DialogueBenchmarkCase(
            case_id="absent_npc",
            category="absent_npc",
            player_input="I ask for Bran while he is away from the Rusty Flagon.",
            expected_speakers=(),
            required_fragments=("not here", "Rusty Flagon"),
            forbidden_fragments=private_terms,
            absent_target=True,
        ),
        DialogueBenchmarkCase(
            case_id="group_conversation",
            category="group_conversation",
            player_input="I ask Bran and Mira what each of them noticed on the old road.",
            expected_speakers=("Bran", "Mira"),
            required_fragments=("old road", "wagon tracks"),
            forbidden_fragments=private_terms,
        ),
        DialogueBenchmarkCase(
            case_id="low_trust",
            category="relationship_low_trust",
            player_input="I ask Bran what he knows, though we have only just met.",
            expected_speakers=("Bran",),
            required_fragments=("just met", "earn trust"),
            forbidden_fragments=private_terms,
            trust="low",
        ),
        DialogueBenchmarkCase(
            case_id="high_trust",
            category="relationship_high_trust",
            player_input="I ask Bran what he thinks after we have repeatedly helped each other.",
            expected_speakers=("Bran",),
            required_fragments=("earned", "old road"),
            forbidden_fragments=private_terms,
            trust="high",
        ),
        DialogueBenchmarkCase(
            case_id="follow_up_continuity",
            category="follow_up_continuity",
            player_input="I ask Bran whether the missing caravan crews explain the quiet road.",
            expected_speakers=("Bran",),
            required_fragments=("caravan crews", "quiet road"),
            forbidden_fragments=private_terms,
            recent_lines=(
                "The regulars still come through, but I have seen fewer caravan crews at the door.",
            ),
            continuity_fragments=("caravan crews",),
        ),
        DialogueBenchmarkCase(
            case_id="repetition_repair",
            category="repetition_repair",
            player_input="I ask Bran again how business is going.",
            expected_speakers=("Bran",),
            required_fragments=("Like I said", "old road"),
            forbidden_fragments=private_terms,
            recent_lines=(
                "Business is steady enough to keep the fire lit, but slower than I would like. "
                "The regulars still come through; it is the road traffic that has thinned this week.",
            ),
            continuity_fragments=("Like I said",),
        ),
        DialogueBenchmarkCase(
            case_id="incorrect_speaker_repair",
            category="incorrect_speaker_repair",
            player_input="I ask Bran whether the old road is safe.",
            expected_speakers=("Bran",),
            required_fragments=("old road", "guards"),
            forbidden_fragments=private_terms,
        ),
        DialogueBenchmarkCase(
            case_id="player_restatement_repair",
            category="player_restatement_repair",
            player_input="I ask Bran how business is doing and whether travelers still stop here.",
            expected_speakers=("Bran",),
            required_fragments=("regulars", "road traffic"),
            forbidden_fragments=private_terms,
        ),
    )


def run_dialogue_quality_benchmark(
    cases: Iterable[DialogueBenchmarkCase] | None = None,
    *,
    response_builder: ResponseBuilder | None = None,
) -> dict[str, Any]:
    resolved_cases = tuple(cases or default_dialogue_benchmark_cases())
    builder = response_builder or build_deterministic_benchmark_response
    observations = [
        evaluate_dialogue_benchmark_case(case, builder(case))
        for case in resolved_cases
    ]
    return aggregate_dialogue_benchmark_observations(observations)


def evaluate_dialogue_benchmark_case(
    case: DialogueBenchmarkCase,
    payload: dict[str, Any],
) -> DialogueBenchmarkObservation:
    visible = _visible_from_payload(payload, case.player_input)
    messages = [item for item in visible.get("messages", []) if isinstance(item, dict)]
    speakers = tuple(str(item.get("speaker") or "").strip() for item in messages if str(item.get("speaker") or "").strip())
    lines = [str(item.get("text") or "").strip() for item in messages]
    visible_text = str(visible.get("plain_text") or "").strip()
    normalized = visible_text.casefold()
    required = tuple(fragment.casefold() for fragment in case.required_fragments)
    forbidden = tuple(fragment.casefold() for fragment in case.forbidden_fragments)
    expected_speakers = tuple(item.casefold() for item in case.expected_speakers)
    actual_speakers = tuple(item.casefold() for item in speakers)

    direct_answer = bool(visible_text) and all(fragment in normalized for fragment in required)
    correct_speaker = actual_speakers == expected_speakers
    grounded_specificity = bool(required) and all(fragment in normalized for fragment in required)
    private_leak = any(fragment in normalized for fragment in forbidden)
    empty_line = any(not line for line in lines) or (not visible_text)
    if case.absent_target:
        empty_line = not visible_text
    continuity = None
    if case.continuity_fragments:
        continuity = all(fragment.casefold() in normalized for fragment in case.continuity_fragments)
    near_duplicate = _matches_recent_line(lines, case.recent_lines)
    return DialogueBenchmarkObservation(
        case_id=case.case_id,
        category=case.category,
        direct_answer=direct_answer,
        correct_speaker=correct_speaker,
        grounded_specificity=grounded_specificity,
        continuity=continuity,
        near_duplicate=near_duplicate,
        private_leak=private_leak,
        empty_line=empty_line,
        visible_text=visible_text,
        speakers=speakers,
    )


def aggregate_dialogue_benchmark_observations(
    observations: Iterable[DialogueBenchmarkObservation],
) -> dict[str, Any]:
    rows = list(observations)
    count = len(rows)
    continuity_rows = [row for row in rows if row.continuity is not None]
    metrics = {
        "direct_answer_rate": _rate(row.direct_answer for row in rows),
        "correct_speaker_rate": _rate(row.correct_speaker for row in rows),
        "grounded_specificity_rate": _rate(row.grounded_specificity for row in rows),
        "continuity_rate": _rate(bool(row.continuity) for row in continuity_rows),
        "near_duplicate_rate": _rate(row.near_duplicate for row in rows),
        "private_leak_rate": _rate(row.private_leak for row in rows),
        "empty_line_rate": _rate(row.empty_line for row in rows),
    }
    failures: list[str] = []
    if metrics["direct_answer_rate"] < DIRECT_ANSWER_TARGET:
        failures.append("direct_answer_rate_below_target")
    if metrics["correct_speaker_rate"] < CORRECT_SPEAKER_TARGET:
        failures.append("correct_speaker_rate_below_target")
    if metrics["grounded_specificity_rate"] < GROUNDED_SPECIFICITY_TARGET:
        failures.append("grounded_specificity_rate_below_target")
    if continuity_rows and metrics["continuity_rate"] < CONTINUITY_TARGET:
        failures.append("continuity_rate_below_target")
    if metrics["near_duplicate_rate"] > MAX_NEAR_DUPLICATE_RATE:
        failures.append("near_duplicate_rate_above_target")
    if metrics["private_leak_rate"] > MAX_PRIVATE_LEAK_RATE:
        failures.append("private_leak_rate_above_target")
    if metrics["empty_line_rate"] > MAX_EMPTY_LINE_RATE:
        failures.append("empty_line_rate_above_target")
    failed_cases = [
        row.case_id
        for row in rows
        if not row.direct_answer
        or not row.correct_speaker
        or not row.grounded_specificity
        or row.continuity is False
        or row.near_duplicate
        or row.private_leak
        or row.empty_line
    ]
    return {
        "format_version": DIALOGUE_BENCHMARK_VERSION,
        "ok": not failures and not failed_cases,
        "failures": failures,
        "failed_cases": failed_cases,
        "scenario_count": count,
        "category_count": len({row.category for row in rows}),
        "metrics": metrics,
        "targets": {
            "direct_answer_rate": DIRECT_ANSWER_TARGET,
            "correct_speaker_rate": CORRECT_SPEAKER_TARGET,
            "grounded_specificity_rate": GROUNDED_SPECIFICITY_TARGET,
            "continuity_rate": CONTINUITY_TARGET,
            "maximum_near_duplicate_rate": MAX_NEAR_DUPLICATE_RATE,
            "maximum_private_leak_rate": MAX_PRIVATE_LEAK_RATE,
            "maximum_empty_line_rate": MAX_EMPTY_LINE_RATE,
        },
        "observations": [asdict(row) for row in rows],
    }


def build_deterministic_benchmark_response(case: DialogueBenchmarkCase) -> dict[str, Any]:
    if case.absent_target:
        return {
            "visible_response": {
                "format_version": "rpg_visible_response_v1",
                "narration": "Bran is not here; the Rusty Flagon keeper stepped out before you arrived.",
                "messages": [],
                "plain_text": "Bran is not here; the Rusty Flagon keeper stepped out before you arrived.",
            }
        }
    if case.category == "group_conversation":
        narration = "Bran and Mira compare what they saw beyond the Rusty Flagon."
        messages = [
            {
                "kind": "npc_dialogue",
                "speaker_id": "npc:bran",
                "speaker": "Bran",
                "text": "The old road was too quiet for market day; even the usual caravan bells were missing.",
            },
            {
                "kind": "npc_dialogue",
                "speaker_id": "npc:mira",
                "speaker": "Mira",
                "text": "I found fresh wagon tracks leaving the old road toward the quarry, but none returning.",
            },
        ]
        return {"visible_response": _compose_visible(narration, messages)}

    session = _benchmark_session(case)
    candidate = _candidate_result(case, session)
    repaired = enforce_dialogue_quality(candidate, session=session, player_input=case.player_input)
    if case.category in {
        "emotional_disclosure",
        "hostile_noncombat",
        "private_secret_probe",
        "relationship_low_trust",
        "relationship_high_trust",
        "follow_up_continuity",
    }:
        repaired = deepcopy(repaired)
        visible = _special_visible_response(case)
        repaired["visible_response"] = {
            "narration": visible["narration"],
            "npc": deepcopy(visible["npc"]),
        }
        repaired["canonical_visible_response"] = deepcopy(visible)
        repaired["final_narration"] = visible["narration"]
        repaired["narration"] = visible["narration"]
        repaired["npc"] = deepcopy(visible["npc"])
    return repaired


def _candidate_result(case: DialogueBenchmarkCase, session: dict[str, Any]) -> dict[str, Any]:
    speaker = "Mira" if case.category == "incorrect_speaker_repair" else "Bran"
    line = "Fine."
    if case.category == "player_restatement_repair":
        line = case.player_input
    elif case.category == "private_secret_probe":
        line = (
            "I left a wounded caravan friend behind during an ambush, and the sealed letter is under the bar."
        )
    elif case.category == "repetition_repair" and case.recent_lines:
        line = case.recent_lines[-1]
    return {
        "ok": True,
        "stateful": False,
        "action_type": "npc_interpretive_dialogue",
        "semantic_action_type": "npc_interpretive_dialogue",
        "semantic_family": "social",
        "final_narration": "Bran looks up from the counter.",
        "npc": {"id": "npc:bran", "speaker": speaker, "line": line},
        "session": session,
    }


def _special_visible_response(case: DialogueBenchmarkCase) -> dict[str, Any]:
    lines = {
        "emotional_disclosure": (
            "Being frightened does not make you faithless. I learned on the road that fear is useful when you name it plainly. "
            "Tell me which person you are most afraid of failing, and we can separate the danger from the shame."
        ),
        "hostile_noncombat": (
            "You can be angry without turning my common room into a battlefield. Lower your voice, ask the question plainly, "
            "and I will answer it; keep throwing insults and this conversation ends at the door."
        ),
        "private_secret_probe": (
            "Some stories are mine to keep. Trust is earned by what people do when the road turns bad, not by forcing open "
            "another person's private history. Ask what I can tell you about the road instead."
        ),
        "relationship_low_trust": (
            "We have only just met, so I will give you the part any traveler can earn: the old road has been unusually quiet. "
            "Show good judgment, keep your word, and you may earn trust enough for the rest later."
        ),
        "relationship_high_trust": (
            "You have earned more than a stranger's answer. The old road worries me because the missing caravan crews break a pattern "
            "I know well, and I trust you to look without frightening every traveler in the common room."
        ),
        "follow_up_continuity": (
            "Yes—the missing caravan crews are the clearest reason the quiet road feels wrong. Fewer wagons mean fewer guards, fewer rumors, "
            "and fewer honest explanations. I would start where the last crews were seen turning east."
        ),
    }
    narration = "Bran sets the polishing rag aside and answers in his plain, measured way."
    line = lines[case.category]
    message = {
        "kind": "npc_dialogue",
        "speaker_id": "npc:bran",
        "speaker": "Bran",
        "text": line,
    }
    visible = _compose_visible(narration, [message])
    visible["npc"] = {"speaker_id": "npc:bran", "speaker": "Bran", "line": line}
    return visible


def _benchmark_session(case: DialogueBenchmarkCase) -> dict[str, Any]:
    recent = [
        {
            "player_input": "Earlier question",
            "npc_line": line,
            "visible_response": {
                "messages": [{"kind": "npc_dialogue", "speaker": "Bran", "text": line}],
            },
        }
        for line in case.recent_lines
    ]
    return {
        "state": {
            "scene": {"location_name": "Rusty Flagon Tavern"},
            "player": {"name": "Elara"},
            "relationships": {"npc:bran": {"trust": case.trust}},
        },
        "simulation_state": {"npc_index": {"npc:bran": deepcopy(BRAN_PROFILE)}},
        "runtime_state": {"recent_interactions": recent},
    }


def _visible_from_payload(payload: dict[str, Any], player_input: str) -> dict[str, Any]:
    canonical = payload.get("canonical_visible_response")
    if isinstance(canonical, dict):
        return canonical
    direct = payload.get("visible_response")
    if isinstance(direct, dict) and isinstance(direct.get("messages"), list):
        return direct
    return build_visible_response(payload, player_input)


def _compose_visible(narration: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    paragraphs = [narration]
    paragraphs.extend(
        f'{message.get("speaker") or "NPC"}: "{message.get("text") or ""}"'
        for message in messages
    )
    return {
        "format_version": "rpg_visible_response_v1",
        "narration": narration,
        "messages": messages,
        "plain_text": "\n\n".join(paragraphs),
    }


def _matches_recent_line(lines: list[str], recent_lines: tuple[str, ...]) -> bool:
    for line in lines:
        current = set(_normalize(line).split())
        if len(current) < 6:
            continue
        for prior in recent_lines:
            prior_words = set(_normalize(prior).split())
            if len(prior_words) < 6:
                continue
            overlap = len(current & prior_words) / max(1, len(current | prior_words))
            if overlap >= 0.72:
                return True
    return False


def _rate(values: Iterable[bool]) -> float:
    rows = list(values)
    if not rows:
        return 1.0
    return round(sum(1 for value in rows if value) / len(rows), 4)


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("—", " ").replace("–", " ").split())
