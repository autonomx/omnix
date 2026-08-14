from __future__ import annotations

from pathlib import Path

from app.gateway.content_free_diagnostics import sanitize_content_free_details

ROOT = Path(__file__).resolve().parents[3]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_live_chat_component_has_no_state_polling_or_dom_observer() -> None:
    source = _source("src/apps/web/src/features/chatbot/LiveChatPanel.tsx")
    assert "setInterval(" not in source
    assert "new MutationObserver" not in source
    assert "useLiveConversationState" in source


def test_duplex_policy_no_longer_infers_playback_from_dom() -> None:
    source = _source("src/apps/web/src/features/assistant-workspace/live-voice-duplex-gate.ts")
    assert "new MutationObserver" not in source
    assert "refreshDuplexGate" not in source
    assert ".assistant-voice-orb" not in source
    assert "handlePlaybackState" in source
    assert "liveConversationStore.getState" in source
    assert "BoundedWaveformReference" in source
    assert "compareRecentWaveforms" in source
    assert "resolveLiveVoiceDeviceKey" in source
    assert "currentDeviceKey" in source


def test_microphone_capture_policy_is_store_derived_and_buffers_finalization() -> None:
    source = _source("src/apps/web/src/features/assistant-workspace/live-voice-controller.ts")
    policy = source[source.index("function processAudioFrame"):source.index("function updateVoiceVisualizer")]
    assert "if (session.finalRequested) return" not in source
    assert "FinalizationAudioBuffer" in source
    assert "segmentedProtocolActive" in policy
    assert "stt_finalization_buffer_overflow" in source
    assert "stt_finalization_buffer_replayed" in source
    assert "liveConversationStore.getState" in source
    assert "function assistantIsSpeaking" not in source
    assert ".querySelector" not in policy
    assert ".dataset" not in policy
    assert "readCurrentAssistantDiagnosticText" in source


def test_segmented_stt_has_acknowledged_bounded_provider_owned_protocol() -> None:
    browser = _source("src/apps/web/src/features/assistant-workspace/live-voice-websocket.ts")
    server = _source("src/app/providers/stt_live_websocket.py")
    scheduler = _source("src/app/providers/stt_segment_scheduler.py")

    for event in ("audio_buffered", "finalize_queued", "result_available"):
        assert event in browser
        assert event in server
    assert "captureStartSample" in browser
    assert "primaryStartSample" in browser
    assert "absoluteSample" in browser
    assert "deduplicateSegmentBoundary" in browser
    assert "replayPendingSegments" in browser
    assert "ProviderSegmentScheduler" in server
    assert "MAX_SEGMENT_AUDIO_MS" in server
    assert "MAX_OPEN_SEGMENTS" in server
    assert "max_queued_jobs" in scheduler
    assert "max_session_jobs" in scheduler
    assert "await _scheduler_for(legacy).submit" in server
    receive_loop = server[server.index("while True:"):]
    assert "await _run_transcription" not in receive_loop


def test_initiative_policy_no_longer_reads_visible_voice_state() -> None:
    source = _source("src/apps/web/src/features/assistant-workspace/live-conversation-initiative-controller.ts")
    assert "dataset.liveVoiceStatus" not in source
    assert "dataset.voiceMode" not in source
    assert "new MutationObserver" not in source
    assert "liveConversationStore.getState" in source
    assert "presencePolicy" in source
    assert "initiative_cooldown_ms" in source


def test_listener_backchannel_policy_is_store_derived_not_dom_derived() -> None:
    source = _source("src/apps/web/src/features/assistant-workspace/live-voice-backchannel.ts")
    assert ".assistant-live-draft" not in source
    assert ".assistant-voice-transcript" not in source
    assert ".assistant-voice-orb" not in source
    assert "liveConversationStore.getState" in source
    assert "listener_backchannel_frequency" in source


def test_avatar_state_is_store_derived_not_dom_derived() -> None:
    source = _source("src/apps/web/src/features/assistant-workspace/live-avatar-presence.ts")
    assert ".assistant-live-state" not in source
    assert "data-live-voice-status" not in source
    assert "projectLegacyLiveVoiceState" not in source
    assert "liveConversationStore.getState" in source


def test_evaluation_uses_content_free_assistant_summaries() -> None:
    source = _source("src/apps/web/src/features/assistant-workspace/live-conversation-evaluation-controller.ts")
    assert "new MutationObserver" not in source
    assert "assistant-voice-transcript" not in source
    assert "assistant-live-draft" not in source
    assert "currentTranscriptText" not in source
    assert "LIVE_ASSISTANT_TURN_SUMMARY_EVENT" in source
    assert "topicFingerprint" in source
    assert "questionCount" in source
    assert "redactPersistedEvent" in source
    assert "liveConversationStore.subscribe" in source


def test_diagnostics_summarize_before_existing_redaction_boundary() -> None:
    source = _source("src/apps/web/src/features/assistant-workspace/live-call-diagnostics-client.ts")
    assert "observeAssistantDiagnostic(traceId, event, details)" in source
    assert "sanitizeDiagnosticDetails(details" in source
    assert source.index("observeAssistantDiagnostic(traceId, event, details)") < source.index(
        "sanitizeDiagnosticDetails(details"
    )
    assert "mode === 'full_local_debug' ? 'lengths_only'" in source


