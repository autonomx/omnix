from __future__ import annotations

from html import escape
from typing import Any, Dict, List

from app.rpg.quests.journal import build_quest_journal_summary
from app.rpg.quests.persistence import build_quest_persistence_snapshot
from app.rpg.quests.rumors import build_rumor_summary
from app.rpg.quests.state import normalize_quest_state

SOURCE = "deterministic_phase3_quest_report"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def build_phase3_quest_report_model(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    quest_state = normalize_quest_state(_safe_dict(simulation_state).get("quest_state"))
    journal_summary = build_quest_journal_summary(simulation_state)
    rumor_summary = build_rumor_summary(simulation_state)
    persistence_snapshot = build_quest_persistence_snapshot(simulation_state)
    quests = []
    for quest_id, quest in sorted(_safe_dict(quest_state.get("quests")).items()):
        objectives = []
        for objective_id, objective in sorted(_safe_dict(quest.get("objectives")).items()):
            objectives.append(
                {
                    "objective_id": objective_id,
                    "description": _safe_str(objective.get("description")) or objective_id,
                    "status": _safe_str(objective.get("status")) or "open",
                    "progress": objective.get("progress", 0),
                    "required": objective.get("required", 1),
                    "source": _safe_str(objective.get("source")) or "deterministic_quest_objective_lifecycle",
                }
            )
        quests.append(
            {
                "quest_id": quest_id,
                "title": _safe_str(quest.get("title")) or quest_id,
                "status": _safe_str(quest.get("status")) or "active",
                "stage": _safe_str(quest.get("stage")) or "active",
                "reward_claimed": bool(quest.get("reward_claimed")),
                "objectives": objectives,
                "source": _safe_str(quest.get("source")) or "deterministic_quest_state",
            }
        )
    return {
        "source": SOURCE,
        "quests": quests,
        "journal": journal_summary,
        "rumors": rumor_summary,
        "persistence": {
            "source": persistence_snapshot.get("source"),
            "summary": persistence_snapshot.get("summary", {}),
        },
        "summary": {
            "quest_count": len(quests),
            "completed_count": len([row for row in quests if row.get("status") == "completed"]),
            "open_objective_count": sum(1 for quest in quests for objective in quest.get("objectives", []) if objective.get("status") == "open"),
            "journal_entry_count": journal_summary.get("entry_count", 0),
            "rumor_count": rumor_summary.get("rumor_count", 0),
            "reward_log_count": persistence_snapshot.get("summary", {}).get("reward_log_count", 0),
        },
    }


def render_phase3_quest_report_html(simulation_state: Dict[str, Any]) -> str:
    model = build_phase3_quest_report_model(simulation_state)
    rows = ["<section><h2>Phase 3 Quest Report</h2>"]
    summary = _safe_dict(model.get("summary"))
    rows.append(
        "<p>"
        f"Quests: <strong>{escape(str(summary.get('quest_count', 0)))}</strong>; "
        f"Completed: <strong>{escape(str(summary.get('completed_count', 0)))}</strong>; "
        f"Journal entries: <strong>{escape(str(summary.get('journal_entry_count', 0)))}</strong>; "
        f"Rumors: <strong>{escape(str(summary.get('rumor_count', 0)))}</strong>; "
        f"Reward logs: <strong>{escape(str(summary.get('reward_log_count', 0)))}</strong>"
        "</p>"
    )
    rows.append("<table><thead><tr><th>Quest</th><th>Status</th><th>Objectives</th><th>Reward</th></tr></thead><tbody>")
    for quest in _safe_list(model.get("quests")):
        objective_text = "; ".join(
            f"{_safe_str(objective.get('objective_id'))}: {_safe_str(objective.get('status'))}"
            for objective in _safe_list(_safe_dict(quest).get("objectives"))
        )
        rows.append(
            "<tr>"
            f"<td>{escape(_safe_str(_safe_dict(quest).get('quest_id')))}</td>"
            f"<td>{escape(_safe_str(_safe_dict(quest).get('status')))}</td>"
            f"<td>{escape(objective_text)}</td>"
            f"<td>{escape(str(bool(_safe_dict(quest).get('reward_claimed'))))}</td>"
            "</tr>"
        )
    rows.append("</tbody></table>")
    latest_lines = []
    for quest_summary in _safe_list(_safe_dict(model.get("journal")).get("quests")):
        next_step = _safe_str(_safe_dict(quest_summary).get("latest_next_objective"))
        if next_step:
            latest_lines.append(f"{_safe_str(_safe_dict(quest_summary).get('quest_id'))}: {next_step}")
    if latest_lines:
        rows.append("<h3>Latest Next Objectives</h3><ul>")
        for line in latest_lines:
            rows.append(f"<li>{escape(line)}</li>")
        rows.append("</ul>")
    rows.append(f"<p class=\"source\">Source: {SOURCE}</p></section>")
    return "\n".join(rows)


def build_phase3_matrix_scenario_payload(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    model = build_phase3_quest_report_model(simulation_state)
    summary = _safe_dict(model.get("summary"))
    covered = {
        "quest_state": summary.get("quest_count", 0) > 0,
        "objective_state": any(_safe_list(quest.get("objectives")) for quest in _safe_list(model.get("quests"))),
        "journal_state": summary.get("journal_entry_count", 0) > 0,
        "rumor_state": summary.get("rumor_count", 0) > 0,
        "reward_state": summary.get("reward_log_count", 0) > 0,
        "persistence_state": bool(_safe_dict(model.get("persistence")).get("summary")),
    }
    return {
        "source": SOURCE,
        "scenario_id": "phase3_full_quest_lifecycle_matrix",
        "covered": covered,
        "ready": all(covered.values()),
        "report_model": model,
    }
