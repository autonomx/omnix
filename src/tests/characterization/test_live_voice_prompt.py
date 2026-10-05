from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.platform.live_voice.pipeline import build_live_voice_prompt
from app.platform.live_voice.prompt import profile as live_voice_profile
from app.platform.live_voice.prompt import cache as prompt_cache
from app.platform.chat.context_budget import PromptBudget
from app.platform.live_voice.prompt.spoken_style import apply_live_voice_spoken_style
from app.platform.chat.models import ChatMessage, ChatSession
from app.conversation.contracts import PromptMemoryItem
from app.platform.live_voice.prompt import companion_context
from app.providers import service as provider_service
from tests.characterization.harness import capture

# The catalog modules this scenario characterizes (scripts/test_module.py).
MODULES = ("live-voice",)


class _ResolvedCharacterIdentity:
    interaction_mode = "character"
    assistant_identity = [
        "You are Sofia, a thoughtful character who speaks plainly and never claims real-world experiences."
    ]

    def model_dump(self, *, mode: str) -> dict[str, Any]:
        assert mode == "json"
        return {
            "interaction_mode": self.interaction_mode,
            "owner_type": "character",
            "owner_id": "character:sofia",
            "display_name": "Sofia",
            "character_id": "character:sofia",
            "character_profile_version": 3,
            "assistant_identity": list(self.assistant_identity),
            "effective_identity_hash": "sofia-identity-v3",
        }


