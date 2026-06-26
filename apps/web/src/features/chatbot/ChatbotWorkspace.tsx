import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { ApiError, omnixApiClient, type ChatSession as ApiChatSession, type JobRecord, type ProviderFacadePayload } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { WorkspacePanel } from '../../design/primitives';
import {
  AssistantWorkspaceActivityPanel,
  AssistantWorkspaceDashboardPanel,
  ToolExecutionPanel,
  createFetchSpeechServiceTransport,
  createInMemoryAssistantWorkspaceEventStore,
  createStoredAssistantWorkspaceEventStore,
  createSttServiceClient,
  createToolExecutionRows,
  createTtsServiceClient,
  type AssistantWorkspaceEvent,
  type AssistantWorkspaceEventStore,
  type AssistantWorkspaceEventStoreFilter,
  type AssistantWorkspaceEventStorage,
  type AssistantWorkspaceRuntimeConfig,
  type TtsSynthesisResponse,
} from '../assistant-workspace';
import { createChatbotActivityEvents, createChatbotFailureEvent } from '../assistant-workspace/chatbot-activity';
import { createAssistantWorkspaceRuntimeConfig } from '../assistant-workspace/runtime-config';
import { AssistantToolSettingsPanel } from './AssistantToolSettingsPanel';

interface ChatbotFormValues {
  content: string;
  providerId: string;
  modelId: string;
}

type AssistantView = 'chats' | 'voice' | 'tools' | 'memory' | 'settings';
type UtilityPanel = 'voice' | 'tools';
type VoiceCaptureMode = 'idle' | 'listening' | 'recording' | 'transcribing' | 'error';

type ChatMessage = {
  id: string;
  role: 'system' | 'user' | 'assistant' | string;
  content: string;
  created_at: string;
  metadata?: Record<string, unknown>;
};

