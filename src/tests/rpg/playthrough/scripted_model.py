"""A scripted model that answers RPG model calls by their semantic role (RQ-0.2, RQ-0.3).

Playthrough scenarios fix the model's answers, not its prompts. ``classify`` names the role of a call
(intent, dialogue, narration, lore, ...) from the registered prompt template it was rendered from
(``app.prompts.registry``), and ``ScriptedRoleModel`` answers each role in the shape that call's contract
expects. A scenario says "Liora answers 'Welcome.'" or "the intent router has no advice"; when a call's
wording or answer shape changes, only this adapter changes, and goldens stay as they were.

The narrative engine's writer is answered here too (role ``narration``): its blocks repeat each beat's
first approved evidence line, so the prose is the engine's own confirmed facts.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Any


class Role(str, Enum):
    INTENT = "intent"  # read what the player means (first-call routers, action advisories)
    DIALOGUE = "dialogue"  # who is addressed, and their spoken line
    NARRATION = "narration"  # the turn's prose (narrator drafts, candidates, the narrative writer)
    LORE = "lore"  # dossiers, lore pages, item and ability descriptions, materialized canon
    WORLD = "world"  # NPC reactions, NPC decisions, state-change proposals, story resolution
    CHOICES = "choices"  # suggested next actions and their flavour
    AUDIT = "audit"  # a check of displayed text against the turn
    UNCLASSIFIED = "unclassified"


# Each registered RPG prompt template, by id prefix, names its call's role. Longest prefix wins.
_TEMPLATE_ROLES: tuple[tuple[str, Role], ...] = (
    ("rpg.turn_intent.", Role.INTENT),
    ("rpg.ai_semantic_action_intelligence.", Role.INTENT),
    ("rpg.ai_action_intelligence.", Role.INTENT),
    ("rpg.cognitive_intent_enrichment.", Role.INTENT),
    ("rpg.ai_compact_dialogue.", Role.DIALOGUE),
    ("rpg.ai_conversation_prompt_builder.", Role.DIALOGUE),
    ("rpg.npc_dialogue_intelligence.", Role.DIALOGUE),
    ("rpg.ai_world_scene_narrator_prompts.prompt_2", Role.WORLD),
    ("rpg.ai_world_scene_narrator_prompts.prompt_3", Role.CHOICES),
    ("rpg.ai_world_scene_narrator_prompts.", Role.NARRATION),
    ("rpg.narration_", Role.NARRATION),
    ("rpg.narrative_", Role.NARRATION),
    ("rpg.jobs_turn_executor.", Role.NARRATION),
    ("rpg.session_genesis_", Role.LORE),
    ("rpg.session_item_detail.", Role.LORE),
    ("rpg.session_ability_detail.", Role.LORE),
    ("rpg.profiles_", Role.LORE),
    ("rpg.ai_llm_mind_npc_prompt_builder.", Role.WORLD),
    ("rpg.session_semantic_state_changes.", Role.WORLD),
    ("rpg.cognitive_resolution_engine.", Role.WORLD),
    ("rpg.session_player_agency_contract.", Role.CHOICES),
    ("rpg.ai_grounding_soft_audit.", Role.AUDIT),
)
# Templates that are fragments inside another call's prompt (grounding rules, schemas): they never name a call.
_FRAGMENT_TEMPLATES = re.compile(
    r"(_grounding\.|personality\.|memory_prompt\.|environment_narration\.|current_turn_prompt_contract\.|"
    r"response_length_prompt_rules|hooks_text|dossier_prompt_contract|party_defeat_instruction)"
)
_MIN_SEGMENT = 24


@lru_cache(maxsize=1)
def _template_segments() -> tuple[tuple[str, str], ...]:
    """(template id, literal segment) for every RPG call template, longest segments first."""
    from app.prompts.registry import load_templates

    segments: list[tuple[str, str]] = []
    for template_id, template in load_templates().items():
        if not template_id.startswith("rpg.") or _FRAGMENT_TEMPLATES.search(template_id):
            continue
        literal = template.text.replace("{{", "\x00").replace("}}", "\x01")
        for part in re.split(r"\{[^{}]*\}", literal):
            part = part.replace("\x00", "{").replace("\x01", "}").strip()
            if len(part) >= _MIN_SEGMENT:
                segments.append((template_id, part))
    return tuple(sorted(segments, key=lambda item: -len(item[1])))


def _role_of_template(template_id: str) -> Role:
    best: tuple[int, Role] = (0, Role.UNCLASSIFIED)
    for prefix, role in _TEMPLATE_ROLES:
        if template_id.startswith(prefix) and len(prefix) > best[0]:
            best = (len(prefix), role)
    return best[1]


@dataclass(frozen=True)
class ModelCall:
    """One model call, as a scenario sees it."""

    role: Role
    template_id: str
    text: str
    player_text: str = ""
    context: Mapping[str, Any] = field(default_factory=dict)

    @property
    def present_npcs(self) -> list[dict[str, Any]]:
        return [dict(npc) for npc in self.context.get("present_npcs") or () if isinstance(npc, Mapping)]


def _context_json(text: str) -> dict[str, Any]:
    if "<<<WORLD_DATA\n" in text:  # a plan fenced as the world's data (narration/world_data.py)
        try:
            value = json.loads(text.rsplit("<<<WORLD_DATA\n", 1)[1].rsplit("\nWORLD_DATA>>>", 1)[0])
        except ValueError:
            value = None
        if isinstance(value, dict):
            return value
    for marker in ("CONTEXT: ", "Context JSON:\n"):
        if marker in text:
            try:
                value = json.loads(text.rsplit(marker, 1)[1])
            except ValueError:
                continue
            if isinstance(value, dict):
                return value
    return {}


def classify(text: str) -> ModelCall:
    """The role of a call, from the registered template its prompt was rendered from."""
    template_id = next((tid for tid, segment in _template_segments() if segment in text), "")
    player = re.search(r"^PLAYER: (.*)$", text, re.MULTILINE)
    return ModelCall(
        role=_role_of_template(template_id) if template_id else Role.UNCLASSIFIED,
        template_id=template_id,
        text=text,
        player_text=player.group(1).strip() if player else "",
        context=_context_json(text),
    )


# A role's answer: a fixed value, or a function of the call. Dialogue answers are (speaker, line):
# the speaker is a present NPC's id or name ("" for "whoever is addressed, else the first present").
Answer = Any | Callable[[ModelCall], Any]

DEFAULT_NARRATION = "The moment passes."
DEFAULT_LINE = "Welcome, traveler."
_EMPTY_CANON = {"entities": [], "documents": [], "facts": [], "relationships": []}


def _addressee(call: ModelCall, wanted: str) -> dict[str, Any]:
    present = call.present_npcs
    if not present:
        return {}
    wanted = wanted.casefold()
    if wanted:
        for npc in present:
            if wanted in (str(npc.get("id") or "").casefold(), str(npc.get("name") or "").casefold()):
                return npc
    spoken = call.player_text.casefold()
    for npc in present:
        name = str(npc.get("name") or "").casefold()
        first = name.split(" ")[0] if name else ""
        if name and (name in spoken or (len(first) > 2 and re.search(rf"\b{re.escape(first)}\b", spoken))):
            return npc
    return present[0]


class ScriptedRoleModel:
    """A provider whose every call is answered by role; records the role of each call it saw."""

    name = "scripted"
    provider_id = "scripted"

    def __init__(self, answers: Mapping[Role, Answer] | None = None) -> None:
        self.answers: dict[Role, Answer] = dict(answers or {})
        self._queued: dict[Role, list[Answer]] = {}
        self.calls: list[ModelCall] = []
        self.writer_payloads: list[dict[str, Any]] = []

    # -- scripting ---------------------------------------------------------------------------------
    def answer(self, role: Role, value: Answer) -> None:
        """Answer every later call of this role with ``value``."""
        self.answers[role] = value

    def queue(self, role: Role, *values: Answer) -> None:
        """Answer the next calls of this role with ``values``, in order, then fall back to ``answer``."""
        self._queued.setdefault(role, []).extend(values)

    def roles(self, since: int = 0) -> list[str]:
        return [call.role.value for call in self.calls[since:]]

    def role_counts(self, since: int = 0) -> dict[str, int]:
        return dict(sorted(Counter(self.roles(since)).items()))

    @property
    def unclassified(self) -> list[str]:
        return [call.text[:300] for call in self.calls if call.role is Role.UNCLASSIFIED]

    def _scripted(self, call: ModelCall, default: Any) -> Any:
        queued = self._queued.get(call.role)
        value = queued.pop(0) if queued else self.answers.get(call.role, default)
        return value(call) if callable(value) else value

    # -- answering, in each contract's shape -------------------------------------------------------
    def _render(self, call: ModelCall) -> str:
        if call.role is Role.INTENT:
            return json.dumps(self._scripted(call, {}) or {})
        if call.role is Role.DIALOGUE:
            speaker, line = self._scripted(call, ("", DEFAULT_LINE))
            npc = _addressee(call, str(speaker or ""))
            if call.template_id == "rpg.ai_compact_dialogue.choose_speaker":
                return json.dumps({"speaker_id": str(npc.get("id") or ""), "line": line})
            if call.template_id.startswith("rpg.ai_conversation_prompt_builder."):
                return json.dumps({"speaker": str(npc.get("name") or speaker or ""), "text": line, "kind": "statement"})
            if call.template_id.startswith("rpg.npc_dialogue_intelligence."):
                return json.dumps({"line": line})
            return str(line)
        if call.role is Role.NARRATION:
            prose = str(self._scripted(call, DEFAULT_NARRATION))
            single = {"format_version": "rpg_narration_v2", "narration": prose, "action": prose,
                      "npc": {"speaker": "", "line": ""}, "reward": None, "followup_hooks": []}
            if "rpg_narration_candidates_v1" in call.text:
                return json.dumps({"format_version": "rpg_narration_candidates_v1", "primary": single,
                                   "safe_fallback": single})
            if '"format_version": "rpg_narration_v2"' in call.text:
                return json.dumps(single)
            return prose
        if call.role is Role.LORE:
            value = self._scripted(call, _EMPTY_CANON)
            return value if isinstance(value, str) else json.dumps(value)
        value = self._scripted(call, {})
        return value if isinstance(value, str) else json.dumps(value)

    def _respond(self, messages: Sequence[Any]) -> str:
        text = "\n".join(str(getattr(message, "content", None) or (message.get("content") if isinstance(message, Mapping) else "") or "")
                         for message in messages)
        call = classify(text)
        self.calls.append(call)
        return self._render(call)

    # -- the provider surface the RPG uses -------------------------------------------------------------
    def chat_completion(self, messages, model=None, stream=False, **kwargs):
        from app.providers.base import ChatResponse

        response = ChatResponse(content=self._respond(messages), model="scripted")
        return iter([response]) if stream else response

    def chat(self, messages=None, **kwargs):
        return self._respond(messages or ())

    def supports_streaming(self) -> bool:
        return False

    def get_capabilities(self) -> list:
        return []

    # -- the narrative engine's writer -------------------------------------------------------------
    def write_narrative(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """The narrative writer's answer: each beat repeats its first approved evidence line."""
        self.writer_payloads.append(dict(payload))
        self.calls.append(ModelCall(role=Role.NARRATION, template_id="narrative_engine.writer", text=""))
        blocks = []
        for beat in payload.get("beats") or ():
            text = next(
                (line for record in beat.get("approved_evidence") or ()
                 if (line := str(record.get("content") or record.get("text") or "").strip().split("\n")[0].strip())),
                "",
            )
            blocks.append({"beat_id": beat["beat_id"], "sequence": beat["sequence"], "kind": beat["kind"],
                           "purpose": beat["purpose"], "speaker_id": beat.get("speaker_id") or "",
                           "text": text or "You take in your surroundings."})
        return {"blocks": blocks}

    def told(self, index: int = -1) -> str:
        """The evidence the narrative writer was given for one turn: what the narrator may say happened."""
        if not self.writer_payloads:
            return ""
        payload = self.writer_payloads[index]
        return " ".join(str(record.get("content") or "") for beat in payload.get("beats") or ()
                        for record in beat.get("approved_evidence") or ())


