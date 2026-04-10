"""Functional tests — Idle conversation settings and real activity timer."""
from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, SRC_DIR)

_REAL_MODULES = {
    "app.rpg.session.runtime",
    "app.rpg.session.ambient_builder",
    "app.rpg.session.ambient_policy",
    "app.rpg.ai.ambient_dialogue",
    "app.rpg.ai.npc_initiative",
    "app.rpg.creator.schema",
    "app.rpg.creator.defaults",
    "app.rpg.analytics.world_events",
}


class _StubModule(types.ModuleType):
    def __init__(self, name: str):
        super().__init__(name)
        self.__path__: list = []
        self.__package__ = name
        self.__file__ = "<stub>"
        self.__loader__ = None

    def __getattr__(self, name: str):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return MagicMock()


class _StubLoader(importlib.abc.Loader):
    def create_module(self, spec):
        return _StubModule(spec.name)

    def exec_module(self, module):
        pass


class _AppStubFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if not fullname.startswith("app."):
            return None
        if fullname in _REAL_MODULES:
            return None
        return importlib.machinery.ModuleSpec(fullname, _StubLoader())


sys.meta_path.insert(0, _AppStubFinder())


def _load(mod_name: str, rel_path: str):
    """Load a real module by file path, bypassing package __init__.py."""
    sys.modules.pop(mod_name, None)
    spec = importlib.util.spec_from_file_location(
        mod_name, os.path.join(SRC_DIR, rel_path),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


_schema = _load("app.rpg.creator.schema", "app/rpg/creator/schema.py")
_defaults = _load("app.rpg.creator.defaults", "app/rpg/creator/defaults.py")
_amb_builder = _load("app.rpg.session.ambient_builder", "app/rpg/session/ambient_builder.py")
_amb_policy = _load("app.rpg.session.ambient_policy", "app/rpg/session/ambient_policy.py")
_amb_dialogue = _load("app.rpg.ai.ambient_dialogue", "app/rpg/ai/ambient_dialogue.py")
_npc_init = _load("app.rpg.ai.npc_initiative", "app/rpg/ai/npc_initiative.py")
_runtime = _load("app.rpg.session.runtime", "app/rpg/session/runtime.py")

_normalize_runtime_settings = _runtime._normalize_runtime_settings
_record_real_player_activity = _runtime._record_real_player_activity
_seconds_since_iso = _runtime._seconds_since_iso
_classify_player_action_context = _runtime._classify_player_action_context
build_ambient_dialogue_candidates = _amb_dialogue.build_ambient_dialogue_candidates


class TestSettingsNormalization:
    def test_default_idle_seconds(self):
        result = _normalize_runtime_settings({})
        assert result["idle_conversation_seconds"] == 60

    def test_allowed_idle_seconds(self):
        for val in (30, 60, 300, 600):
            result = _normalize_runtime_settings({"idle_conversation_seconds": val})
            assert result["idle_conversation_seconds"] == val

    def test_disallowed_idle_seconds_defaults(self):
        result = _normalize_runtime_settings({"idle_conversation_seconds": 45})
        assert result["idle_conversation_seconds"] == 60

    def test_string_idle_seconds(self):
        result = _normalize_runtime_settings({"idle_conversation_seconds": "60"})
        assert result["idle_conversation_seconds"] == 60

    def test_booleans_normalized(self):
        result = _normalize_runtime_settings({
            "idle_conversations_enabled": True,
            "follow_reactions_enabled": False,
        })
        assert result["idle_conversations_enabled"] is True
        assert result["follow_reactions_enabled"] is False

    def test_unknown_keys_dropped(self):
        result = _normalize_runtime_settings({"bogus_key": "xyz"})
        assert "bogus_key" not in result

    def test_reaction_style_enum(self):
        for val in ("minimal", "normal", "lively"):
            result = _normalize_runtime_settings({"reaction_style": val})
            assert result["reaction_style"] == val

    def test_invalid_reaction_style_defaults(self):
        result = _normalize_runtime_settings({"reaction_style": "extreme"})
        assert result["reaction_style"] == "normal"

    def test_none_input(self):
        result = _normalize_runtime_settings(None)
        assert result["response_length"] == "short"
        assert result["idle_conversation_seconds"] == 60

    def test_response_length_preserved(self):
        result = _normalize_runtime_settings({"response_length": "long"})
        assert result["response_length"] == "long"

    def test_response_length_medium_preserved(self):
        result = _normalize_runtime_settings({"response_length": "medium"})
        assert result["response_length"] == "medium"

    def test_response_length_legacy_dict_uses_narrator_length(self):
        result = _normalize_runtime_settings({
            "response_length": {
                "narrator_length": "long",
                "character_length": "short",
            }
        })
        assert result["response_length"] == "long"

    def test_response_length_legacy_dict_invalid_defaults_to_short(self):
        result = _normalize_runtime_settings({"response_length": {"narrator_length": "verbose"}})
        assert result["response_length"] == "short"


class TestRealPlayerActivity:
    def test_records_timestamp(self):
        rt = {"last_real_player_activity_at": "", "idle_streak": 5}
        rt = _record_real_player_activity(rt)
        assert rt["last_real_player_activity_at"] != ""
        assert rt["idle_streak"] == 0

    def test_seconds_since_iso_empty_returns_high(self):
        assert _seconds_since_iso("") == 9999

    def test_seconds_since_iso_recent_returns_small(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        result = _seconds_since_iso(now)
        assert result < 5

    def test_seconds_since_iso_invalid(self):
        assert _seconds_since_iso("not-a-date") == 9999


class TestIdleGateLogic:
    def test_idle_gate_closed_when_disabled(self):
        settings = _normalize_runtime_settings({"idle_conversations_enabled": False})
        idle_gate_open = bool(settings.get("idle_conversations_enabled")) and 9999 >= 60
        assert idle_gate_open is False

    def test_idle_gate_closed_before_threshold(self):
        settings = _normalize_runtime_settings({"idle_conversations_enabled": True, "idle_conversation_seconds": 300})
        idle_seconds = 60  # less than 300
        idle_gate_open = bool(settings.get("idle_conversations_enabled")) and idle_seconds >= 300
        assert idle_gate_open is False

    def test_idle_gate_open_after_threshold(self):
        settings = _normalize_runtime_settings({"idle_conversations_enabled": True, "idle_conversation_seconds": 60})
        idle_seconds = 120  # more than 60
        idle_gate_open = bool(settings.get("idle_conversations_enabled")) and idle_seconds >= 60
        assert idle_gate_open is True


class TestClassifyPlayerAction:
    def test_rush_intent(self):
        result = _classify_player_action_context(
            "i rush toward the fissure", {}, {"tick": 5, "player_state": {"location_id": "loc:cave"}}, {}
        )
        assert result["movement_intent"] == "rush"
        assert result["urgency"] == "high"

    def test_inspect_intent(self):
        result = _classify_player_action_context(
            "i examine the ancient runes", {}, {"tick": 5, "player_state": {"location_id": "loc:cave"}}, {}
        )
        assert result["movement_intent"] == "inspect"
        assert result["risk_level"] == "low"

    def test_retreat_intent(self):
        result = _classify_player_action_context(
            "flee from the danger", {}, {"tick": 5, "player_state": {"location_id": "loc:cave"}}, {}
        )
        assert result["movement_intent"] == "retreat"

    def test_wait_intent(self):
        result = _classify_player_action_context(
            "wait here and rest", {}, {"tick": 5, "player_state": {"location_id": "loc:cave"}}, {}
        )
        assert result["movement_intent"] == "wait"

    def test_attack_intent_high_risk(self):
        result = _classify_player_action_context(
            "attack the guard", {}, {"tick": 5, "player_state": {"location_id": "loc:cave"}}, {}
        )
        assert result["movement_intent"] == "attack"
        assert result["risk_level"] == "high"

    def test_unknown_intent(self):
        result = _classify_player_action_context(
            "hmm interesting", {}, {"tick": 5, "player_state": {"location_id": "loc:cave"}}, {}
        )
        assert result["movement_intent"] == "unknown"

    def test_bounded_player_input(self):
        long_input = "x" * 500
        result = _classify_player_action_context(
            long_input, {}, {"tick": 5, "player_state": {"location_id": "loc:cave"}}, {}
        )
        assert len(result["player_input"]) <= 200


class TestIdleNpcToNpcRespectsSettings:
    def test_npc_to_npc_disabled(self):
        sim = {
            "tick": 5,
            "npc_index": {
                "npc:a": {"name": "A", "location_id": "loc:x", "role": "merchant"},
                "npc:b": {"name": "B", "location_id": "loc:x", "role": "merchant"},
            },
            "npc_minds": {
                "npc:a": {"beliefs": {"npc:b": {"trust": 0.5}}, "goals": []},
                "npc:b": {"beliefs": {"npc:a": {"trust": 0.5}}, "goals": []},
            },
            "player_state": {"location_id": "loc:x", "nearby_npc_ids": ["npc:a", "npc:b"], "party_npc_ids": []},
        }
        rt = {"tick": 5, "ambient_cooldowns": {}, "settings": {"idle_npc_to_npc_enabled": False}}
        ctx = {"player_location": "loc:x", "nearby_npc_ids": ["npc:a", "npc:b"]}
        candidates = build_ambient_dialogue_candidates(sim, rt, ctx, lane="idle")
        npc_to_npc = [c for c in candidates if c.get("kind") == "npc_to_npc" and c.get("lane") == "idle"]
        assert len(npc_to_npc) == 0