type BrowserSpeechRecognitionAlternative = { transcript: string };
type BrowserSpeechRecognitionResult = { isFinal: boolean; 0?: BrowserSpeechRecognitionAlternative };
type BrowserSpeechRecognitionEvent = { resultIndex: number; results: { length: number; [index: number]: BrowserSpeechRecognitionResult } };
type BrowserSpeechRecognitionErrorEvent = { error?: string; message?: string };
type BrowserSpeechRecognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: BrowserSpeechRecognitionEvent) => void) | null;
  onerror: ((event: BrowserSpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
};
type BrowserSpeechRecognitionConstructor = new () => BrowserSpeechRecognition;
type SpeechRecognitionWindow = Window & { SpeechRecognition?: BrowserSpeechRecognitionConstructor; webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor };

type VoiceJobOutputRef = {
  data_url?: unknown;
  audio_url?: unknown;
  provider_fallback?: unknown;
  provider_success?: unknown;
  segments?: unknown;
};

const assistantSidebarItems: Array<{ id: AssistantView; label: string; icon: string }> = [
  { id: 'chats', label: 'Chats', icon: '▣' },
  { id: 'voice', label: 'Voice Sessions', icon: '◉' },
  { id: 'tools', label: 'Tools', icon: '⚒' },
  { id: 'memory', label: 'Memory', icon: '▦' },
  { id: 'settings', label: 'Settings', icon: '⚙' },
];

const suggestedPrompts = ['Tell me a fun fact', 'Recommend a movie', 'Give me productivity tips'] as const;
const CALL_TIMER_TICK_MS = 1_000;
const DEFAULT_SPEECH_LANGUAGE = 'en-US';

export function ChatbotWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<AssistantView>('chats');
  const [activeUtilityPanel, setActiveUtilityPanel] = useState<UtilityPanel>('voice');
  const [audioStatus, setAudioStatus] = useState<string | null>(null);
  const [callStartedAt, setCallStartedAt] = useState<number | null>(null);
  const [callElapsedMs, setCallElapsedMs] = useState(0);
  const [voiceCaptureMode, setVoiceCaptureMode] = useState<VoiceCaptureMode>('idle');
  const [liveTranscript, setLiveTranscript] = useState('');
  const [liveInterimTranscript, setLiveInterimTranscript] = useState('');
  const [autoSpeakResponses, setAutoSpeakResponses] = useState(true);
  const [spokenMessageIds, setSpokenMessageIds] = useState<Record<string, true>>({});
  const speechRecognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const recordingChunksRef = useRef<Blob[]>([]);
  const queryClient = useQueryClient();
  const runtimeConfig = useMemo(() => createAssistantWorkspaceRuntimeConfig(), []);
  const eventStore = useMemo(() => createChatbotWorkspaceEventStore(runtimeConfig), [runtimeConfig]);
  const [activityEvents, setActivityEvents] = useState<AssistantWorkspaceEvent[]>(() =>
    eventStore.list(createWorkspaceEventFilter(runtimeConfig)),
  );
  const providerQuery = useQuery({ queryKey: ['platform', 'providers'], queryFn: () => omnixApiClient.listProviders() });
  const sessionsQuery = useQuery({ queryKey: ['feature', 'chatbot', 'sessions'], queryFn: () => omnixApiClient.listChatSessions() });
  const sessionQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'session', selectedSessionId],
    queryFn: () => omnixApiClient.getChatSession(selectedSessionId ?? ''),
    enabled: Boolean(selectedSessionId),
  });
  const { register, handleSubmit, reset, setValue, watch, formState: { errors } } = useForm<ChatbotFormValues>({
    defaultValues: { content: '', providerId: runtimeConfig.defaultProviderId ?? '', modelId: runtimeConfig.defaultModelId ?? '' },
  });
  const composerContent = watch('content') ?? '';
  const selectedProviderId = watch('providerId');
  const selectedModelId = watch('modelId');
  const providerPayload = providerQuery.data;
  const chatProviders = useMemo(() => chatCapableProviders(providerPayload), [providerPayload]);
  const chatModels = useMemo(() => chatCapableModels(providerPayload, selectedProviderId), [providerPayload, selectedProviderId]);
  const chatSessions = sessionsQuery.data?.sessions ?? [];
  const pinnedSessions = useMemo(() => chatSessions.filter(isPinnedSession), [chatSessions]);

  useEffect(() => {
    if (!selectedSessionId && sessionsQuery.data?.sessions[0]) setSelectedSessionId(sessionsQuery.data.sessions[0].id);
  }, [selectedSessionId, sessionsQuery.data]);

  const sendMutation = useMutation({
    mutationFn: async (values: ChatbotFormValues) => {
      const providerId = values.providerId || undefined;
      const modelId = values.modelId || undefined;
      let sessionId = selectedSessionId;
      if (!sessionId) {
        const created = await omnixApiClient.createChatSession({ title: values.content.slice(0, 48) || 'New chat', provider_id: providerId, model_id: modelId });
        sessionId = created.id;
        setSelectedSessionId(sessionId);
      }
      return omnixApiClient.sendChatMessage(sessionId, { content: values.content, provider_id: providerId, model_id: modelId });
    },
    onSuccess: async (_result, values) => {
      reset({ content: '', providerId: values.providerId, modelId: values.modelId });
      setLiveTranscript('');
      setLiveInterimTranscript('');
      await queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot'] });
      await queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] });
    },
    onError: (error, values) => {
      const sessionId = selectedSessionId ?? undefined;
      const filter = createWorkspaceEventFilter(runtimeConfig, sessionId);
      const failureEvent = createChatbotFailureEvent({
        workspaceId: runtimeConfig.workspaceId,
        projectId: runtimeConfig.projectId,
        sessionId,
        providerId: values.providerId || runtimeConfig.defaultProviderId,
        modelId: values.modelId || runtimeConfig.defaultModelId,
        message: chatbotSubmitErrorMessage(error),
        ...(error instanceof ApiError ? { statusCode: error.status } : {}),
        submittedContent: values.content,
        createdAt: new Date().toISOString(),
      });
      appendWorkspaceEventIfMissing(eventStore, failureEvent, filter);
      setActivityEvents(eventStore.list(filter));
    },
  });

  const activeSession = sendMutation.data?.session ?? sessionQuery.data;
  const generationComplete = Boolean(sendMutation.data?.session.messages?.some((message) => message.role === 'assistant'));
  const activeMessageCount = activeSession?.messages?.length ?? 0;
  const providerLabel = selectedProviderLabel(providerPayload, selectedProviderId);
  const modelLabel = selectedModelLabel(providerPayload, selectedModelId);
  const recentMessages = activeSession?.messages?.slice(-4) ?? [];
  const latestAssistantMessage = getLatestAssistantMessage(activeSession?.messages ?? []);
  const toolExecutionRows = useMemo(() => createToolExecutionRows(activityEvents), [activityEvents]);
  const enabledToolCount = runtimeConfig.features.toolExecution ? Math.max(toolExecutionRows.length, 3) : 0;
  const liveVoiceActive = callStartedAt !== null;
  const liveVoiceState = liveVoiceActive ? voiceCaptureLabel(voiceCaptureMode) : voiceCaptureMode === 'error' ? 'Error' : 'Idle';
  const liveConnectionLabel = liveVoiceActive ? 'Connected' : 'Disconnected';
  const liveCallTimerLabel = formatCallDuration(callElapsedMs);
  const liveDraftText = [liveTranscript, liveInterimTranscript].filter(Boolean).join(' ').trim();
  const speechInputLabel = getSpeechRecognitionConstructor() ? 'Browser speech-to-text' : runtimeConfig.sttServiceUrl ? 'STT service recording' : 'No STT input configured';
  const ttsOutputLabel = runtimeConfig.ttsServiceUrl ? 'TTS service' : 'Voice Studio TTS job';

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
    const filter = createWorkspaceEventFilter(runtimeConfig, activeSession?.id);
    const currentEvents = eventStore.list(filter);
    const currentEventIds = new Set(currentEvents.map((event) => event.id));
    const sessionEvents = createChatbotActivityEvents(activeSession, { workspaceId: runtimeConfig.workspaceId, projectId: runtimeConfig.projectId });
    for (const event of sessionEvents) {
      if (!currentEventIds.has(event.id)) {
        eventStore.append(event);
        currentEventIds.add(event.id);
      }
    }
    setActivityEvents(eventStore.list(filter));
  }, [activeSession, eventStore, runtimeConfig]);

  useEffect(() => {
    return () => stopVoiceInput();
  }, []);

  useEffect(() => {
    if (!autoSpeakResponses || !liveVoiceActive || !latestAssistantMessage || spokenMessageIds[latestAssistantMessage.id]) return;
    setSpokenMessageIds((current) => ({ ...current, [latestAssistantMessage.id]: true }));
    void playAssistantResponseAudio(latestAssistantMessage.content);
  }, [autoSpeakResponses, latestAssistantMessage?.id, liveVoiceActive, spokenMessageIds]);

  function applySuggestedPrompt(prompt: string): void {
    setActiveView('chats');
    setValue('content', prompt, { shouldDirty: true, shouldTouch: true, shouldValidate: true });
  }

  function refreshActivityPanel(): void {
    setActivityEvents(eventStore.list(createWorkspaceEventFilter(runtimeConfig, activeSession?.id)));
  }

  function showAssistantView(view: AssistantView): void {
    setActiveView(view);
    if (view === 'voice') setActiveUtilityPanel('voice');
    if (view === 'tools') setActiveUtilityPanel('tools');
  }

  async function startLiveCall(): Promise<void> {
    if (callStartedAt !== null) return;
    setActiveUtilityPanel('voice');
    setCallStartedAt(Date.now());
    setCallElapsedMs(0);
    await startVoiceInput();
  }

  function stopLiveCall(): void {
    if (callStartedAt === null) return;
    stopVoiceInput();
    setCallStartedAt(null);
    setCallElapsedMs(0);
    setAudioStatus('Live voice call ended.');
  }

  async function startVoiceInput(): Promise<void> {
    setActiveUtilityPanel('voice');
    setLiveTranscript('');
    setLiveInterimTranscript('');
    const Recognition = getSpeechRecognitionConstructor();
    if (Recognition) {
      try {
        const recognition = new Recognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = DEFAULT_SPEECH_LANGUAGE;
        recognition.onresult = (event) => {
          let finalText = '';
          let interimText = '';
          for (let index = event.resultIndex; index < event.results.length; index += 1) {
            const result = event.results[index];
            const transcript = result?.[0]?.transcript?.trim() ?? '';
            if (!transcript) continue;
            if (result.isFinal) finalText = mergeTranscript(finalText, transcript);
            else interimText = mergeTranscript(interimText, transcript);
          }
          if (finalText) {
            setLiveTranscript((current) => {
              const next = mergeTranscript(current, finalText);
              setValue('content', next, { shouldDirty: true, shouldTouch: true, shouldValidate: true });
              return next;
            });
          }
          setLiveInterimTranscript(interimText);
        };
        recognition.onerror = (event) => {
          setVoiceCaptureMode('error');
          setAudioStatus(`Speech recognition failed${event.error ? `: ${event.error}` : ''}.`);
        };
        recognition.onend = () => {
          if (speechRecognitionRef.current === recognition) {
            setVoiceCaptureMode((current) => current === 'listening' ? 'idle' : current);
          }
        };
        speechRecognitionRef.current = recognition;
        recognition.start();
        setVoiceCaptureMode('listening');
        setAudioStatus('Listening. Speak and your words will appear in the message composer.');
      } catch (error) {
        setVoiceCaptureMode('error');
        setAudioStatus(error instanceof Error ? error.message : 'Speech recognition could not start.');
      }
      return;
    }
    await startSttRecordingFallback();
  }

  async function startSttRecordingFallback(): Promise<void> {
    if (!runtimeConfig.sttServiceUrl) {
      setVoiceCaptureMode('error');
      setAudioStatus('Browser speech recognition is unavailable and VITE_ASSISTANT_STT_URL is not configured.');
      return;
    }
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setVoiceCaptureMode('error');
      setAudioStatus('Browser audio recording is not available.');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      recordingChunksRef.current = [];
      mediaStreamRef.current = stream;
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) recordingChunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        const mimeType = recordingChunksRef.current[0]?.type || 'audio/webm';
        const audio = new Blob(recordingChunksRef.current, { type: mimeType });
        recordingChunksRef.current = [];
        stopMediaStream();
        void transcribeRecordedAudio(audio, mimeType);
      };
      recorder.start();
      setVoiceCaptureMode('recording');
      setAudioStatus('Recording voice input. End the call to transcribe it.');
    } catch (error) {
      setVoiceCaptureMode('error');
      setAudioStatus(error instanceof Error ? error.message : 'Could not start voice recording.');
      stopMediaStream();
    }
  }

  async function transcribeRecordedAudio(audio: Blob, mimeType: string): Promise<void> {
    if (!runtimeConfig.sttServiceUrl) return;
    try {
      setVoiceCaptureMode('transcribing');
      setAudioStatus('Transcribing recorded voice input…');
      const sttClient = createSttServiceClient({ baseUrl: runtimeConfig.sttServiceUrl, transport: createFetchSpeechServiceTransport() });
      const response = await sttClient.transcribeAudio({ audio, filename: 'chatbot-live-voice.webm', mimeType });
      const text = response.text.trim();
      if (!text) {
        setAudioStatus('No speech was detected in the recording.');
        setVoiceCaptureMode('idle');
        return;
      }
      setLiveTranscript((current) => {
        const next = mergeTranscript(current, text);
        setValue('content', next, { shouldDirty: true, shouldTouch: true, shouldValidate: true });
        return next;
      });
      setLiveInterimTranscript('');
      setVoiceCaptureMode('idle');
      setAudioStatus('Voice input transcribed into the message composer.');
    } catch (error) {
      setVoiceCaptureMode('error');
      setAudioStatus(error instanceof Error ? error.message : 'Voice transcription failed.');
    }
  }

  function stopVoiceInput(): void {
    const recognition = speechRecognitionRef.current;
    speechRecognitionRef.current = null;
    if (recognition) {
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.onend = null;
      try { recognition.stop(); } catch { recognition.abort(); }
    }
    const recorder = mediaRecorderRef.current;
    mediaRecorderRef.current = null;
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop();
    } else {
      stopMediaStream();
    }
    setLiveInterimTranscript('');
    setVoiceCaptureMode((current) => current === 'transcribing' ? current : 'idle');
  }

  function stopMediaStream(): void {
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
  }

  function clearVoiceTranscript(): void {
    setLiveTranscript('');
    setLiveInterimTranscript('');
    setValue('content', '', { shouldDirty: true, shouldTouch: true, shouldValidate: true });
    setAudioStatus('Voice transcript cleared.');
  }

  function sendVoiceTranscript(): void {
    const content = (liveDraftText || composerContent).trim();
    if (!content) {
      setAudioStatus('Speak or type a message before sending voice text.');
      return;
    }
    sendMutation.mutate({ content, providerId: selectedProviderId, modelId: selectedModelId });
  }

  async function playAssistantResponseAudio(text: string): Promise<void> {
    const spokenText = text.trim();
    if (!spokenText) {
      setAudioStatus('No assistant response is ready to play.');
      return;
    }
    try {
      setAudioStatus(runtimeConfig.ttsVoice ? `Synthesizing ${runtimeConfig.ttsVoice} voice…` : 'Synthesizing response voice…');
      const audioSource = runtimeConfig.ttsServiceUrl
        ? await synthesizeWithTtsService(spokenText)
        : await synthesizeWithVoiceJob(spokenText);
      const audio = new Audio(audioSource);
      await audio.play();
      setAudioStatus(runtimeConfig.ttsVoice ? 'Playing cloned response voice.' : 'Playing response voice.');
    } catch (error) {
      setAudioStatus(error instanceof Error ? error.message : 'Response audio playback failed.');
    }
  }

  async function synthesizeWithTtsService(text: string): Promise<string> {
    if (!runtimeConfig.ttsServiceUrl) throw new Error('TTS service URL is not configured.');
    const ttsClient = createTtsServiceClient({ baseUrl: runtimeConfig.ttsServiceUrl, transport: createFetchSpeechServiceTransport() });
    const response = await ttsClient.synthesizeSpeech({
      text,
      voice: runtimeConfig.ttsVoice,
      format: 'wav',
      metadata: { source: 'chatbot_response_playback', sessionId: activeSession?.id, providerId: selectedProviderId || runtimeConfig.defaultProviderId, modelId: selectedModelId || runtimeConfig.defaultModelId },
    });
    return getSynthesizedAudioSource(response);
  }

  async function synthesizeWithVoiceJob(text: string): Promise<string> {
    setAudioStatus('Queueing local Voice Studio TTS job…');
    const job = await omnixApiClient.createJob({
      module: 'voice',
      type: 'tts.synthesize',
      resource_class: 'gpu:tts',
      priority: 1,
      input_payload: {
        text,
        provider_id: null,
        speaker: 'Omnix Assistant',
        voice_id: runtimeConfig.ttsVoice || null,
        script_mode: 'single_speaker',
        script_speakers: [{ name: 'Omnix Assistant', count: 1 }],
        script_segments: [{ index: 0, speaker: 'Omnix Assistant', text }],
        character_voice_assignments: [{ speaker: 'Omnix Assistant', voice_id: runtimeConfig.ttsVoice || null, style: 'Conversational', line_count: 1 }],
        save_output: true,
      },
      stages: [
        { id: 'synthesize-chatbot-response', label: 'Generate chatbot response speech', resource_class: 'gpu:tts', status: 'queued' },
        { id: 'store-chatbot-response-audio', label: 'Save chatbot response audio', resource_class: 'cpu', status: 'queued' },
      ],
    }, { timeoutMs: 120_000, timeoutMessage: 'Voice synthesis timed out after 120s.' });
    await queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] });
    const source = getVoiceJobAudioSource(job);
    if (!source) throw new Error(voiceJobErrorMessage(job) || 'Voice Studio did not return playable speech audio.');
    return source;
  }

  return (
    <WorkspacePanel className="assistant-chat-page">
      <h2 id="module-title" className="workspace-module-heading">{module.label}</h2>
      <div className="assistant-chat-layout">
        <aside className="assistant-chat-sidebar" aria-label="Omnix assistant navigation">
          <nav className="assistant-sidebar-nav" aria-label="Assistant workspace">
            {assistantSidebarItems.map((item) => (
              <button aria-label={`Open ${item.label} view`} className={activeView === item.id ? 'active' : undefined} key={item.id} onClick={() => showAssistantView(item.id)} title={item.label} type="button">
                <span aria-hidden="true">{item.icon}</span>
                <span>{item.label}</span>
              </button>
            ))}
          </nav>

          <section className="assistant-sidebar-section assistant-sidebar-sessions" aria-labelledby="assistant-chat-sessions">
            <header><h2 id="assistant-chat-sessions">Sessions</h2></header>
            <div className="assistant-sidebar-list">
              {chatSessions.length ? chatSessions.map((session) => (
                <button className={session.id === selectedSessionId ? 'active' : undefined} key={session.id} type="button" onClick={() => { setSelectedSessionId(session.id); setActiveView('chats'); }}>
                  <span aria-hidden="true">▱</span>
                  <span>{sessionTitle(session)}</span>
                  <small>{session.message_count} messages</small>
                </button>
              )) : <p className="assistant-sidebar-empty">No chat sessions yet.</p>}
            </div>
          </section>

          <section className="assistant-sidebar-section" aria-labelledby="assistant-chat-pinned">
            <header><h2 id="assistant-chat-pinned">Pinned</h2><button type="button" aria-label="Add pinned chat">+</button></header>
            <div className="assistant-sidebar-list">
              {pinnedSessions.length ? pinnedSessions.map((session) => (
                <button key={session.id} type="button" onClick={() => setSelectedSessionId(session.id)}>
                  <span aria-hidden="true">▤</span><span>{sessionTitle(session)}</span><small aria-hidden="true">◆</small>
                </button>
              )) : <p className="assistant-sidebar-empty">No pinned chats yet.</p>}
            </div>
          </section>

          <section className="assistant-sidebar-section" aria-labelledby="assistant-chat-recent">
            <header><h2 id="assistant-chat-recent">Recent</h2></header>
            <div className="assistant-sidebar-list">
              {chatSessions.length ? chatSessions.map((session) => (
                <button className={session.id === selectedSessionId ? 'active' : undefined} key={`recent-${session.id}`} type="button" onClick={() => { setSelectedSessionId(session.id); setActiveView('chats'); }}>
                  <span aria-hidden="true">▱</span><span>{sessionTitle(session)}</span><time>{formatSessionTime(session)}</time>
                </button>
              )) : <p className="assistant-sidebar-empty">Recent chats appear after your first message.</p>}
            </div>
          </section>
        </aside>

        <section className="assistant-chat-main" aria-labelledby="module-title">
          {activeView === 'chats' ? (
            <>
              <header className="assistant-chat-header">
                <div><p className="eyebrow">Current chat</p><h2>{activeSession?.title ?? 'Hey! How are you today?'}</h2></div>
                <div className="assistant-chat-header-actions"><button type="button">Share</button><button type="button" aria-label="Star conversation">☆</button><button type="button" aria-label="More actions">⋮</button></div>
              </header>
              <div className="assistant-chat-messages" role="log" aria-live="polite">
                {activeSession?.messages?.length ? activeSession.messages.map((message) => (
                  <article key={message.id} className={`assistant-chat-message ${message.role}`}>
                    {message.role !== 'user' ? <span className="assistant-chat-avatar" aria-hidden="true" /> : null}
                    <div className="assistant-chat-bubble">
                      <header><strong>{message.role === 'assistant' ? 'Omnix Assistant' : message.role === 'user' ? 'You' : message.role}</strong><time dateTime={message.created_at}>{formatMessageTime(message.created_at)}</time></header>
                      <p>{message.content}</p>
                      {message.role === 'assistant' ? <div className="assistant-message-actions" aria-label="Assistant message actions"><button type="button" aria-label="Like response">♡</button><button type="button" aria-label="Dislike response">↯</button><button type="button" aria-label="Copy response">□</button><button type="button" aria-label="Play response audio" onClick={() => void playAssistantResponseAudio(message.content)}>▶</button><button type="button" aria-label="More response actions">⋮</button></div> : null}
                    </div>
                  </article>
                )) : <div className="platform-empty" role="status">No chat messages yet.</div>}
              </div>
              <form className="assistant-composer" onSubmit={handleSubmit((values) => sendMutation.mutate(values))}>
                <div className="assistant-suggestion-row" aria-label="Suggested prompts">
                  {suggestedPrompts.map((prompt) => <button key={prompt} type="button" onClick={() => applySuggestedPrompt(prompt)}>{prompt}</button>)}
                  <button type="button" onClick={() => applySuggestedPrompt('Give me more options for this conversation')}>More</button>
                </div>
                <div className="assistant-composer-controls" aria-label="Conversation controls">
                  <label><span>Provider</span><select {...register('providerId')} aria-label="Provider"><option value="">Default provider</option>{chatProviders.map((provider) => <option key={provider.id} value={provider.id}>{provider.label}</option>)}</select></label>
                  <label><span>Model</span><select {...register('modelId')} aria-label="Model"><option value="">Default model</option>{chatModels.map((model) => <option key={model.id} value={model.id}>{model.label}</option>)}</select></label>
                  <button type="button" className="assistant-composer-chip" onClick={() => void playAssistantResponseAudio(latestAssistantMessage?.content ?? '')} disabled={!latestAssistantMessage}><span>Voice</span><strong>{ttsOutputLabel}</strong></button>
                  <button className="assistant-composer-chip" type="button" onClick={() => showAssistantView('memory')}><span>Memory</span><strong>On</strong></button>
                  <button type="button" className="assistant-composer-chip" onClick={() => { showAssistantView('tools'); setActiveUtilityPanel('tools'); }}><span>Tools</span><strong>{runtimeConfig.features.toolExecution ? `${enabledToolCount} Active` : 'Off'}</strong></button>
                  <button type="button" className="assistant-composer-chip" onClick={refreshActivityPanel}><span>Context</span><strong>{activeMessageCount > 0 ? 'Project Brief' : 'Ready'}</strong></button>
                </div>
                <label className="assistant-message-input"><span>Message</span><textarea rows={3} aria-invalid={Boolean(errors.content)} placeholder="Message Omnix Assistant, or use the microphone…" {...register('content', { required: true })} /></label>
                <div className="assistant-composer-actions"><button type="button" className="assistant-mic-button" aria-label={liveVoiceActive ? 'Stop voice input' : 'Start voice input'} onClick={() => void (liveVoiceActive ? stopLiveCall() : startLiveCall())}>{liveVoiceActive ? '■' : '◉'}</button><button aria-label={sendMutation.isPending ? 'Generating response' : 'Queue response'} className="assistant-send-button" type="submit" disabled={sendMutation.isPending}>{sendMutation.isPending ? 'Generating response…' : 'Send message'}</button></div>
              </form>
            </>
          ) : (
            <AssistantWorkspaceView activeView={activeView} chatProviders={chatProviders} enabledToolCount={enabledToolCount} modelLabel={modelLabel} providerLabel={providerLabel} runtimeConfig={runtimeConfig} speechInputLabel={speechInputLabel} toolExecutionRows={toolExecutionRows.length} ttsOutputLabel={ttsOutputLabel} onStartLiveCall={startLiveCall} onShowTools={() => setActiveUtilityPanel('tools')} />
          )}
          <div className="assistant-inline-status" aria-live="polite">
            {errors.content ? <span role="alert">Enter a message before sending.</span> : null}
            {sendMutation.isPending ? <span role="status">Contacting the selected chat provider…</span> : null}
            {sendMutation.isError ? <span role="alert">{chatbotSubmitErrorMessage(sendMutation.error)}</span> : null}
            {audioStatus ? <span role="status">{audioStatus}</span> : null}
            {sendMutation.data ? <span role="status">{generationComplete ? 'Generation completed' : 'Generation job queued'}: {sendMutation.data.job.id}</span> : null}
          </div>
        </section>

        <aside className="assistant-chat-side" aria-label="Live voice, tools, and workspace activity">
          <div className="assistant-side-panel-toggle" aria-label="Assistant utility panel"><button type="button" className={activeUtilityPanel === 'voice' ? 'active' : undefined} onClick={() => setActiveUtilityPanel('voice')}>Live Voice</button><button type="button" className={activeUtilityPanel === 'tools' ? 'active' : undefined} onClick={() => setActiveUtilityPanel('tools')}>Tools</button></div>
          <div className="assistant-live-tools-grid" data-active-panel={activeUtilityPanel}>
            <section className="assistant-live-card">
              <header><div><p className="eyebrow">Live Voice</p></div><strong>{liveConnectionLabel}</strong></header>
              <div className="assistant-live-state" aria-label="Live voice state"><span>{liveVoiceState}</span><span aria-hidden="true">v</span></div>
              <div className="assistant-voice-orb" aria-hidden="true"><span /></div>
              <time className="assistant-call-timer" dateTime={`PT${Math.floor(callElapsedMs / 1000)}S`}>{liveCallTimerLabel}</time>
              <div className="assistant-voice-controls"><button type="button" onClick={clearVoiceTranscript}>Clear</button><button type="button" className={liveVoiceActive ? 'danger' : undefined} onClick={() => void (liveVoiceActive ? stopLiveCall() : startLiveCall())}>{liveVoiceActive ? 'End Call' : 'Start Call'}</button><button type="button" onClick={sendVoiceTranscript} disabled={sendMutation.isPending || !(liveDraftText || composerContent).trim()}>Send text</button></div>
              <label className="assistant-voice-toggle"><input type="checkbox" checked={autoSpeakResponses} onChange={(event) => setAutoSpeakResponses(event.currentTarget.checked)} /> Auto-speak assistant replies</label>
              <div className="assistant-live-draft" aria-live="polite"><strong>Voice draft</strong><p>{liveDraftText || 'Start Live Voice and speak. Final speech is copied into the message composer.'}</p></div>
              <div className="assistant-voice-transcript"><div className="assistant-voice-transcript-header"><h3>Transcript</h3><button type="button" onClick={clearVoiceTranscript}>Clear</button></div>{recentMessages.length ? recentMessages.map((message) => <p key={`transcript-${message.id}`} className={message.role === 'assistant' ? 'assistant' : 'user'}><span><strong>{message.role === 'assistant' ? 'Omnix' : 'You'}</strong><time dateTime={message.created_at}>{formatMessageTime(message.created_at)}</time></span>{message.content}</p>) : <p className="muted">Voice transcript will appear here during live calls.</p>}</div>
              <div className="assistant-audio-devices"><header><h3>Audio Services</h3><button type="button" onClick={() => void startVoiceInput()}>Test input</button></header><div><span>Input</span><strong>{speechInputLabel}</strong><i aria-hidden="true" /></div><div><span>Output</span><strong>{ttsOutputLabel}</strong><i aria-hidden="true" /></div></div>
              <footer className="assistant-voice-status"><span>Voice Status</span><strong>{liveVoiceState}</strong></footer>
            </section>
            <section className="assistant-tool-sidebar-card" aria-labelledby="assistant-tool-execution-heading"><ToolExecutionPanel rows={toolExecutionRows} title="Tool execution" description="Review approvals and monitor tool execution results." /></section>
          </div>
          <div className="assistant-supporting-panels">
            <AssistantWorkspaceDashboardPanel input={{ workspaceName: runtimeConfig.workspaceId, projectName: runtimeConfig.projectId ?? 'Chatbot', sessionTitle: activeSession?.title ?? 'New chat', sessionMode: liveVoiceActive ? 'voice' : 'text', providerLabel, modelLabel, messageCount: activeMessageCount, contextSourceCount: activeMessageCount > 0 ? 1 : 0, memoryCount: 0, knowledgeChunkCount: 0, enabledToolCount: runtimeConfig.features.toolExecution ? 1 : 0, qualitySignals: [{ id: 'session', label: 'Conversation session is available', passed: Boolean(activeSession?.id) || !selectedSessionId, severity: 'info' }, { id: 'provider', label: 'At least one chat provider is available', passed: providerQuery.isLoading || chatProviders.length > 0, severity: 'warning' }, { id: 'stt', label: 'Speech-to-text input is available', passed: Boolean(getSpeechRecognitionConstructor() || runtimeConfig.sttServiceUrl), severity: 'warning' }, { id: 'tts', label: 'TTS playback can use service or Voice Studio jobs', passed: true, severity: 'info' }, { id: 'messages', label: 'Conversation projection can render messages', passed: Boolean(activeSession?.messages) || !activeSession, severity: 'info' }, { id: 'event-store', label: 'Workspace events are configured for persistence', passed: runtimeConfig.features.persistedEvents, severity: 'warning' }] }} />
            <AssistantWorkspaceActivityPanel events={activityEvents} />
          </div>
        </aside>
      </div>
    </WorkspacePanel>
  );
}