@contextmanager
def scripted_model_installed(monkeypatch, model: ScriptedRoleModel | None = None) -> Iterator[ScriptedRoleModel]:
    """Route every RPG model call, and the narrative writer, to ``model``; install the PostgreSQL job store."""
    from app.jobs import store as job_store
    from app.persistence.startup import bootstrap_postgresql_runtime
    from app.platform.chat.persistence.job_store import PostgresJobStoreAdapter
    from app.providers import service as provider_service
    from app.apps.rpg.narration.narrative_engine import service as narrative_service
    from app.apps.rpg.narration.narrative_engine.writer import StructuredNarrativeWriter

    model = model or ScriptedRoleModel()
    monkeypatch.setenv("OMNIX_RPG_TURNS_PER_HOUR", "0")  # a playthrough plays many turns quickly (no RPG turn budget)
    bootstrap_postgresql_runtime()
    jobs = PostgresJobStoreAdapter()
    job_store.install_default_job_store_factory(lambda: jobs)
    monkeypatch.setattr(provider_service, "get_provider", lambda *args, **kwargs: model)
    monkeypatch.setattr(provider_service, "get_routed_provider", lambda *args, **kwargs: model)
    monkeypatch.setattr(
        narrative_service,
        "_production_writer",
        lambda: StructuredNarrativeWriter(model.write_narrative, provider="scripted", model="scripted"),
    )
    try:
        yield model
    finally:
        job_store.reset_default_job_store_factory_for_tests()
