"""Tests for deterministic RPG memory grounding guard."""
from __future__ import annotations

from app.rpg.ai import world_scene_narrator
from app.rpg.ai.memory_narration_grounding import (
    build_memory_narration_evidence,
    memory_narration_prompt_block,
    sanitize_memory_narration_payload,
    validate_memory_narration_text,
)
from app.rpg.ai.world_scene_narrator_prompts import build_scene_prompt
from app.rpg.session.memory_actor import write_actor_memory


def _session_with_bran_memory() -> dict:
    return write_actor_memory(
        {"runtime_state": {}},
        actor_id="bran",
        text="Bran remembers that the player paid for stew without haggling.",
        relationship={"target_id": "player", "axes": {"trust": 2}},
        location_id="rusty_flagon",
        tags=["stew", "commerce"],
    )


def _context() -> dict:
    session = _session_with_bran_memory()
    return {
        "runtime_state": session["runtime_state"],
        "simulation_state": {"player_state": {"location_id": "rusty_flagon"}},
        "player_input": "Bran, do you remember me?",
        "turn_contract": {
            "narration_brief": {"summary": "Bran answers the player's question."},
            "interpreted_action": {"target_id": "bran", "target_name": "Bran"},
            "present_npcs": [{"id": "bran", "name": "Bran"}],
        },
        "resolved_result": {
            "target_id": "bran",
            "target_name": "Bran",
            "summary": "Bran answers the player's question.",
        },
    }


def test_memory_narration_evidence_uses_relevant_memory():
    evidence = build_memory_narration_evidence(_context())

    assert evidence["format_version"] == "rpg_memory_narration_grounding_v1"
    assert evidence["memory_ids"] == ["mem:000001"]
    assert "stew" in evidence["evidence_tokens"]


def test_memory_narration_validation_accepts_backed_memory_reference():
    result = validate_memory_narration_text(
        "Bran remembers that you paid for stew without haggling.",
        _context(),
    )

    assert result["ok"] is True
    assert result["violations"] == []


def test_memory_narration_validation_rejects_unbacked_memory_reference():
    result = validate_memory_narration_text(
        "Bran remembers that you stole a moonstone locket last time.",
        _context(),
    )

    assert result["ok"] is False
    assert result["violations"][0]["code"] == "unsupported_memory_reference"


def test_memory_narration_sanitizer_strips_unbacked_claims():
    payload = {
        "format_version": "rpg_narration_v2",
        "narration": (
            "Bran remembers that you stole a moonstone locket last time. "
            "He keeps his hands on the counter."
        ),
        "action": "",
        "npc": {
            "speaker": "Bran",
            "line": "I remember you stole that moonstone locket.",
        },
    }

    sanitized = sanitize_memory_narration_payload(payload, _context())

    assert "moonstone" not in sanitized["narration"]
    assert sanitized["narration"] == "He keeps his hands on the counter."
    assert sanitized["npc"]["line"] == "I can only speak to what I know right now."
    assert sanitized["memory_grounding_validation"]["ok"] is True
    assert sanitized["memory_grounding_validation"]["original_violations"]


def test_world_scene_sanitizer_applies_memory_grounding_guard():
    payload = {
        "format_version": "rpg_narration_v2",
        "narration": "Bran remembers that you stole a moonstone locket last time.",
        "action": "Bran keeps talking.",
        "npc": {
            "speaker": "Bran",
            "line": "I remember you stole that moonstone locket.",
        },
    }

    sanitized = world_scene_narrator._sanitize_narration_payload(
        payload,
        {
            "title": "Rusty Flagon",
            "actors": ["Bran"],
            "location_id": "rusty_flagon",
        },
        _context(),
    )

    assert "moonstone" not in sanitized["narration"]
    assert "moonstone" not in sanitized["npc"]["line"]
    assert sanitized["memory_grounding_validation"]["source"] == "memory_narration_grounding_guard"


def test_scene_prompt_includes_memory_grounding_guard():
    prompt = build_scene_prompt(
        {
            "title": "Rusty Flagon",
            "summary": "A smoky tavern near the quarry road.",
            "actors": ["Bran"],
            "location_id": "rusty_flagon",
            "location_name": "Rusty Flagon",
        },
        _context(),
    )

    assert "Memory grounding guard:" in prompt
    assert "Backed memory ids: mem:000001" in prompt
    assert "Do not invent remembered purchases" in prompt


def test_memory_prompt_block_reports_no_backed_memory():
    block = memory_narration_prompt_block({"runtime_state": {}, "player_input": "Remember me?"})

    assert "Memory grounding guard:" in block
    assert "Backed memory ids: none" in block