function AssistantWorkspaceView({ activeView, chatProviders, enabledToolCount, modelLabel, onShowTools, onStartLiveCall, providerLabel, runtimeConfig, speechInputLabel, toolExecutionRows, ttsOutputLabel }: { activeView: Exclude<AssistantView, 'chats'>; chatProviders: ReturnType<typeof chatCapableProviders>; enabledToolCount: number; modelLabel: string; onShowTools: () => void; onStartLiveCall: () => void | Promise<void>; providerLabel: string; runtimeConfig: AssistantWorkspaceRuntimeConfig; speechInputLabel: string; toolExecutionRows: number; ttsOutputLabel: string }) {
  if (activeView === 'voice') return <section className="assistant-view-panel" aria-label="Voice Sessions view"><p className="eyebrow">Omnix Assistant</p><h2>Voice Sessions</h2><p>Use browser speech-to-text or the configured STT service to draft messages, then play assistant replies through the TTS service or local Voice Studio jobs.</p><div className="platform-grid"><article><h3>Live call</h3><p>Input: {speechInputLabel}. Output: {ttsOutputLabel}.</p><button type="button" onClick={() => void onStartLiveCall()}>Start Call</button></article><article><h3>Response playback</h3><p>{runtimeConfig.ttsVoice ? `Active voice: ${runtimeConfig.ttsVoice}` : 'Chatbot will synthesize assistant replies with the default configured voice.'}</p></article></div></section>;
  if (activeView === 'tools') return <AssistantToolSettingsPanel enabledToolCount={enabledToolCount} toolExecutionRows={toolExecutionRows} onShowExecutionPanel={onShowTools} />;
  if (activeView === 'memory') return <section className="assistant-view-panel" aria-label="Memory view"><p className="eyebrow">Omnix Assistant</p><h2>Memory</h2><p>Review assistant-scoped memory and what is available to future chat, voice, tool, and context assembly flows.</p><div className="platform-grid"><article><h3>Project memory</h3><p>Project-scoped memories are enabled for this assistant workspace.</p></article><article><h3>Conversation memory</h3><p>Current session events are persisted and replayable through the assistant workspace event store.</p></article></div></section>;
  return <section className="assistant-view-panel" aria-label="Settings view"><p className="eyebrow">Omnix Assistant</p><h2>Settings</h2><p>Review runtime configuration used by this assistant workspace.</p><dl className="assistant-settings-list"><div><dt>Provider</dt><dd>{providerLabel}</dd></div><div><dt>Model</dt><dd>{modelLabel}</dd></div><div><dt>Speech input</dt><dd>{speechInputLabel}</dd></div><div><dt>TTS output</dt><dd>{ttsOutputLabel}</dd></div><div><dt>Event storage</dt><dd>{runtimeConfig.features.persistedEvents ? runtimeConfig.eventStorageKey : 'In-memory only'}</dd></div><div><dt>Live assistant</dt><dd>{runtimeConfig.features.liveAssistant ? 'Enabled' : 'Disabled'}</dd></div><div><dt>Tool execution</dt><dd>{runtimeConfig.features.toolExecution ? 'Enabled' : 'Disabled'}</dd></div><div><dt>Available chat providers</dt><dd>{chatProviders.length}</dd></div></dl></section>;
}

