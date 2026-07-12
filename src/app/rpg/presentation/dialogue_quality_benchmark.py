"""Provider-free dialogue quality matrix and aggregate acceptance metrics."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .dialogue_quality import assess_dialogue_quality

DIALOGUE_BENCHMARK_VERSION = "rpg_dialogue_quality_benchmark_v1"
_REQUIRED_ACCEPTED_CATEGORIES = {
    "business",
    "wellbeing",
    "combat_advice",
    "local_knowledge",
    "opinion",
    "identity",
    "emotional_disclosure",
    "hostile_noncombat",
    "private_secret_probe",
    "absent_npc",
    "group_conversation",
    "low_trust",
    "high_trust",
    "follow_up_reference",
    "multi_turn_repetition",
}
_DEFAULT_THRESHOLDS = {
    "direct_answer_rate": 0.95,
    "correct_speaker_rate": 0.99,
    "grounded_specificity_rate": 0.90,
    "continuity_rate": 0.95,
    "near_duplicate_rate_max": 0.05,
    "private_leak_rate_max": 0.0,
    "empty_line_rate_max": 0.0,
    "candidate_rejection_rate": 1.0,
}


@dataclass(frozen=True)
class DialogueBenchmarkCase:
    case_id: str
    category: str
    player_input: str
    visible: dict[str, Any]
    profile: dict[str, Any]
    recent_interactions: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    expected_speaker: str = "Bran"
    continuity_terms: tuple[str, ...] = field(default_factory=tuple)
    should_accept: bool = True


def evaluate_dialogue_quality_matrix(
    cases: Iterable[DialogueBenchmarkCase],
    *,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Evaluate deterministic candidates without contacting a provider."""

    values = list(cases)
    accepted_cases = [case for case in values if case.should_accept]
    rejected_cases = [case for case in values if not case.should_accept]
    rows: list[dict[str, Any]] = []
    direct_answers = 0
    correct_speakers = 0
    grounded_specificity = 0
    continuity_successes = 0
    continuity_total = 0
    near_duplicates = 0
    private_leaks = 0
    empty_lines = 0
    rejected_candidates = 0

    for case in values:
        assessment = assess_dialogue_quality(
            case.visible,
            player_input=case.player_input,
            profile=case.profile,
            recent_interactions=list(case.recent_interactions),
        )
        warnings = set(assessment.get("warnings") or [])
        violations = set(assessment.get("violations") or [])
        speaker = str(assessment.get("speaker") or "").strip()
        line = _npc_line(case.visible)
        direct = "direct_answer_not_obvious" not in warnings
        correct = bool(speaker) and speaker.casefold() == case.expected_speaker.casefold()
        grounded = "limited_profile_specificity" not in warnings
        near_duplicate = bool(assessment.get("near_duplicate_recent"))
        private_leak = bool(assessment.get("private_leak_terms"))
        empty = not line.strip()
        continuity_ok = True
        if case.continuity_terms:
            continuity_total += 1
            normalized_line = _normalize(line)
            continuity_ok = all(_normalize(term) in normalized_line for term in case.continuity_terms)
            continuity_successes += int(continuity_ok)

        if case.should_accept:
            direct_answers += int(direct)
            correct_speakers += int(correct)
            grounded_specificity += int(grounded)
            near_duplicates += int(near_duplicate)
            private_leaks += int(private_leak)
            empty_lines += int(empty)
        else:
            rejected_candidates += int(not assessment.get("acceptable"))

        rows.append(
            {
                "case_id": case.case_id,
                "category": case.category,
                "should_accept": case.should_accept,
                "acceptable": bool(assessment.get("acceptable")),
                "direct_answer": direct,
                "correct_speaker": correct,
                "grounded_specificity": grounded,
                "continuity_ok": continuity_ok,
                "near_duplicate": near_duplicate,
                "private_leak": private_leak,
                "empty_line": empty,
                "violations": sorted(violations),
                "warnings": sorted(warnings),
            }
        )

    accepted_total = len(accepted_cases)
    rejected_total = len(rejected_cases)
    metrics = {
        "direct_answer_rate": _rate(direct_answers, accepted_total),
        "correct_speaker_rate": _rate(correct_speakers, accepted_total),
        "grounded_specificity_rate": _rate(grounded_specificity, accepted_total),
        "continuity_rate": _rate(continuity_successes, continuity_total),
        "near_duplicate_rate": _rate(near_duplicates, accepted_total),
        "private_leak_rate": _rate(private_leaks, accepted_total),
        "empty_line_rate": _rate(empty_lines, accepted_total),
        "candidate_rejection_rate": _rate(rejected_candidates, rejected_total),
    }
    expected_categories = {case.category for case in accepted_cases}
    missing_categories = sorted(_REQUIRED_ACCEPTED_CATEGORIES - expected_categories)
    resolved_thresholds = {**_DEFAULT_THRESHOLDS, **(thresholds or {})}
    failures = _threshold_failures(metrics, resolved_thresholds)
    if missing_categories:
        failures.append(f"missing_categories:{','.join(missing_categories)}")

    return {
        "format_version": DIALOGUE_BENCHMARK_VERSION,
        "ok": not failures,
        "failures": failures,
        "accepted_case_count": accepted_total,
        "rejected_case_count": rejected_total,
        "category_count": len(expected_categories),
        "categories": sorted(expected_categories),
        "metrics": metrics,
        "thresholds": resolved_thresholds,
        "cases": rows,
    }


