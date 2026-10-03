import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, type Dispatch, type RefObject, type SetStateAction } from 'react';
import type { UseFormGetValues, UseFormSetValue } from 'react-hook-form';
import { omnixApiClient, type ChatSession as ApiChatSession } from '../../api/client';
import { openStream, statusError } from '../../api/transport';
import { liveCallPresentationStore, liveChatSubmissionGateway, liveVoiceTranscriptStore, type AssistantWorkspaceRuntimeConfig } from '../assistant-workspace';
import { characterClient, type CharacterLiveCallRuntime } from './characterClient';
import {
  CALL_TIMER_TICK_MS,
  LIVE_CALL_DIAGNOSTIC_EVENT,
  LIVE_SESSION_PROJECTION_FALLBACK_DELAY_MS,
  LIVE_VOICE_AUTO_SEND_DELAY_MS,
  LIVE_VOICE_STOP_EVENT,
  createPersonalityPrompt,
  dedicatedLiveVoiceControllerInstalled,
  liveVoiceSubmissionKey,
  mergeTranscript,
  parseChatStreamEvent,
  shouldFlushStreamedSpeechBuffer,
  unifiedLiveVoiceAudioInstalled,
  type AssistantSettings,
  type ChatMessage,
  type ChatbotFormValues,
  type UtilityPanel,
} from './chatbotWorkspaceModel';
import { useBrowserVoiceInput } from './useBrowserVoiceInput';
import type { useResponseAudio } from './useResponseAudio';
import type { VoiceTurnDiagnostics } from './useVoiceTurnDiagnostics';

type LiveVoiceCallOptions = Pick<ReturnType<typeof useResponseAudio>, 'playAssistantResponseAudio' | 'stopAssistantResponseAudio' | 'currentLiveCallSpeechStyle'>
  & Pick<VoiceTurnDiagnostics, 'voiceTurnPerformanceRef' | 'markVoiceTurnPerformance' | 'recordVoiceTurnDiagnostic'>
  & {
    runtimeConfig: AssistantWorkspaceRuntimeConfig;
    assistantSettings: AssistantSettings;
    selectedSessionId: string | null;
    setSelectedSessionId: (sessionId: string | null) => void;
    selectedProviderId: string;
    selectedModelId: string;
    setValue: UseFormSetValue<ChatbotFormValues>;
    getValues: UseFormGetValues<ChatbotFormValues>;
    setAudioStatus: Dispatch<SetStateAction<string | null>>;
    setActiveUtilityPanel: (panel: UtilityPanel) => void;
    liveVoiceActiveRef: RefObject<boolean>;
    liveCallRuntimeRef: RefObject<CharacterLiveCallRuntime | null>;
    setLiveCallRuntime: (runtime: CharacterLiveCallRuntime | null) => void;
    latestAssistantMessage: ChatMessage | undefined;
    recentMessages: ChatMessage[];
    /** Sends a typed message as a queued reply job (outside a call). */
    sendChatMessage: (values: ChatbotFormValues) => void;
  };

/**
 * Chat's live voice call: starting and ending it, sending each spoken turn
 * as a streamed reply, speaking replies, and holding the session projection
 * back until the reply's audio has played.
 */