function chatCapableProviders(payload: ProviderFacadePayload | undefined) { return payload?.providers.filter((provider) => provider.capabilities.includes('chat')) ?? []; }
function chatCapableModels(payload: ProviderFacadePayload | undefined, providerId: string) { return payload?.models.filter((model) => { const providerMatches = providerId ? model.provider_id === providerId : true; return providerMatches && model.capabilities.includes('chat'); }) ?? []; }
function selectedProviderLabel(payload: ProviderFacadePayload | undefined, providerId: string) { if (!providerId) return 'Default provider'; return payload?.providers.find((provider) => provider.id === providerId)?.label ?? providerId; }
function selectedModelLabel(payload: ProviderFacadePayload | undefined, modelId: string) { if (!modelId) return 'Default model'; return payload?.models.find((model) => model.id === modelId)?.label ?? modelId; }
function chatbotSubmitErrorMessage(error: unknown): string { if (error instanceof ApiError) return `Chat request failed with status ${error.status}`; if (error instanceof Error) return error.message; return 'Chat request failed'; }
function formatMessageTime(value: string): string { if (value.includes('T')) return value.slice(11, 16); return value; }
function formatCallDuration(valueMs: number): string { const totalSeconds = Math.max(0, Math.floor(valueMs / 1000)); const hours = Math.floor(totalSeconds / 3600); const minutes = Math.floor((totalSeconds % 3600) / 60); const seconds = totalSeconds % 60; return [hours, minutes, seconds].map((value) => value.toString().padStart(2, '0')).join(':'); }
function createChatbotWorkspaceEventStore(config: AssistantWorkspaceRuntimeConfig): AssistantWorkspaceEventStore { const storage = getAssistantWorkspaceEventStorage(); if (config.features.persistedEvents && storage) return createStoredAssistantWorkspaceEventStore(storage, config.eventStorageKey); return createInMemoryAssistantWorkspaceEventStore(); }
function appendWorkspaceEventIfMissing(eventStore: AssistantWorkspaceEventStore, event: AssistantWorkspaceEvent, filter: AssistantWorkspaceEventStoreFilter): void { const currentEventIds = new Set(eventStore.list(filter).map((currentEvent) => currentEvent.id)); if (!currentEventIds.has(event.id)) eventStore.append(event); }
function getAssistantWorkspaceEventStorage(): AssistantWorkspaceEventStorage | undefined { try { return typeof window === 'undefined' ? undefined : window.localStorage; } catch { return undefined; } }
function createWorkspaceEventFilter(config: AssistantWorkspaceRuntimeConfig, sessionId?: string): AssistantWorkspaceEventStoreFilter { return { workspaceId: config.workspaceId, projectId: config.projectId, sessionId }; }
function getLatestAssistantMessage(messages: ChatMessage[]): ChatMessage | undefined { return [...messages].reverse().find((message) => message.role === 'assistant' && message.content.trim()); }
function getSynthesizedAudioSource(response: TtsSynthesisResponse): string { if (response.audioUrl) return response.audioUrl; if (response.audioBase64) return `data:${response.mimeType ?? 'audio/wav'};base64,${response.audioBase64}`; throw new Error('TTS service did not return playable audio.'); }
function isPinnedSession(session: ApiChatSession): boolean { const metadata = 'metadata' in session ? (session as { metadata?: Record<string, unknown> }).metadata : undefined; return metadata?.pinned === true || metadata?.starred === true; }
function sessionTitle(session: ApiChatSession): string { return session.title?.trim() || 'Untitled chat'; }
function formatSessionTime(session: ApiChatSession): string { const timestamp = session.updated_at || session.created_at; if (!timestamp) return 'Recent'; return timestamp.includes('T') ? formatMessageTime(timestamp) : timestamp; }
function mergeTranscript(current: string, next: string): string { return [current.trim(), next.trim()].filter(Boolean).join(' ').replace(/\s+/g, ' ').trim(); }
function voiceCaptureLabel(mode: VoiceCaptureMode): string { if (mode === 'recording') return 'Recording'; if (mode === 'transcribing') return 'Transcribing'; if (mode === 'error') return 'Error'; if (mode === 'listening') return 'Listening'; return 'Ready'; }
function getSpeechRecognitionConstructor(): BrowserSpeechRecognitionConstructor | undefined { if (typeof window === 'undefined') return undefined; const speechWindow = window as SpeechRecognitionWindow; return speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition; }
function getVoiceJobAudioSource(job: JobRecord): string | null { const refs = Array.isArray(job.output_refs) ? job.output_refs : []; for (const ref of refs) { const output = ref as VoiceJobOutputRef; if (isFallbackVoiceOutput(output)) continue; if (typeof output.data_url === 'string' && output.data_url.startsWith('data:audio/')) return output.data_url; if (typeof output.audio_url === 'string' && output.audio_url.trim()) return output.audio_url; } return null; }
function isFallbackVoiceOutput(ref: VoiceJobOutputRef): boolean { if (ref.provider_fallback === true || ref.provider_success === false) return true; const segments = Array.isArray(ref.segments) ? ref.segments : []; return segments.some((segment) => { const row = segment as { provider_fallback?: unknown; provider_success?: unknown } | null; return row?.provider_fallback === true || row?.provider_success === false; }); }
function voiceJobErrorMessage(job: JobRecord): string { if (job.status !== 'failed') return ''; const error = job.error as { message?: unknown } | null | undefined; return typeof error?.message === 'string' ? error.message : 'Voice Studio TTS job failed.'; }
