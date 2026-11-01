"""Dialogue on the pipeline (RQ-2.2; docs/rpg/design/dialogue.md): the plan decides, one model call phrases the line.

``resolve_dialogue`` builds the speaker's ``DialoguePlan`` (``rules/dialogue/plan.py``), has the model write the line
from it, checks the line against the plan (no secret said), and falls back to the plan's own line when the model
cannot write one. The plan's changes (what is now known, a quest offered) and the exchange are the turn's changes.
"""
from __future__ import annotations

import logging
import re
from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import ContextVar, copy_context
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
    "rpg.ai_compact_dialogue.plan", "10",
    "Reply as the speaker in the PLAN, in one or two concise spoken sentences, in their voice and stance. Output "
    "only the words they say: no name label, narration, JSON or markdown. Share what may_reveal holds, offer what "
    "offers_quest or offers_to_tell_for_a_price hold, and name each of wares with its price as written. Asked what to "
    "do or how, point to heros_quests: where each goes on, in the speaker's own words, never quoting a quest's title "
    "(one that is done is done: do not send them back to it). Asked of a place or person, they may tell what "
    "common_knowledge holds, in their own way. When what_these_words_do names a step, the hero's words do it now: "
    "answer as one to whom it has just been done, never asking for it again or for it to be done elsewhere. "
    "Speak to and of the hero as hero names them, with no gendered address (lass, lad, sir, madam) their pronouns "
    "do not call for. "
    "Never invent a task, item or requirement the PLAN does not hold, and never speak of the plan itself. About "
    "anything else, answer from their role and "
    "background or say they do not know. Keep continuity with "
    "recent_exchanges without repeating them: no phrase, image or saying of theirs again. " + WORLD_DATA_RULE + "\nPLAYER: {v0}\nPLAN: ",
)
MAX_LINE = 400
_LINE_OPTIONS = {"temperature": 0.55, "max_tokens": 90, "chat_template_kwargs": {"enable_thinking": False}}
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
    from app.apps.rpg.narration.lore_links import note

    line = note(_s(raw)).strip().strip('"').strip()  # a lore mark is noted for the links, never kept (EV-12)
    line = re.sub(rf"^\s*{re.escape(speaker)}\s*:\s*", "", line, flags=re.IGNORECASE).strip().strip('"')
    if line[:1] in "{[<" or not re.search(r"[^\W\d_]", line):
        return ""  # JSON, markup or no words at all is no line: the plan's own answers
    return line[:MAX_LINE]


def _write_line(plan: DialoguePlan, exchanges: list[dict[str, Any]], text: str, *, held: bool = False) -> str:
    """The line the model writes from the plan; ``held``: written beside the intent call, not shown as it grows (it
    may be discarded, EV-9)."""
    from app.apps.rpg.foundation.llm_app_gateway import build_app_llm_gateway

    gateway = build_app_llm_gateway()
    if gateway is None:
        return ""
    context = {**plan.context(), "recent_exchanges": exchanges[-3:]}
    prompt = _LINE_PROMPT.format(v0=text[:500]) + world_data(context)  # the plan's world text, fenced as data
    try:
        if narration_draft_active() and not held:  # the line is shown as it is written (Q-12)
            return _streamed_line(gateway, prompt, plan.speaker_name)
        raw = gateway.generate(prompt, timeout_s=LINE_TIMEOUT_SECONDS, provider_options=_LINE_OPTIONS)
    except Exception:
        logger.warning("rpg_dialogue_line_failed speaker=%s", plan.speaker_id, exc_info=True)
        return ""
    return _s(raw)


def _streamed_line(gateway: Any, prompt: str, speaker: str) -> str:
    """The line as the model writes it, published to the turn's draft as it grows; the whole line is returned."""
    parts: list[str] = []
    for chunk in gateway.generate_stream(prompt, timeout_s=LINE_TIMEOUT_SECONDS, provider_options=_LINE_OPTIONS):
        parts.append(_s(chunk.get("text")))
        partial = _clean("".join(parts), speaker)
        if partial:
            publish_narration_draft(f'{speaker}: "{partial}"')
    return "".join(parts)


def speaker_for(simulation: Mapping[str, Any], runtime: Mapping[str, Any], target_id: str) -> str:
    """Who answers a line: the person present it names; unnamed, the one the hero is talking with, or the one person
    here; "" when no one present is clearly spoken to."""
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


@dataclass
class HeldReply:
    """A person's reply written beside the intent call in a conversation under way (EV-9), from their plan with no
    topics; held, not shown, and used only when the turn's own plan for them is the plan it was written for."""

    speaker_id: str
    context: dict[str, Any]
    future: Future[str]
    used: bool = False


