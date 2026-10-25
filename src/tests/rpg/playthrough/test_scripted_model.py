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
    from app.apps.rpg.session.turn.dialogue import _LINE_PROMPT
    from app.apps.rpg.session.turn.intent import _PROMPT as INTENT

    model = ScriptedRoleModel({Role.DIALOGUE: ("", "Mind the step.")})
    line = _LINE_PROMPT.format(v0="hello") + json.dumps({"speaker": "Orik Stonewake"})
    assert model.chat_completion([ChatMessage(role="user", content=line)]).content == "Mind the step."

    intent = INTENT.format(v0="I hum a tune") + json.dumps({"SCENE": []})
    model.queue(Role.INTENT, {"readings": [{"family": "look", "confidence": 0.9}]})
    assert json.loads(model.chat_completion([ChatMessage(role="user", content=intent)]).content)["readings"]
    assert model.chat_completion([ChatMessage(role="user", content=intent)]).content == "{}"  # queue spent

    assert classify("an unrelated prompt").role is Role.UNCLASSIFIED
    assert model.roles() == ["dialogue", "intent", "intent"]