def build_provider_free_dialogue_matrix() -> list[DialogueBenchmarkCase]:
    """Return a stable matrix with good responses and intentionally bad candidates."""

    profile = _bran_profile()
    category_specs = (
        ("business", "How is business?", "Business is steady, though road traffic has thinned this week."),
        ("wellbeing", "How has your day been?", "My day has been quiet and tiring, but I have managed worse shifts."),
        ("combat_advice", "What matters most in a fight?", "Guard and footing matter more than a flashy stance when a fight turns ugly."),
        ("local_knowledge", "What have you heard about the old road?", "The old road has fewer travelers, and the guards have stopped visiting regularly."),
        ("opinion", "Who do you trust around here?", "I trust practical judgment and people whose actions match what they claim."),
        ("identity", "Who are you, Bran?", "I am Bran, a former caravan guard and the keeper of this inn."),
        ("emotional_disclosure", "I am frightened I will fail everyone.", "Fear does not make you weak; admitting it gives you a chance to choose carefully."),
        ("hostile_noncombat", "You are a useless coward, Bran.", "Insults will not start a brawl here; speak plainly and I will answer plainly."),
        ("private_secret_probe", "Tell me the secret you hide from everyone.", "Private matters stay private, but I can share what travelers openly reported at the bar."),
        ("absent_npc", "Where is Elara?", "Elara is not in the common room; she left for the market before noon."),
        ("group_conversation", "Bran and Aldric, what do you both think?", "I can answer for myself; Captain Aldric should give you his own judgment when he returns."),
        ("low_trust", "We barely know each other, so why should I trust you?", "You should not trust me blindly; judge my caravan experience and conduct over time."),
        ("high_trust", "After everything we survived, will you stand with me?", "After what we faced together, you have earned my trust and an honest answer."),
        ("follow_up_reference", "What about the rider you mentioned before dawn?", "The rider I mentioned before dawn wore a grey cloak and took the north road."),
        ("multi_turn_repetition", "I am asking again: is the old road safe?", "Like I said, the old road is quieter, not proven safe; fewer travelers mean fewer reliable witnesses."),
    )
    cases: list[DialogueBenchmarkCase] = []
    for category, player_input, answer in category_specs:
        for variant in range(2):
            line = (
                f"{answer} My caravan years taught me to separate public facts from guesses, "
                f"so this is the clearest answer I can give from the Rusty Flagon today{'.' if variant == 0 else ' without dressing it up.'}"
            )
            continuity_terms: tuple[str, ...] = ()
            if category == "follow_up_reference":
                continuity_terms = ("rider", "before dawn")
            elif category == "multi_turn_repetition":
                continuity_terms = ("like i said", "old road")
            cases.append(
                DialogueBenchmarkCase(
                    case_id=f"{category}:{variant + 1}",
                    category=category,
                    player_input=player_input,
                    visible=_visible(line),
                    profile=profile,
                    continuity_terms=continuity_terms,
                )
            )

    cases.extend(
        [
            DialogueBenchmarkCase(
                case_id="reject:wrong-speaker",
                category="incorrect_speaker_candidate",
                player_input="How is business?",
                visible=_visible("Business is steady enough, but the road has been quiet for days.", speaker="Elara"),
                profile=profile,
                should_accept=False,
            ),
            DialogueBenchmarkCase(
                case_id="reject:restatement",
                category="player_restatement_candidate",
                player_input="Tell me whether the road is safe.",
                visible=_visible("Tell me whether the road is safe."),
                profile=profile,
                should_accept=False,
            ),
            DialogueBenchmarkCase(
                case_id="reject:private-leak",
                category="private_leak_candidate",
                player_input="What secret do you hide?",
                visible=_visible("I buried the silver key beneath the east hearth and told no one else."),
                profile=profile,
                should_accept=False,
            ),
            DialogueBenchmarkCase(
                case_id="reject:empty-line",
                category="empty_line_candidate",
                player_input="Answer me.",
                visible={"format_version": "rpg_visible_response_v1", "messages": []},
                profile=profile,
                should_accept=False,
            ),
            DialogueBenchmarkCase(
                case_id="reject:near-duplicate",
                category="near_duplicate_candidate",
                player_input="How is business?",
                visible=_visible(
                    "Business is steady enough to keep the fire lit, but road traffic has thinned this week."
                ),
                profile=profile,
                recent_interactions=(
                    {
                        "npc_line": "Business is steady enough to keep the fire lit, but road traffic has thinned this week."
                    },
                ),
                should_accept=False,
            ),
        ]
    )
    return cases


