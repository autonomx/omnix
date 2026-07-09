"""Apply the narrow CHAR-8 system-session runtime fallback to ChatbotWorkspace."""
from pathlib import Path

path = Path("apps/web/src/features/chatbot/ChatbotWorkspace.tsx")
text = path.read_text(encoding="utf-8")
old = """      let sessionId = selectedSessionId;
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
"""
new = """      let sessionId = selectedSessionId;
      let createdSystemSession = false;
      if (!sessionId) {
        const personalityPrompt = createPersonalityPrompt(assistantSettings);
        const created = await omnixApiClient.createChatSession({
          title: 'Live voice call',
          provider_id: selectedProviderId || undefined,
          model_id: selectedModelId || undefined,
          system_prompt: personalityPrompt || undefined,
        });
        sessionId = created.id;
        createdSystemSession = true;
        setSelectedSessionId(sessionId);
      }
      let runtime: CharacterLiveCallRuntime;
      try {
        runtime = await characterClient.liveCallRuntime(sessionId);
      } catch (runtimeError) {
        if (!createdSystemSession) throw runtimeError;
        runtime = {
          session_id: sessionId,
          interaction_mode: 'system',
          display_name: 'System Assistant',
          character_id: null,
          character_profile_version: null,
          effective_identity_hash: null,
          voice_asset_id: assistantSettings.voiceId || runtimeConfig.ttsVoice || null,
          greeting: '',
          speech_style: currentLiveCallSpeechStyle(),
          read_memory: false,
          write_memory: false,
          shared_memory_access: 'none',
          memory_snapshot_id: null,
          preload: {
            profile_loaded: false,
            voice_resolved: Boolean(assistantSettings.voiceId || runtimeConfig.ttsVoice),
            memory_snapshot_loaded: false,
            memory_record_count: 0,
            preload_ms: 0,
            resolved_at: new Date().toISOString(),
          },
        };
        console.info('[Omnix Voice Perf] live-call runtime endpoint unavailable for new system session; using neutral fallback', {
          sessionId,
          reason: runtimeError instanceof Error ? runtimeError.message : 'runtime unavailable',
        });
      }
"""
if text.count(old) != 1:
    raise RuntimeError(f"expected one live-call preload block, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
