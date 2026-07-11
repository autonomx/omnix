from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_live_chat_component_has_no_state_polling_or_dom_observer() -> None:
    source = _source("apps/web/src/features/chatbot/LiveChatPanel.tsx")
    assert "setInterval(" not in source
    assert "new MutationObserver" not in source
    assert "useLiveConversationState" in source


def test_duplex_policy_no_longer_infers_playback_from_dom() -> None:
    source = _source("apps/web/src/features/assistant-workspace/live-voice-duplex-gate.ts")
    assert "new MutationObserver" not in source
    assert "refreshDuplexGate" not in source
    assert "handlePlaybackState" in source
    assert "liveConversationStore.dispatch" in source


def test_initiative_policy_no_longer_reads_visible_voice_state() -> None:
    source = _source("apps/web/src/features/assistant-workspace/live-conversation-initiative-controller.ts")
    assert "dataset.liveVoiceStatus" not in source
    assert "dataset.voiceMode" not in source
    assert "new MutationObserver" not in source
    assert "liveConversationStore.getState" in source
    assert "presencePolicy" in source
    assert "initiative_cooldown_ms" in source


def test_listener_backchannel_policy_is_store_derived_not_dom_derived() -> None:
    source = _source("apps/web/src/features/assistant-workspace/live-voice-backchannel.ts")
    assert ".assistant-live-draft" not in source
    assert ".assistant-voice-transcript" not in source
    assert ".assistant-voice-orb" not in source
    assert "liveConversationStore.getState" in source
    assert "listener_backchannel_frequency" in source


def test_avatar_state_is_store_derived_not_dom_derived() -> None:
    source = _source("apps/web/src/features/assistant-workspace/live-avatar-presence.ts")
    assert ".assistant-live-state" not in source
    assert "data-live-voice-status" not in source
    assert "projectLegacyLiveVoiceState" not in source
    assert "liveConversationStore.getState" in source


def test_evaluation_no_longer_observes_or_persists_transcript_dom() -> None:
    source = _source("apps/web/src/features/assistant-workspace/live-conversation-evaluation-controller.ts")
    assert "new MutationObserver" not in source
    assert "assistant-voice-transcript" not in source
    assert "assistant-live-draft" not in source
    assert "redactPersistedEvent" in source
    assert "liveConversationStore.subscribe" in source


def test_durable_payload_uses_aggregates_not_event_or_content_uploads() -> None:
    source = _source(
        "apps/web/src/features/assistant-workspace/live-conversation-durable-evaluation-controller.ts"
    )
    assert "snapshot().events" not in source
    assert "quality_metrics" in source
    assert "latency_summary" in source
    assert "eos_termination_counts" in source
    assert "transcript:" not in source
    assert "prompt:" not in source
    assert "pcm:" not in source