_HELD: ContextVar[HeldReply | None] = ContextVar("RPG_HELD_REPLY", default=None)
_REPLIES = ThreadPoolExecutor(max_workers=4, thread_name_prefix="rpg-held-reply")


def under_way(session: Mapping[str, Any]) -> str:
    """The person a conversation is under way with: the last turn left the hero talking with them, and they are still
    here; "" when there is none."""
    simulation = _d(_sections.simulation_state_of(session))
    focus = _s(_d(_d(_sections.runtime_state_of(session)).get("dialogue_focus")).get("target_id"))
    present = set(_l(_d(_sections.present_npc_state_of(simulation)).get("present_npc_ids")))
    return focus if focus and focus in present else ""


def hold_reply(session: Mapping[str, Any], text: str) -> HeldReply | None:
    """In a conversation under way, start the person's reply to ``text`` from their topic-free plan, beside the
    intent call; the turn uses it only when its own plan matches (``take_held_reply``)."""
    speaker_id = under_way(session)
    if not speaker_id:
        _HELD.set(None)
        return None
    simulation = _d(_sections.simulation_state_of(session))
    sheet = _d(_d(session.get("state")).get("player"))
    hero = {key: _s(sheet.get(key)) for key in ("name", "pronouns") if _s(sheet.get(key))}
    plan = build_plan(simulation, speaker_id, text, hero=hero)
    if plan is None:
        _HELD.set(None)
        return None
    exchanges = [_d(row) for row in _l(_d(_d(simulation.get("dialogue")).get("exchanges")).get(speaker_id))]
    future = _REPLIES.submit(copy_context().run, _write_held, plan, exchanges, text)
    held = HeldReply(speaker_id=speaker_id, context=plan.context(), future=future)
    _HELD.set(held)
    return held


def _write_held(plan: DialoguePlan, exchanges: list[dict[str, Any]], text: str) -> str:
    from app.apps.rpg.foundation.model_calls import APART, counted_as

    with counted_as(APART):  # counted apart: the turn may discard it (F3)
        return _write_line(plan, exchanges, text, held=True)


def take_held_reply(plan: DialoguePlan) -> str | None:
    """The held reply, when it was written for this very plan (the reading's topics and step added nothing to it);
    ``None`` otherwise, and the line is written for the plan as it is."""
    held = _HELD.get()
    if held is None or held.speaker_id != plan.speaker_id or held.context != plan.context():
        return None
    try:
        line = held.future.result(timeout=LINE_TIMEOUT_SECONDS)
    except Exception:  # timed out or failed: the line is written now
        logger.warning("rpg_held_reply_failed speaker=%s", plan.speaker_id, exc_info=True)
        return None
    from app.apps.rpg.foundation.model_calls import used_apart

    held.used = True
    used_apart()  # the turn's own dialogue call after all
    return line


def settle_held_reply() -> str:
    """How the held reply went, once the turn is planned and resolved: "used", "discarded" (counted apart, F3), or
    "" when none was written."""
    held = _HELD.get()
    _HELD.set(None)
    if held is None:
        return ""
    return "used" if held.used else "discarded"


def resolve_dialogue(session: Mapping[str, Any], target_id: str, text: str, *, topics: tuple[str, ...] = (),
                     step: str = "") -> DialogueResolution | None:
    """The answer of the person spoken to, to the line ``text``, which asks about its reading's ``topics`` and may
    answer a quest ``step`` (EV-3: accepted only when it is one of the speaker's open steps); ``None`` when no one
    present is clearly spoken to (the older path's)."""
    from app.apps.rpg.rules.quest.progress import accepted_step

    simulation = _d(_sections.simulation_state_of(session))
    speaker_id = speaker_for(simulation, _d(_sections.runtime_state_of(session)), target_id)
    sheet = _d(_d(session.get("state")).get("player"))  # who the hero is, as their sheet names them
    hero = {key: _s(sheet.get(key)) for key in ("name", "pronouns") if _s(sheet.get(key))}
    plan = (build_plan(simulation, speaker_id, text, topics=topics, step=accepted_step(simulation, speaker_id, step),
                       hero=hero) if speaker_id else None)
    if plan is None:
        return None
    exchanges = [_d(row) for row in _l(_d(_d(simulation.get("dialogue")).get("exchanges")).get(speaker_id))]
    held = take_held_reply(plan)  # written beside the intent call for this same plan (EV-9)
    written = _clean(held if held is not None else _write_line(plan, exchanges, text), plan.speaker_name)
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
                                                      npc_line=line, step=plan.step)]
    return DialogueResolution(changes, told, speaker_id, plan.speaker_name, line, written_by_model=keeps)


__all__ = ["DialogueResolution", "HeldReply", "hold_reply", "resolve_dialogue", "settle_held_reply", "speaker_for",
           "take_held_reply", "under_way"]