export function useLiveVoiceCall({
  runtimeConfig,
  assistantSettings,
  selectedSessionId,
  setSelectedSessionId,
  selectedProviderId,
  selectedModelId,
  setValue,
  getValues,
  setAudioStatus,
  setActiveUtilityPanel,
  liveVoiceActiveRef,
  liveCallRuntimeRef,
  setLiveCallRuntime,
  latestAssistantMessage,
  recentMessages,
  sendChatMessage,
  playAssistantResponseAudio,
  stopAssistantResponseAudio,
  currentLiveCallSpeechStyle,
  voiceTurnPerformanceRef,
  markVoiceTurnPerformance,
  recordVoiceTurnDiagnostic,
}: LiveVoiceCallOptions) {
  const queryClient = useQueryClient();
  const [callStartedAt, setCallStartedAt] = useState<number | null>(null);
  const [callElapsedMs, setCallElapsedMs] = useState(0);
  const [clearedVoiceTranscriptMessageIds, setClearedVoiceTranscriptMessageIds] = useState<Record<string, true>>({});
  const [autoSpeakResponses, setAutoSpeakResponses] = useState(true);
  const [spokenMessageIds, setSpokenMessageIds] = useState<Record<string, true>>({});
  const streamedSpeechQueueRef = useRef<Promise<void>>(Promise.resolve());
  const liveVoiceAutoSendTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const liveVoiceSubmissionInFlightRef = useRef(false);
  const pendingLiveSessionProjectionRef = useRef<ApiChatSession | null>(null);
  const pendingLiveComposerResetRef = useRef(false);
  const pendingLiveProjectionCommitTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSubmittedVoiceTextRef = useRef('');
  const {
    voiceCaptureMode, setVoiceCaptureMode,
    liveTranscript, setLiveTranscript,
    liveInterimTranscript, setLiveInterimTranscript,
    startVoiceInput,
    stopVoiceInput,
  } = useBrowserVoiceInput({
    runtimeConfig,
    setValue,
    setAudioStatus,
    setActiveUtilityPanel,
    scheduleLiveVoiceAutoSend,
    clearLiveVoiceAutoSendTimer,
  });

  const liveVoiceActive = callStartedAt !== null;
  const liveDraftText = [liveTranscript, liveInterimTranscript].filter(Boolean).join(' ').trim();
  const visibleVoiceTranscriptMessages = recentMessages.filter((message) => !clearedVoiceTranscriptMessageIds[message.id]);

  useEffect(() => {
    liveCallPresentationStore.update({ autoSpeak: autoSpeakResponses });
    return () => liveCallPresentationStore.update({ autoSpeak: false });
  }, [autoSpeakResponses]);

  useEffect(() => {
    if (callStartedAt === null) {
      setCallElapsedMs(0);
      return undefined;
    }
    const updateElapsed = () => setCallElapsedMs(Date.now() - callStartedAt);
    updateElapsed();
    const intervalId = window.setInterval(updateElapsed, CALL_TIMER_TICK_MS);
    return () => window.clearInterval(intervalId);
  }, [callStartedAt]);

  useEffect(() => {
    return () => {
      liveVoiceActiveRef.current = false;
      clearLiveVoiceAutoSendTimer();
      dispatchLiveVoiceStop();
      stopVoiceInput();
      stopAssistantResponseAudio();
      if (pendingLiveProjectionCommitTimerRef.current !== null) {
        window.clearTimeout(pendingLiveProjectionCommitTimerRef.current);
        pendingLiveProjectionCommitTimerRef.current = null;
      }
    };
    // On unmount the call ends: the cleanup reads refs and stops audio and the microphone.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const handleDiagnostic = (event: Event) => {
      const detail = (event as CustomEvent<{ event?: unknown }>).detail;
      if (detail?.event === 'turn_finished') commitPendingLiveSessionProjection();
    };
    window.addEventListener(LIVE_CALL_DIAGNOSTIC_EVENT, handleDiagnostic);
    return () => window.removeEventListener(LIVE_CALL_DIAGNOSTIC_EVENT, handleDiagnostic);
    // Re-subscribes when what a projection commit reads changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSpeakResponses, queryClient]);

  useEffect(() => {
    if (unifiedLiveVoiceAudioInstalled()) return;
    if (!autoSpeakResponses || !liveVoiceActive || !latestAssistantMessage || spokenMessageIds[latestAssistantMessage.id]) return;
    setSpokenMessageIds((current) => ({ ...current, [latestAssistantMessage.id]: true }));
    void playAssistantResponseAudio(latestAssistantMessage.content);
    // Speaks each new reply once, keyed by its id.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSpeakResponses, latestAssistantMessage?.id, liveVoiceActive, spokenMessageIds]);

  useEffect(() => liveChatSubmissionGateway.register(async (input) => {
    if (input.sessionId !== selectedSessionId) throw new Error('live_chat_session_mismatch');
    await sendStreamingVoiceTranscript(input.text);
    // Re-registers when what a streamed turn reads changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [selectedSessionId, selectedProviderId, selectedModelId, assistantSettings, autoSpeakResponses]);

  function commitPendingLiveSessionProjection(): void {
    if (pendingLiveProjectionCommitTimerRef.current !== null) {
      window.clearTimeout(pendingLiveProjectionCommitTimerRef.current);
      pendingLiveProjectionCommitTimerRef.current = null;
    }
    const session = pendingLiveSessionProjectionRef.current;
    if (session) {
      pendingLiveSessionProjectionRef.current = null;
      if (autoSpeakResponses) markAssistantMessagesSpoken(session);
      queryClient.setQueryData(['feature', 'chatbot', 'session', session.id], session);
    }
    if (pendingLiveComposerResetRef.current) {
      pendingLiveComposerResetRef.current = false;
      setLiveTranscript('');
      setLiveInterimTranscript('');
      setValue('content', '', {
        shouldDirty: false,
        shouldTouch: false,
        shouldValidate: false,
      });
    }
  }

  function schedulePendingLiveSessionProjection(): void {
    if (!liveVoiceActiveRef.current || pendingLiveSessionProjectionRef.current === null) return;
    if (pendingLiveProjectionCommitTimerRef.current !== null) return;
    pendingLiveProjectionCommitTimerRef.current = window.setTimeout(() => {
      pendingLiveProjectionCommitTimerRef.current = null;
      if (liveVoiceActiveRef.current) commitPendingLiveSessionProjection();
    }, LIVE_SESSION_PROJECTION_FALLBACK_DELAY_MS);
  }

  async function startLiveCall(): Promise<void> {
    if (callStartedAt !== null) return;
    setActiveUtilityPanel('voice');
    liveVoiceActiveRef.current = true;
    setCallStartedAt(Date.now());
    setCallElapsedMs(0);
    setAudioStatus('Live voice call started.');
    try {
      let sessionId = selectedSessionId;
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
          voice_speaker_id: null,
          avatar_pack: null,
          greeting: '',
          speech_style: currentLiveCallSpeechStyle(),
          read_memory: false,
          write_memory: false,
          shared_memory_access: 'none',
          memory_snapshot_id: null,
          preload: {
            profile_loaded: false,
            voice_resolved: Boolean(assistantSettings.voiceId || runtimeConfig.ttsVoice),
            voice_error: null,
            avatar_pack_loaded: false,
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
      liveCallRuntimeRef.current = runtime;
      setLiveCallRuntime(runtime);
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
      if (dedicatedLiveVoiceControllerInstalled()) {
        setVoiceCaptureMode('listening');
        setAudioStatus(`${runtime.display_name} call ready · streaming microphone active`);
      } else {
        await startVoiceInput();
      }
    } catch (error) {
      liveVoiceActiveRef.current = false;
      liveCallRuntimeRef.current = null;
      setLiveCallRuntime(null);
      setCallStartedAt(null);
      setCallElapsedMs(0);
      setAudioStatus(error instanceof Error ? error.message : 'Live-call preload failed.');
    }
  }

  function stopLiveCall(): void {
    if (callStartedAt === null) return;
    liveVoiceActiveRef.current = false;
    dispatchLiveVoiceStop();
    stopVoiceInput();
    stopAssistantResponseAudio();
    commitPendingLiveSessionProjection();
    setCallStartedAt(null);
    setCallElapsedMs(0);
    liveCallRuntimeRef.current = null;
    setLiveCallRuntime(null);
    setAudioStatus('Live voice call ended.');
    // Each streamed response already installs its authoritative session in the
    // query cache. Reconcile list/interaction projections once the latency-
    // sensitive call is over instead of competing with browser PCM delivery.
    void queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot'] });
  }

  function clearVoiceTranscript(): void {
    clearLiveVoiceAutoSendTimer();
    lastSubmittedVoiceTextRef.current = '';
    setLiveTranscript('');
    setLiveInterimTranscript('');
    setClearedVoiceTranscriptMessageIds((current) => {
      const next = { ...current };
      recentMessages.forEach((message) => {
        next[message.id] = true;
      });
      return next;
    });
    setValue('content', '', { shouldDirty: true, shouldTouch: true, shouldValidate: true });
    liveVoiceTranscriptStore.clear();
    setAudioStatus('Voice transcript cleared.');
  }

  function sendVoiceTranscript(): void {
    const content = (liveDraftText || getValues('content') || '').trim();
    void submitVoiceTranscriptContent(content, { manual: true });
  }

  async function submitVoiceTranscriptContent(content: string, { manual = false }: { manual?: boolean } = {}): Promise<void> {
    const trimmed = content.trim();
    if (manual) clearLiveVoiceAutoSendTimer();
    if (!trimmed) {
      setAudioStatus('Speak or type a message before sending voice text.');
      return;
    }
    const submissionKey = liveVoiceSubmissionKey(trimmed);
    if (liveVoiceSubmissionInFlightRef.current || submissionKey === lastSubmittedVoiceTextRef.current) return;
    lastSubmittedVoiceTextRef.current = submissionKey;
    if (liveVoiceActiveRef.current) {
      setLiveTranscript('');
      setLiveInterimTranscript('');
      setValue('content', '', { shouldDirty: false, shouldTouch: false, shouldValidate: false });
      await sendStreamingVoiceTranscript(trimmed);
      return;
    }
    sendChatMessage({ content: trimmed, providerId: selectedProviderId, modelId: selectedModelId });
  }

  function scheduleLiveVoiceAutoSend(content: string): void {
    if (!liveVoiceActiveRef.current) return;
    clearLiveVoiceAutoSendTimer();
    liveVoiceAutoSendTimerRef.current = window.setTimeout(() => {
      liveVoiceAutoSendTimerRef.current = null;
      void submitVoiceTranscriptContent(content);
    }, LIVE_VOICE_AUTO_SEND_DELAY_MS);
  }

  function clearLiveVoiceAutoSendTimer(): void {
    if (liveVoiceAutoSendTimerRef.current === null) return;
    clearTimeout(liveVoiceAutoSendTimerRef.current);
    liveVoiceAutoSendTimerRef.current = null;
  }

  async function sendStreamingVoiceTranscript(content: string): Promise<void> {
    liveVoiceSubmissionInFlightRef.current = true;
    markVoiceTurnPerformance('chatSubmitStartedAt');
    recordVoiceTurnDiagnostic('chat_submit_started', {
      input_chars: content.length,
      provider_configured: Boolean(selectedProviderId),
      model_configured: Boolean(selectedModelId),
    });
    setAudioStatus('Sending voice text.');
    const providerId = selectedProviderId || undefined;
    const modelId = selectedModelId || undefined;
    const personalityPrompt = createPersonalityPrompt(assistantSettings);
    let sessionId = selectedSessionId;
    if (!sessionId) {
      const created = await omnixApiClient.createChatSession({
        title: content.slice(0, 48) || 'New chat',
        provider_id: providerId,
        model_id: modelId,
        system_prompt: personalityPrompt || undefined,
      });
      sessionId = created.id;
      setSelectedSessionId(sessionId);
    }

    let responseText = '';
    let speechBuffer = '';
    try {
      const response = await openStream(`/api/chat/sessions/${encodeURIComponent(sessionId)}/messages/stream`, {
        body: {
          content,
          provider_id: providerId,
          model_id: modelId,
          coding_approval_policy: assistantSettings.codingApprovalPolicy,
          live_voice_turn_id: voiceTurnPerformanceRef.current?.turnId,
        },
      }).catch(statusError('Chat stream'));
      if (!response.body) throw new Error(`Chat stream failed with status ${response.status}.`);
      markVoiceTurnPerformance('chatResponseReceivedAt');
      recordVoiceTurnDiagnostic('chat_response_opened', { status: response.status });
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let pending = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        pending += decoder.decode(value, { stream: true });
        const events = pending.split(/\n\n/);
        pending = events.pop() ?? '';
        for (const eventText of events) {
          const event = parseChatStreamEvent(eventText);
          if (!event) continue;
          if (event.type === 'error') throw new Error(typeof event.message === 'string' ? event.message : 'Chat stream failed.');
          if (event.type === 'text_chunk' && typeof event.text === 'string') {
            const firstChunk = voiceTurnPerformanceRef.current?.llmFirstChunkReceivedAt === undefined;
            markVoiceTurnPerformance('llmFirstChunkReceivedAt');
            if (firstChunk) {
              recordVoiceTurnDiagnostic('llm_first_text_chunk_received', {
                text_chunk_chars: event.text.length,
              });
            }
            responseText = mergeTranscript(responseText, event.text);
            speechBuffer = mergeTranscript(speechBuffer, event.text);
            // Updating workspace state for each live token re-renders the full
            // conversation projection (often hundreds of messages) while PCM
            // frames are arriving. The call controller already owns the live
            // status surface, so keep this text-mode update off the hot path.
            if (!liveVoiceActiveRef.current) setAudioStatus('Assistant response streaming.');
            if (autoSpeakResponses && shouldFlushStreamedSpeechBuffer(speechBuffer)) {
              queueStreamedAssistantAudio(speechBuffer);
              speechBuffer = '';
            }
          }
          if (event.type === 'session' && event.session) {
            if (liveVoiceActiveRef.current) {
              // A full live session can contain hundreds of messages. Project it
              // after playback so React work cannot block arriving PCM frames.
              pendingLiveSessionProjectionRef.current = event.session;
            } else {
              if (autoSpeakResponses) markAssistantMessagesSpoken(event.session);
              queryClient.setQueryData(['feature', 'chatbot', 'session', event.session.id], event.session);
            }
          }
        }
      }
      if (liveVoiceActiveRef.current) {
        pendingLiveComposerResetRef.current = true;
        // The audio controller normally commits this projection at
        // turn_finished. Keep the chat screen correct even when that
        // controller is unavailable or audio completion is interrupted.
        schedulePendingLiveSessionProjection();
      } else {
        setLiveTranscript('');
        setLiveInterimTranscript('');
        setValue('content', '', { shouldDirty: false, shouldTouch: false, shouldValidate: false });
      }
      if (autoSpeakResponses && speechBuffer.trim()) queueStreamedAssistantAudio(speechBuffer);
      markVoiceTurnPerformance('llmCompletedAt');
      recordVoiceTurnDiagnostic('llm_stream_completed', {
        response_chars: responseText.length,
      });
      if (!liveVoiceActiveRef.current) {
        await queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot'] });
      }
      if (!liveVoiceActiveRef.current) {
        setAudioStatus(responseText ? 'Response ready.' : 'Voice text sent.');
      }
    } catch (error) {
      recordVoiceTurnDiagnostic('chat_stream_failed', {
        error_name: error instanceof Error ? error.name : 'unknown',
        error_code: error instanceof Error && error.message.trim()
          ? error.message.trim().slice(0, 240)
          : 'live_chat_stream_failed',
      });
      setAudioStatus(error instanceof Error ? error.message : 'Voice text stream failed.');
    } finally {
      liveVoiceSubmissionInFlightRef.current = false;
    }
  }

  function queueStreamedAssistantAudio(text: string): void {
    if (unifiedLiveVoiceAudioInstalled()) return;
    streamedSpeechQueueRef.current = streamedSpeechQueueRef.current
      .catch(() => undefined)
      .then(() => playAssistantResponseAudio(text));
  }

  function markAssistantMessagesSpoken(session: ApiChatSession): void {
    const assistantMessageIds = session.messages
      ?.filter((message) => message.role === 'assistant')
      .map((message) => message.id)
      .filter(Boolean) ?? [];
    if (!assistantMessageIds.length) return;
    setSpokenMessageIds((current) => {
      const next = { ...current };
      for (const messageId of assistantMessageIds) next[messageId] = true;
      return next;
    });
  }

  function dispatchLiveVoiceStop(): void {
    window.dispatchEvent(new CustomEvent(LIVE_VOICE_STOP_EVENT));
  }

  return {
    liveVoiceActive,
    callElapsedMs,
    voiceCaptureMode,
    liveDraftText,
    visibleVoiceTranscriptMessages,
    autoSpeakResponses, setAutoSpeakResponses,
    setLiveTranscript, setLiveInterimTranscript,
    startLiveCall,
    stopLiveCall,
    startVoiceInput,
    clearVoiceTranscript,
    sendVoiceTranscript,
    submitVoiceTranscriptContent,
  };
}