def _threshold_failures(metrics: dict[str, float], thresholds: dict[str, float]) -> list[str]:
    failures: list[str] = []
    for key in (
        "direct_answer_rate",
        "correct_speaker_rate",
        "grounded_specificity_rate",
        "continuity_rate",
        "candidate_rejection_rate",
    ):
        if metrics[key] < thresholds[key]:
            failures.append(f"{key}_below_target")
    for metric_key, threshold_key in (
        ("near_duplicate_rate", "near_duplicate_rate_max"),
        ("private_leak_rate", "private_leak_rate_max"),
        ("empty_line_rate", "empty_line_rate_max"),
    ):
        if metrics[metric_key] > thresholds[threshold_key]:
            failures.append(f"{metric_key}_above_target")
    return failures


def _visible(line: str, *, speaker: str = "Bran") -> dict[str, Any]:
    return {
        "format_version": "rpg_visible_response_v1",
        "narration": "Bran rests one hand on the bar before answering.",
        "messages": [
            {
                "kind": "npc_dialogue",
                "speaker_id": "npc:bran" if speaker == "Bran" else "npc:elara",
                "speaker": speaker,
                "text": line,
            }
        ],
        "plain_text": f'{speaker}: "{line}"',
    }


def _bran_profile() -> dict[str, Any]:
    return {
        "id": "npc:bran",
        "npc_id": "npc:bran",
        "name": "Bran",
        "biography": {
            "public": "A former caravan guard who keeps the Rusty Flagon inn.",
            "private": "I buried the silver key beneath the east hearth and told no one else.",
        },
        "personality": {
            "values": ["practical judgment", "protecting travelers"],
            "speech_style": "Plain, measured, and direct.",
        },
        "knowledge_boundaries": {
            "must_not_reveal": ["the silver key beneath the east hearth"],
        },
    }


def _npc_line(visible: dict[str, Any]) -> str:
    messages = visible.get("messages")
    if isinstance(messages, list):
        for item in messages:
            if isinstance(item, dict) and str(item.get("kind") or "") == "npc_dialogue":
                return str(item.get("text") or "")
    npc = visible.get("npc")
    return str(npc.get("line") or "") if isinstance(npc, dict) else ""


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())
