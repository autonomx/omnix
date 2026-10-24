"""Dialogue on the pipeline (RQ-2.2; docs/rpg/design/dialogue.md): the plan decides, one model call phrases the line.

``resolve_dialogue`` builds the speaker's ``DialoguePlan`` (``rules/dialogue/plan.py``), has the model write the line
from it, checks the line against the plan (no secret said), and falls back to the plan's own line when the model
cannot write one. The plan's changes (what is now known, a quest offered) and the exchange are the turn's changes.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state.changes import DialogueExchanged, StateChange
from app.apps.rpg.rules.dialogue.plan import DialoguePlan, build_plan, line_keeps_the_plan, plan_changes
from app.prompts import prompt_template

logger = logging.getLogger(__name__)
_LINE_PROMPT = prompt_template(
    "rpg.ai_compact_dialogue.plan", "1",
    "Reply as the speaker in the PLAN, in one or two concise spoken sentences, in their voice and stance. Output "
    "only the words they say: no name label, narration, JSON or markdown. Share what may_reveal holds, offer what "
    "offers_quest or offers_to_tell_for_a_price hold, and name each of wares with its price as written; about anything else, answer from their role and "
    "background or say they do not know. Never say or hint at anything in must_never_reveal. Keep continuity with "
    "recent_exchanges without repeating them.\nPLAYER: {v0}\nPLAN: ",
)
MAX_LINE = 400


@dataclass(frozen=True)
class DialogueResolution:
    changes: list[StateChange]
    lines: list[str]  # what the narrator is told
    speaker_id: str
    speaker_name: str
    line: str
    written_by_model: bool


def _clean(raw: Any, speaker: str) -> str:
    line = _s(raw).strip().strip('"').strip()
    line = re.sub(rf"^\s*{re.escape(speaker)}\s*:\s*", "", line, flags=re.IGNORECASE).strip().strip('"')
    return line[:MAX_LINE]


def _write_line(plan: DialoguePlan, exchanges: list[dict[str, Any]], text: str) -> str:
    from app.apps.rpg.foundation.llm_app_gateway import build_app_llm_gateway

    gateway = build_app_llm_gateway()
    if gateway is None:
        return ""
    context = {**plan.context(), "recent_exchanges": exchanges[-3:]}
    prompt = _LINE_PROMPT.format(v0=text[:500]) + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    try:
        raw = gateway.generate(prompt, provider_options={"temperature": 0.55, "max_tokens": 90,
                                                         "chat_template_kwargs": {"enable_thinking": False}})
    except Exception:
        logger.warning("rpg_dialogue_line_failed speaker=%s", plan.speaker_id, exc_info=True)
        return ""
    return _s(raw)


def _speaker(simulation: Mapping[str, Any], runtime: Mapping[str, Any], target_id: str) -> str:
    present = set(_l(_d(simulation.get("present_npc_state")).get("present_npc_ids")))
    if target_id and target_id in present:
        return target_id
    focus = _s(_d(runtime.get("dialogue_focus")).get("target_id"))
    return focus if not target_id and focus in present else ""


def resolve_dialogue(session: Mapping[str, Any], target_id: str, text: str) -> DialogueResolution | None:
    """The answer of the person spoken to; ``None`` when no one present is clearly spoken to (the older path's)."""
    simulation = _d(session.get("simulation_state"))
    speaker_id = _speaker(simulation, _d(session.get("runtime_state")), target_id)
    plan = build_plan(simulation, speaker_id, text) if speaker_id else None
    if plan is None:
        return None
    exchanges = [_d(row) for row in _l(_d(_d(simulation.get("dialogue")).get("exchanges")).get(speaker_id))]
    written = _clean(_write_line(plan, exchanges, text), plan.speaker_name)
    keeps = bool(written) and line_keeps_the_plan(plan, written)
    line = written if keeps else plan.fallback_line()
    told = [f"{plan.speaker_name} answers ({plan.stance})."]
    if plan.reveals:
        told.append(f"They share: {' '.join(plan.reveals)}")
    if plan.quest_offer:
        told.append(f"They offer the quest {plan.quest_offer.get('title')}.")
    if plan.wares:
        told.append(f"They sell {', '.join(plan.wares)}.")
    if not line:
        return DialogueResolution(plan_changes(plan), [*told, plan.fallback_beat()], speaker_id, plan.speaker_name,
                                  "", written_by_model=False)
    changes = [*plan_changes(plan), DialogueExchanged(npc_id=speaker_id, name=plan.speaker_name, player_line=text[:500],
                                                      npc_line=line)]
    return DialogueResolution(changes, told, speaker_id, plan.speaker_name, line, written_by_model=keeps)


__all__ = ["DialogueResolution", "resolve_dialogue"]