def test_server_diagnostics_enforce_content_free_boundary() -> None:
    tts = _source("src/app/gateway/tts_stream_diagnostics.py")
    browser_route = _source("src/app/gateway/live_voice_diagnostics_routes.py")
    assert "sanitize_content_free_details(details)" in tts
    assert "sanitize_content_free_details(item.details)" in browser_route
    assert "**item.details" not in browser_route

    sanitized = sanitize_content_free_details(
        {
            "text": "private phrase",
            "sanitized_text": "private phrase",
            "text_sha256": "dictionary-guessable",
            "text_length": 14,
            "phrase_index": 2,
            "nested": {"transcript": "secret", "latency_ms": 42},
        }
    )
    assert sanitized == {
        "text_chars": 14,
        "sanitized_text_chars": 14,
        "text_length": 14,
        "phrase_index": 2,
        "nested": {"transcript_chars": 6, "latency_ms": 42},
    }


def test_durable_payload_uses_aggregates_not_event_or_content_uploads() -> None:
    source = _source(
        "src/apps/web/src/features/assistant-workspace/live-conversation-durable-evaluation-controller.ts"
    )
    assert "snapshot().events" not in source
    assert "quality_metrics" in source
    assert "latency_summary" in source
    assert "eos_termination_counts" in source
    assert "browser_version" in source
    assert "os_version" in source
    assert "liveChatEvaluationClient.releaseGate" in source
    assert "transcript:" not in source
    assert "prompt:" not in source
    assert "pcm:" not in source


def test_release_gate_aggregates_durable_system_and_character_evidence() -> None:
    source = _source("src/app/gateway/live_chat_release_gate.py")
    aggregation = _source("src/app/gateway/live_chat_release_aggregation.py")
    routes = _source("src/app/gateway/live_chat_evaluation_routes.py")
    assert "evaluate_live_chat_release_gate_bundles" in source
    assert "metadata_records" in source
    assert "character_id" in source
    assert "durable_record_to_bundle" in aggregation
    assert '"/evaluations/release-gate"' in routes


def test_fullscreen_shell_reuses_existing_runtime_owners() -> None:
    shell = _source("src/apps/web/src/features/chatbot/LiveChatFullscreenShell.tsx")
    adapters = _source("src/apps/web/src/features/chatbot/live-chat-runtime-adapters.ts")
    controller = _source("src/apps/web/src/features/chatbot/live-chat-fullscreen-controller.ts")
    combined = "\n".join((shell, adapters, controller))
    forbidden_runtime_owners = (
        "getUserMedia(",
        "new WebSocket",
        "new Audio(",
        "AudioContext(",
        "SpeechRecognition",
        "/api/tts",
        "/api/chat/",
    )
    for forbidden in forbidden_runtime_owners:
        assert forbidden not in combined
    assert "useLiveConversationState" in shell
    assert "invokeExistingLiveCallControl" in shell
    assert "submitLiveChatMessageThroughExistingComposer" in shell
    assert "createPortal" in shell
    assert ".assistant-composer textarea" in adapters
    assert ".assistant-live-character-avatar" in adapters
    assert "requestFullscreen" in controller
    assert "exitFullscreen" in controller


def test_live_voice_final_routing_has_no_composer_dependency() -> None:
    controller = _source("src/apps/web/src/features/assistant-workspace/live-voice-controller.ts")
    coordinator = _source("src/apps/web/src/features/assistant-workspace/live-session-coordinator.ts")
    interceptor = _source("src/apps/web/src/features/assistant-workspace/live-segment-submit-interceptor.ts")
    assert "requestSubmit" not in controller
    assert ".assistant-composer" not in controller
    assert "populateComposer" not in controller
    assert "querySelector" not in coordinator
    assert "requestSubmit" not in coordinator
    assert "document.addEventListener('submit'" not in interceptor
    assert "onAcceptedFinal" in controller
    assert "routeAcceptedFinal" in controller
    assert "direct_final_routing: true" in _source("src/apps/web/src/features/assistant-workspace/live-runtime-provenance.ts")



def test_stt_final_does_not_preempt_audio_before_coordination() -> None:
    source = _source("src/apps/web/src/features/chatbot/ChatbotWorkspace.tsx")
    marker = "if (detail.stage !== 'stt_final_received') return;"
    handler = source[source.index(marker):source.index("window.addEventListener(LIVE_VOICE_PERF_EVENT", source.index(marker))]
    assert "stopAssistantResponseAudio" not in handler


def test_live_response_audio_is_call_scoped_and_owned() -> None:
    source = _source("src/apps/web/src/features/assistant-workspace/live-voice-unified-audio-controller.ts")
    assert "sessionScoped: true" in source
    assert "enqueueOutputPhrase" in source
    assert "waitForOutputItem" in source
    assert "cancelOutputItem" in source
    assert "session.finish()" not in source


def test_capture_owner_persists_direct_routing_provenance() -> None:
    source = _source("src/apps/web/src/features/assistant-workspace/live-voice-controller.ts")
    assert "live_runtime_provenance" in source
    assert "live_task_contract_acknowledged" in source
    assert "coordination_started" in source
    assert "coordination_completed" in source
    assert "currentLiveRuntimeProvenance()" in source
