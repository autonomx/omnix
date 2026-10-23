"""The role-keyed scripted model classifies calls by their prompt template (RQ-0.2)."""
from __future__ import annotations

import json

from tests.rpg.playthrough.scripted_model import Role, ScriptedRoleModel, _FRAGMENT_TEMPLATES, _role_of_template, classify


def test_every_rpg_call_template_has_a_role() -> None:
    """A new RPG prompt must be given a role here, or playthroughs would answer it blindly.

    World generation and image prompts (``rpg.worlds_``, ``rpg.api_``) are not made inside a turn.
    """
    from app.prompts.registry import load_templates

    unassigned = [template_id for template_id in load_templates()
                  if template_id.startswith("rpg.") and not template_id.startswith(("rpg.worlds_", "rpg.api_"))
                  and not _FRAGMENT_TEMPLATES.search(template_id)
                  and _role_of_template(template_id) is Role.UNCLASSIFIED]
    assert unassigned == [], unassigned


def test_calls_are_answered_by_role_in_their_contracts_shape() -> None:
    from app.providers.base import ChatMessage
    from app.apps.rpg.session.compact_dialogue import _PROMPT_1, _PROMPT_2
    from app.apps.rpg.session.semantic_action_intelligence import _PROMPT_1 as INTENT

    context = {"present_npcs": [{"id": "npc:orik", "name": "Orik Stonewake"}, {"id": "npc:liora", "name": "Liora Fen"}]}
    model = ScriptedRoleModel({Role.DIALOGUE: ("", "Mind the step.")})

    choose = _PROMPT_2.format(v0="I ask Liora where we are") + json.dumps(context)
    answer = json.loads(model.chat_completion([ChatMessage(role="user", content=choose)]).content)
    assert answer == {"speaker_id": "npc:liora", "line": "Mind the step."}  # the one addressed by name

    line = _PROMPT_1.format(v0="hello") + json.dumps(context)
    assert model.chat_completion([ChatMessage(role="user", content=line)]).content == "Mind the step."

    intent = INTENT.text + "\nContext JSON:\n{}"
    model.queue(Role.INTENT, {"action_intent": {"action_type": "observe"}})
    assert json.loads(model.chat_completion([ChatMessage(role="user", content=intent)]).content)["action_intent"]
    assert model.chat_completion([ChatMessage(role="user", content=intent)]).content == "{}"  # queue spent

    assert classify("an unrelated prompt").role is Role.UNCLASSIFIED
    assert model.roles() == ["dialogue", "dialogue", "intent", "intent"]
