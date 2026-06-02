"""Deterministic RPG quest state machine helpers."""

from app.rpg.quests.conditions import evaluate_quest_condition
from app.rpg.quests.journal import (
    add_journal_entry,
    add_journal_entry_from_objective_result,
    build_quest_journal_summary,
    ensure_journal_state,
    render_quest_journal_report_html,
)
from app.rpg.quests.objectives import (
    complete_objective_lifecycle,
    create_objective,
    derive_quest_lifecycle,
    fail_objective,
    objective_from_template,
    update_objective_progress,
)
from app.rpg.quests.rewards import build_reward_payload, claim_quest_rewards, mark_reward_claimed
from app.rpg.quests.rumors import (
    back_rumor_with_evidence,
    build_rumor_summary,
    convert_rumor_to_quest_offer,
    ensure_rumor_state,
    propagate_backed_rumors,
    register_rumor,
)
from app.rpg.quests.state import (
    complete_objective,
    ensure_quest_state,
    get_quest,
    normalize_quest_state,
    set_quest_stage,
    start_quest,
)
from app.rpg.quests.transitions import apply_quest_transition
from app.rpg.quests.work import (
    build_work_inquiry_narration_contract,
    classify_work_inquiry,
    route_work_inquiry,
    suggest_objectives,
)

__all__ = [
    "add_journal_entry",
    "add_journal_entry_from_objective_result",
    "apply_quest_transition",
    "back_rumor_with_evidence",
    "build_quest_journal_summary",
    "build_reward_payload",
    "build_rumor_summary",
    "build_work_inquiry_narration_contract",
    "claim_quest_rewards",
    "classify_work_inquiry",
    "complete_objective",
    "complete_objective_lifecycle",
    "convert_rumor_to_quest_offer",
    "create_objective",
    "derive_quest_lifecycle",
    "ensure_journal_state",
    "ensure_quest_state",
    "ensure_rumor_state",
    "evaluate_quest_condition",
    "fail_objective",
    "get_quest",
    "mark_reward_claimed",
    "normalize_quest_state",
    "objective_from_template",
    "propagate_backed_rumors",
    "register_rumor",
    "render_quest_journal_report_html",
    "route_work_inquiry",
    "set_quest_stage",
    "start_quest",
    "suggest_objectives",
    "update_objective_progress",
]
