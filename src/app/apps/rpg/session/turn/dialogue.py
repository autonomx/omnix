"""Dialogue on the pipeline (RQ-2.2; docs/rpg/design/dialogue.md): the plan decides, one model call phrases the line.

``resolve_dialogue`` builds the speaker's ``DialoguePlan`` (``rules/dialogue/plan.py``), has the model write the line
from it, checks the line against the plan (no secret said), and falls back to the plan's own line when the model
cannot write one. The plan's changes (what is now known, a quest offered) and the exchange are the turn's changes.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Mapping

from app.apps.rpg.foundation.safe_values import safe_dict as _d, safe_list as _l, safe_str as _s
from app.apps.rpg.foundation.state.changes import DialogueExchanged, StateChange
from app.apps.rpg.narration.narration_drafts import narration_draft_active, publish_narration_draft
from app.apps.rpg.narration.world_data import RULE as WORLD_DATA_RULE, world_data
from app.apps.rpg.rules.dialogue.plan import DialoguePlan, build_plan, line_keeps_the_plan, plan_changes
from app.prompts import prompt_template
from app.apps.rpg.foundation.state import access as _sections

logger = logging.getLogger(__name__)
_LINE_PROMPT = prompt_template(
    "rpg.ai_compact_dialogue.plan", "3",
    "Reply as the speaker in the PLAN, in one or two concise spoken sentences, in their voice and stance. Output "
    "only the words they say: no name label, narration, JSON or markdown. Share what may_reveal holds, offer what "
    "offers_quest or offers_to_tell_for_a_price hold, and name each of wares with its price as written; about anything else, answer from their role and "
    "background or say they do not know. Keep continuity with "
    "recent_exchanges without repeating them. " + WORLD_DATA_RULE + "\nPLAYER: {v0}\nPLAN: ",
)
MAX_LINE = 400
LINE_TIMEOUT_SECONDS = 20.0  # a person's line: past this the plan's own line answers (RQ-8.8)


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
    if line[:1] in "{[<" or not re.search(r"[^\W\d_]", line):
        return ""  # JSON, markup or no words at all is no line: the plan's own answers
    return line[:MAX_LINE]


def _write_line(plan: DialoguePlan, exchanges: list[dict[str, Any]], text: str) -> str:
    from app.apps.rpg.foundation.llm_app_gateway import build_app_llm_gateway

    gateway = build_app_llm_gateway()
    if gateway is None:
        return ""
    context = {**plan.context(), "recent_exchanges": exchanges[-3:]}
    prompt = _LINE_PROMPT.format(v0=text[:500]) + world_data(context)  # the plan's world text, fenced as data
    try:
        if narration_draft_active():  # the play screen follows the turn: the line is shown as it is written (Q-12)
            return _streamed_line(gateway, prompt, plan.speaker_name)
        raw = gateway.generate(prompt, timeout_s=LINE_TIMEOUT_SECONDS,
                               provider_options={"temperature": 0.55, "max_tokens": 90,
                                                 "chat_template_kwargs": {"enable_thinking": False}})
    except Exception:
        logger.warning("rpg_dialogue_line_failed speaker=%s", plan.speaker_id, exc_info=True)
        return ""
    return _s(raw)


def _streamed_line(gateway: Any, prompt: str, speaker: str) -> str:
    """The line as the model writes it, published to the turn's draft as it grows; the whole line is returned."""
    parts: list[str] = []
    for chunk in gateway.generate_stream(prompt, timeout_s=LINE_TIMEOUT_SECONDS):
        parts.append(_s(chunk.get("text")))
        partial = _clean("".join(parts), speaker)
        if partial:
            publish_narration_draft(f'{speaker}: "{partial}"')
    return "".join(parts)


def _speaker(simulation: Mapping[str, Any], runtime: Mapping[str, Any], target_id: str) -> str:
    present = set(_l(_d(_sections.present_npc_state_of(simulation)).get("present_npc_ids")))
    if target_id and target_id in present:
        return target_id
    focus = _s(_d(runtime.get("dialogue_focus")).get("target_id"))
    if target_id:
        return ""
    if focus in present:
        return focus
    # Spoken to no one in particular, with one person here: they are the one who answers.
    return next(iter(present)) if len(present) == 1 else ""


def resolve_dialogue(session: Mapping[str, Any], target_id: str, text: str) -> DialogueResolution | None:
    """The answer of the person spoken to; ``None`` when no one present is clearly spoken to (the older path's)."""
    simulation = _d(_sections.simulation_state_of(session))
    speaker_id = _speaker(simulation, _d(_sections.runtime_state_of(session)), target_id)
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