def test_live_voice_prompt_matches_pre_refactor_golden(monkeypatch) -> None:
    memory = PromptMemoryItem(
        memory_id="memory:sofia:tea",
        content="The user prefers jasmine tea.",
        scope="character:sofia",
        category="preference",
        revision=2,
        source="character",
    )
    conversation_profile = SimpleNamespace(
        initiative_mode="gentle", emotional_attunement=0.2
    )
    current_message = ChatMessage(
        id="message:voice-current",
        role="user",
        content="Could you suggest something calming?",
        created_at="2026-09-28T16:30:00+00:00",
        metadata={
            "user_turn_id": "voice-user-turn:turn-17",
            "speech_segment_id": "voice-segment:turn-17",
        },
    )
    session = ChatSession(
        id="chat:live-voice-characterization",
        title="Sofia conversation",
        interaction_mode="character",
        character_id="character:sofia",
        character_profile_version=3,
        voice_asset_id="voice:sofia:calm",
        read_memory=True,
        write_memory=False,
        created_at="2026-09-28T16:00:00+00:00",
        updated_at="2026-09-28T16:30:00+00:00",
        messages=[
            ChatMessage(
                id="message:legacy-system",
                role="system",
                content="This legacy instruction is suppressed in character mode.",
                created_at="2026-09-28T16:00:00+00:00",
                metadata={},
            ),
            ChatMessage(
                id="message:prior-user",
                role="user",
                content="I have had a long day.",
                created_at="2026-09-28T16:10:00+00:00",
                metadata={},
            ),
            ChatMessage(
                id="message:prior-assistant",
                role="assistant",
                content="That sounds tiring. Would tea help you unwind?",
                created_at="2026-09-28T16:11:00+00:00",
                metadata={},
            ),
            current_message,
        ],
    )
    prompt_cache._reset_live_prompt_cache_for_tests()
    prompt_cache.cache_character_snapshot(
        SimpleNamespace(id="character:sofia", version=3)
    )
    monkeypatch.setattr(
        prompt_cache,
        "resolve_interaction_context",
        lambda _selection, *, character: _ResolvedCharacterIdentity(),
    )
    monkeypatch.setattr(
        provider_service,
        "get_global_system_prompt",
        lambda: "The global prompt is suppressed for character mode.",
    )
    rollout = SimpleNamespace(
        stage="characterization",
        active_initiative_enabled=False,
        memory_read_enabled=True,
        proactive_memory_enabled=False,
        paralinguistic_signals_enabled=False,
        content_free_diagnostics=lambda: {
            "stage": "characterization",
            "memory_read_enabled": True,
            "proactive_memory_enabled": False,
            "paralinguistic_signals_enabled": False,
        },
    )
    packet = SimpleNamespace(
        prompt_memory=[memory],
        sections={},
        selected_count=1,
        candidate_count=1,
        token_estimate=11,
        token_budget=800,
        build_ms=0.0,
        cache_hit=False,
        truncated=False,
        content_free_diagnostics=lambda: {
            "selected_count": 1,
            "candidate_count": 1,
            "token_estimate": 11,
            "token_budget": 800,
            "truncated": False,
        },
    )
    monkeypatch.setattr(
        companion_context,
        "resolve_prompt_memory",
        lambda _session, *, query_text, memory_service_factory: (
            [memory],
            {
                "authority": "v2",
                "memory_enabled": True,
                "approved_count": 1,
                "query_text": query_text,
            },
        ),
    )
    monkeypatch.setattr(
        companion_context,
        "load_memory_runtime_settings",
        lambda: SimpleNamespace(transcript_retention_enabled=True),
    )
    monkeypatch.setattr(companion_context, "companion_rollout_policy", lambda _settings: rollout)
    monkeypatch.setattr(
        companion_context,
        "resolve_session_memory_scope",
        lambda _session: {"scope": "character:sofia"},
    )
    monkeypatch.setattr(
        companion_context,
        "_effective_profile",
        lambda _session_id: conversation_profile,
    )
    monkeypatch.setattr(
        companion_context,
        "build_companion_context_packet",
        lambda *_args, **_kwargs: packet,
    )
    monkeypatch.setattr(companion_context, "record_memory_usage", lambda *_args: None)
    monkeypatch.setattr(
        companion_context, "record_companion_diagnostics", lambda *_args: None
    )
    monkeypatch.setattr(companion_context, "compaction_enabled", lambda: False)
    monkeypatch.setattr(
        live_voice_profile,
        "_live_voice_prompt_budget",
        lambda: PromptBudget(
            max_input_tokens=4096,
            reserved_output_tokens=512,
            memory_tokens=800,
            summary_tokens=800,
            history_tokens=0,
            external_context_tokens=512,
        ),
    )

    def scenario() -> dict[str, Any]:
        assembly, rendered = build_live_voice_prompt(
            SimpleNamespace(
                memory_service_factory=lambda: None,
                summary_repository_factory=lambda: None,
            ),
            session,
            current_message,
            [],
        )
        apply_live_voice_spoken_style(rendered)
        assembly.diagnostics["spoken_style"] = {
            "enabled": True,
            "tokens": rendered.diagnostics.section_tokens["live_voice_spoken_style"],
        }
        return {
            "character": {
                "id": session.character_id,
                "profile_version": session.character_profile_version,
                "voice_asset_id": session.voice_asset_id,
            },
            "conversation_profile": {
                "initiative_mode": conversation_profile.initiative_mode,
                "emotional_attunement": conversation_profile.emotional_attunement,
            },
            "profile": {
                "name": assembly.diagnostics["latency_profile"]["name"],
                "recent_message_limit": assembly.diagnostics["latency_profile"][
                    "recent_message_limit"
                ],
                "max_input_tokens": assembly.diagnostics["latency_profile"][
                    "max_input_tokens"
                ],
                "history_tokens": assembly.diagnostics["latency_profile"][
                    "history_tokens"
                ],
            },
            "approved_memory": [item.model_dump(mode="json") for item in assembly.approved_memory],
            "messages": [
                {"role": message.role, "content": message.content}
                for message in rendered.messages
            ],
            "diagnostics": {
                "memory": assembly.diagnostics["memory"],
                "companion_context": assembly.diagnostics["companion_context"],
                "temporal_retrieval": assembly.diagnostics["temporal_retrieval"],
                "initiative": assembly.diagnostics["initiative"],
                "paralinguistic_state": assembly.diagnostics[
                    "paralinguistic_state"
                ],
                "rollout": assembly.diagnostics["rollout"],
                "history_recall": assembly.diagnostics["history_recall"],
                "truncated_sections": rendered.diagnostics.truncated_sections,
                "estimated_tokens": rendered.diagnostics.estimated_tokens,
                "spoken_style": assembly.diagnostics["spoken_style"],
            },
        }

    capture("live-voice-prompt", scenario)
