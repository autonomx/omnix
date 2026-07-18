"""Generic repair for malformed first-call NPC dialogue advisories."""
from __future__ import annotations

from functools import wraps
from typing import Any

_HOOK_SENTINEL = "_omnix_npc_dialogue_repair_hook_installed"
_PLAYER_SPEAKER_ALIASES = {"player", "you", "the player", "adventurer", "traveler"}


def install_npc_dialogue_repair_hook() -> None:
    from app.rpg.ai import semantic_action_intelligence as semantic
    from app.rpg.session import interactive_first_call_runtime as runtime

    if getattr(runtime, _HOOK_SENTINEL, False):
        return

    original_prompt = semantic.build_semantic_action_prompt
    original_normalize = semantic.normalize_semantic_action_advisory
    original_fallback = runtime._safe_dialogue_fallback_line
    original_dialogue_result = runtime.build_non_stateful_dialogue_result

    @wraps(original_prompt)
    def patched_prompt(*args: Any, **kwargs: Any) -> str:
        prompt = original_prompt(*args, **kwargs)
        return prompt + (
            "\n\nSTRICT VISIBLE RESPONSE RULES:\n"
            "- final_narration_candidate.npc.speaker must be the NPC who answers, never Player, you, narrator, scene, or system.\n"
            "- final_narration_candidate.npc.line must be the NPC's answer, not a restatement of the player's request.\n"
            "- priority_context.dialogue_resolution is authoritative when locked is true; keep that target_id even when the current utterance does not repeat the NPC's name.\n"
            "- Use priority_context.dialogue_context.recent_turns as an exact speaker/target transcript. Declarative answers, corrections, pronouns, and topic continuations may all be dialogue replies.\n"
            "- Resolve a different target only when dialogue_resolution supplies multiple candidate_target_ids and the transcript genuinely disambiguates one of them.\n"
            "- If you cannot safely produce an NPC answer, leave final_narration_candidate empty and set dialogue_gate.safe_to_display_now false.\n"
            "- Use only allowed utterance_mode and risk_domain enum values from the input lists.\n"
        )

    @wraps(original_normalize)
    def patched_normalize(advisory: dict[str, Any], candidate_action: dict[str, Any]) -> dict[str, Any]:
        normalized = original_normalize(advisory, candidate_action)
        visible = _d(normalized.get("visible_response"))
        npc = _d(visible.get("npc"))
        speaker = _s(npc.get("speaker")).strip().casefold()
        line = _s(npc.get("line")).strip()
        if speaker in _PLAYER_SPEAKER_ALIASES or _line_restates_player_input(line, normalized):
            normalized["visible_response"] = {}
            normalized["final_narration_candidate"] = {}
            gate = _d(normalized.get("direct_response_gate"))
            gate["safe_to_display_now"] = False
            flags = [str(flag) for flag in gate.get("risk_flags", []) if str(flag)]
            if "invalid_npc_visible_response" not in flags:
                flags.append("invalid_npc_visible_response")
            gate["risk_flags"] = flags
            gate["reason"] = "visible_response_rejected_player_speaker_or_restatement"
            normalized["direct_response_gate"] = gate
            normalized["dialogue_gate"] = gate
            normalized["visible_response_repaired"] = True
        return normalized

    @wraps(original_fallback)
    def patched_fallback(*, speaker: str, profile: dict[str, Any], player_input: str) -> tuple[str, str]:
        topic, line = original_fallback(speaker=speaker, profile=profile, player_input=player_input)
        if line != "Ask that plainly again, and I will answer as best I can.":
            return topic, line
        repaired_topic, repaired_line = _generic_question_fallback(
            speaker=speaker,
            profile=profile,
            player_input=player_input,
        )
        if repaired_line:
            return repaired_topic, repaired_line
        return topic, line

    @wraps(original_dialogue_result)
    def patched_dialogue_result(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = original_dialogue_result(*args, **kwargs)
        if not isinstance(result, dict) or result.get("consumed") is not True or result.get("ok") is not True:
            return result
        session = kwargs.get("session")
        runtime_state = _d(kwargs.get("runtime_state"))
        player_input = _s(kwargs.get("player_input"))
        if not isinstance(session, dict):
            return result
        try:
            from app.rpg.session.dialogue_focus import record_direct_dialogue_exchange

            turn_id = _s(result.get("turn_id"))
            if not turn_id:
                try:
                    turn_id = _s(runtime.canonical_runtime._build_turn_id(runtime_state))
                except Exception:
                    turn_id = f"turn:{int(runtime_state.get('tick', 0) or 0)}"
            record_direct_dialogue_exchange(
                session=session,
                player_input=player_input,
                result=result,
                tick=int(runtime_state.get("tick", 0) or 0),
                turn_id=turn_id,
                persist=True,
            )
        except Exception as exc:
            result["conversation_thread_record"] = {
                "recorded": False,
                "reason": "dialogue_focus_record_failed",
                "error": f"{type(exc).__name__}: {exc}",
                "source": "direct_dialogue_focus_v1",
            }
        return result

    semantic.build_semantic_action_prompt = patched_prompt
    semantic.normalize_semantic_action_advisory = patched_normalize
    runtime._safe_dialogue_fallback_line = patched_fallback
    runtime.build_non_stateful_dialogue_result = patched_dialogue_result
    setattr(runtime, _HOOK_SENTINEL, True)


def _d(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _s(value: Any) -> str:
    return str(value) if value is not None else ""


def _line_restates_player_input(line: str, advisory: dict[str, Any]) -> bool:
    line_norm = _norm(line)
    if not line_norm:
        return False
    diagnostics = _d(advisory.get("first_call_grounding_diagnostics"))
    packet = _d(diagnostics.get("turn_grounding_packet"))
    player_input = _norm(packet.get("player_input"))
    if not player_input:
        return False
    return line_norm == player_input or (player_input in line_norm and len(line_norm) <= len(player_input) + 30)


def _norm(value: Any) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", " ", _s(value).casefold()).strip()


def _generic_question_fallback(*, speaker: str, profile: dict[str, Any], player_input: str) -> tuple[str, str]:
    text = _s(player_input).casefold()
    if not ("?" in text or any(term in text for term in ("what", "why", "how", "where", "who", "tell me", "any "))):
        return "", ""

    speaker_name = _s(speaker).strip() or "I"
    profile = _d(profile)
    role = _s(profile.get("role") or profile.get("occupation") or profile.get("title")).strip()
    role_phrase = f" as {role}" if role else ""

    if any(term in text for term in ("trouble", "troubles", "problem", "problems", "concern", "concerns", "wrong", "worry", "worries")):
        return (
            "concern_inquiry",
            f"I can answer that{role_phrase}, but I will not turn guesses into facts. There have been enough concerns nearby that I would listen carefully, ask what you want to know, and separate rumor from what I have seen.",
        )
    if any(term in text for term in ("rumor", "rumour", "news", "gossip", "heard", "word")):
        return (
            "rumor_inquiry",
            f"I hear pieces of news{role_phrase}, but I trust only some of them. Ask about a person, place, or road, and I will tell you what sounds solid.",
        )
    if any(term in text for term in ("think", "thought", "opinion", "feel")):
        return (
            "opinion_question",
            f"My opinion{role_phrase} is worth only what I have lived and heard, but I can give it plainly if you name the matter.",
        )
    if any(term in text for term in ("where", "place", "road", "town", "tavern", "local")):
        return (
            "local_knowledge",
            f"I can tell you what I know of the local roads and people{role_phrase}, but I will keep it to what belongs in this place and this moment.",
        )
    if speaker_name and speaker_name != "I":
        return (
            "information_inquiry",
            f"{speaker_name} considers the question before answering from what they know, not from guesswork. Ask the part you care about most, and they will answer directly.",
        )
    return (
        "information_inquiry",
        "I can answer from what I know, but I will not invent certainty. Ask the part you care about most, and I will answer directly.",
    )
