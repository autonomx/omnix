"""Apply the narrow CHAR-8 live-call integration to ChatbotWorkspace.

This script is intentionally exact and fails if the expected source shape moves.
It is used once on the phase branch, then removed before merge.
"""
from __future__ import annotations

from pathlib import Path

PATH = Path("apps/web/src/features/chatbot/ChatbotWorkspace.tsx")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = PATH.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "import { MemoryManagementPanel } from './MemoryManagementPanel';\n",
        "import { MemoryManagementPanel } from './MemoryManagementPanel';\n"
        "import { characterClient, type CharacterLiveCallRuntime, type LiveCallSpeechStyle } from './characterClient';\n",
        "character client import",
    )

    text = replace_once(
        text,
        "  const [assistantSettings, setAssistantSettings] = useState<AssistantSettings>(() => loadAssistantSettings(runtimeConfig));\n",
        "  const [assistantSettings, setAssistantSettings] = useState<AssistantSettings>(() => loadAssistantSettings(runtimeConfig));\n"
        "  const [liveCallRuntime, setLiveCallRuntime] = useState<CharacterLiveCallRuntime | null>(null);\n"
        "  const liveCallRuntimeRef = useRef<CharacterLiveCallRuntime | null>(null);\n",
        "live call runtime state",
    )

    text = replace_once(
        text,
        "  const activeVoiceId = assistantSettings.voiceId || runtimeConfig.ttsVoice || '';\n"
        "  const activeVoiceLabel = voiceLabelForId(activeVoiceId, voiceProfiles);\n",
        "  const configuredVoiceId = assistantSettings.voiceId || runtimeConfig.ttsVoice || '';\n"
        "  const activeVoiceId = liveCallRuntime?.voice_asset_id || configuredVoiceId;\n"
        "  const activeVoiceLabel = voiceLabelForId(activeVoiceId, voiceProfiles);\n",
        "active voice resolution",
    )

    old_start = """  async function startLiveCall(): Promise<void> {
    if (callStartedAt !== null) return;
    liveVoiceActiveRef.current = true;
    setActiveUtilityPanel('voice');
    setCallStartedAt(Date.now());
    setCallElapsedMs(0);
    await startVoiceInput();
  }
"""
    new_start = """  function currentLiveCallVoiceId(): string {
    return liveCallRuntimeRef.current?.voice_asset_id || assistantSettings.voiceId || runtimeConfig.ttsVoice || '';
  }

  function currentLiveCallSpeechStyle(): LiveCallSpeechStyle {
    return liveCallRuntimeRef.current?.speech_style ?? {
      speed: 1,
      temperature: 0.6,
      top_k: 20,
      top_p: 0.85,
      repetition_penalty: 1,
      expressiveness: 'neutral',
      emotion: 'neutral',
      interruption_style: 'balanced',
    };
  }

  function currentLiveCallDisplayName(): string {
    return liveCallRuntimeRef.current?.display_name || 'Omnix Assistant';
  }

  async function startLiveCall(): Promise<void> {
    if (callStartedAt !== null) return;
    setActiveUtilityPanel('voice');
    setAudioStatus('Preloading live-call identity, voice, and memory context…');
    try {
      let sessionId = selectedSessionId;
      if (!sessionId) {
        const personalityPrompt = createPersonalityPrompt(assistantSettings);
        const created = await omnixApiClient.createChatSession({
          title: 'Live voice call',
          provider_id: selectedProviderId || undefined,
          model_id: selectedModelId || undefined,
          system_prompt: personalityPrompt || undefined,
        });
        sessionId = created.id;
        setSelectedSessionId(sessionId);
      }
      const runtime = await characterClient.liveCallRuntime(sessionId);
      liveCallRuntimeRef.current = runtime;
      setLiveCallRuntime(runtime);
      liveVoiceActiveRef.current = true;
      setCallStartedAt(Date.now());
      setCallElapsedMs(0);
      console.info('[Omnix Voice Perf] live-call runtime preloaded', {
        sessionId,
        interactionMode: runtime.interaction_mode,
        characterId: runtime.character_id,
        profileVersion: runtime.character_profile_version,
        identityHash: runtime.effective_identity_hash,
        voiceAssetId: runtime.voice_asset_id,
        memoryRecordCount: runtime.preload.memory_record_count,
        preloadMs: runtime.preload.preload_ms,
      });
      setAudioStatus(`${runtime.display_name} call ready · preload ${Math.round(runtime.preload.preload_ms)}ms`);
      if (runtime.greeting.trim()) await playAssistantResponseAudio(runtime.greeting);
      await startVoiceInput();
    } catch (error) {
      liveVoiceActiveRef.current = false;
      liveCallRuntimeRef.current = null;
      setLiveCallRuntime(null);
      setCallStartedAt(null);
      setCallElapsedMs(0);
      setAudioStatus(error instanceof Error ? error.message : 'Live-call preload failed.');
    }
  }
"""
    text = replace_once(text, old_start, new_start, "start live call")

    text = replace_once(
        text,
        "    setCallStartedAt(null);\n    setCallElapsedMs(0);\n    setAudioStatus('Live voice call ended.');\n",
        "    setCallStartedAt(null);\n    setCallElapsedMs(0);\n"
        "    liveCallRuntimeRef.current = null;\n    setLiveCallRuntime(null);\n"
        "    setAudioStatus('Live voice call ended.');\n",
        "stop live call cleanup",
    )

    text = replace_once(
        text,
        "    const requestStartedAt = performance.now();\n    const audioContext = new AudioContextCtor({ latencyHint: 'interactive', sampleRate: STREAMING_TTS_SAMPLE_RATE });\n",
        "    const requestStartedAt = performance.now();\n"
        "    const speechStyle = currentLiveCallSpeechStyle();\n"
        "    const resolvedVoiceId = currentLiveCallVoiceId();\n"
        "    const audioContext = new AudioContextCtor({ latencyHint: 'interactive', sampleRate: STREAMING_TTS_SAMPLE_RATE });\n",
        "streaming runtime values",
    )

    text = text.replace("speaker: activeVoiceId || null,", "speaker: resolvedVoiceId || null,")
    if text.count("speaker: resolvedVoiceId || null,") < 2:
        raise RuntimeError("streaming speaker replacements were not applied")

    for old, new, label in (
        ("        temperature: 0.6,", "        temperature: speechStyle.temperature,", "temperature"),
        ("        top_k: 20,", "        top_k: speechStyle.top_k,", "top_k"),
        ("        top_p: 0.85,", "        top_p: speechStyle.top_p,", "top_p"),
        ("        repetition_penalty: 1.0,", "        repetition_penalty: speechStyle.repetition_penalty,", "repetition penalty"),
    ):
        text = replace_once(text, old, new, label)

    old_audio_source = """        const source = audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioContext.destination);
        const underrunSeconds = Math.max(0, audioContext.currentTime - nextStartAt);
        const startAt = Math.max(nextStartAt, audioContext.currentTime + STREAMING_TTS_RECOVERY_DELAY_SECONDS);
        source.start(startAt);
        playback.sources.push(source);
        nextStartAt = startAt + audioBuffer.duration;
        scheduledAudioSeconds += audioBuffer.duration;
"""
    new_audio_source = """        const source = audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.playbackRate.value = speechStyle.speed;
        source.connect(audioContext.destination);
        const underrunSeconds = Math.max(0, audioContext.currentTime - nextStartAt);
        const startAt = Math.max(nextStartAt, audioContext.currentTime + STREAMING_TTS_RECOVERY_DELAY_SECONDS);
        source.start(startAt);
        playback.sources.push(source);
        const effectiveDuration = audioBuffer.duration / speechStyle.speed;
        nextStartAt = startAt + effectiveDuration;
        scheduledAudioSeconds += effectiveDuration;
"""
    text = replace_once(text, old_audio_source, new_audio_source, "streaming playback speed")

    text = replace_once(
        text,
        "      const source = audioContext.createBufferSource();\n      source.buffer = audioBuffer;\n      source.connect(audioContext.destination);\n",
        "      const source = audioContext.createBufferSource();\n      source.buffer = audioBuffer;\n"
        "      source.playbackRate.value = currentLiveCallSpeechStyle().speed;\n"
        "      source.connect(audioContext.destination);\n",
        "decoded playback speed",
    )

    text = replace_once(
        text,
        "      audio.preload = 'auto';\n      const playing = waitForAudioElementPlaying(audio);\n",
        "      audio.preload = 'auto';\n      audio.playbackRate = currentLiveCallSpeechStyle().speed;\n"
        "      const playing = waitForAudioElementPlaying(audio);\n",
        "audio element playback speed",
    )

    text = replace_once(
        text,
        "      voice: activeVoiceId || undefined,\n      format: 'wav',\n"
        "      metadata: { source: 'chatbot_response_playback', sessionId: activeSession?.id, providerId: selectedProviderId || runtimeConfig.defaultProviderId, modelId: selectedModelId || runtimeConfig.defaultModelId },\n",
        "      voice: currentLiveCallVoiceId() || undefined,\n      format: 'wav',\n"
        "      metadata: { source: 'chatbot_response_playback', sessionId: activeSession?.id, providerId: selectedProviderId || runtimeConfig.defaultProviderId, modelId: selectedModelId || runtimeConfig.defaultModelId, speechStyle: currentLiveCallSpeechStyle(), characterId: liveCallRuntimeRef.current?.character_id, characterProfileVersion: liveCallRuntimeRef.current?.character_profile_version },\n",
        "batch TTS runtime",
    )

    text = replace_once(text, "        speaker: 'Omnix Assistant',", "        speaker: currentLiveCallDisplayName(),", "voice job speaker")
    text = text.replace("voice_id: activeVoiceId || null", "voice_id: currentLiveCallVoiceId() || null")
    if text.count("voice_id: currentLiveCallVoiceId() || null") < 2:
        raise RuntimeError("voice job voice replacements were not applied")
    text = replace_once(
        text,
        "        script_speakers: [{ name: 'Omnix Assistant', count: 1 }],\n"
        "        script_segments: [{ index: 0, speaker: 'Omnix Assistant', text }],\n"
        "        character_voice_assignments: [{ speaker: 'Omnix Assistant', voice_id: currentLiveCallVoiceId() || null, style: selectedPersonalityLabel, line_count: 1 }],\n",
        "        script_speakers: [{ name: currentLiveCallDisplayName(), count: 1 }],\n"
        "        script_segments: [{ index: 0, speaker: currentLiveCallDisplayName(), text }],\n"
        "        character_voice_assignments: [{ speaker: currentLiveCallDisplayName(), voice_id: currentLiveCallVoiceId() || null, style: liveCallRuntimeRef.current?.speech_style.expressiveness || selectedPersonalityLabel, line_count: 1 }],\n",
        "voice job character delivery",
    )

    PATH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
