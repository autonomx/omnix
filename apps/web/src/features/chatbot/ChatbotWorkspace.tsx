import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { ApiError, omnixApiClient, type ChatSession as ApiChatSession, type ProviderFacadePayload } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { WorkspacePanel } from '../../design/primitives';
import {
  AssistantWorkspaceActivityPanel,
  AssistantWorkspaceDashboardPanel,
  ToolExecutionPanel,
  createFetchSpeechServiceTransport,
  createInMemoryAssistantWorkspaceEventStore,
  createStoredAssistantWorkspaceEventStore,
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

type ChatMessage = {
  id: string;
  role: 'system' | 'user' | 'assistant' | string;
  content: string;
  created_at: string;
  metadata?: Record<string, unknown>;
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

export function ChatbotWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<AssistantView>('chats');
  const [activeUtilityPanel, setActiveUtilityPanel] = useState<UtilityPanel>('voice');
  const [audioStatus, setAudioStatus] = useState<string | null>(null);
  const [callStartedAt, setCallStartedAt] = useState<number | null>(null);
  const [callElapsedMs, setCallElapsedMs] = useState(0);
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
  const liveVoiceState = liveVoiceActive ? 'Listening' : 'Idle';
  const liveConnectionLabel = liveVoiceActive ? 'Connected' : 'Disconnected';
  const liveCallTimerLabel = formatCallDuration(callElapsedMs);

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

  function startLiveCall(): void {
    if (callStartedAt !== null) return;
    setActiveUtilityPanel('voice');
    setCallStartedAt(Date.now());
    setCallElapsedMs(0);
    setAudioStatus('Live voice call started.');
  }

  function stopLiveCall(): void {
    if (callStartedAt === null) return;
    setCallStartedAt(null);
    setCallElapsedMs(0);
    setAudioStatus('Live voice call ended.');
  }

  async function playAssistantResponseAudio(text: string): Promise<void> {
    const spokenText = text.trim();
    if (!spokenText) {
      setAudioStatus('No assistant response is ready to play.');
      return;
    }
    if (!runtimeConfig.ttsServiceUrl) {
      setAudioStatus('Configure VITE_ASSISTANT_TTS_URL to play response audio.');
      return;
    }
    try {
      setAudioStatus(runtimeConfig.ttsVoice ? `Synthesizing ${runtimeConfig.ttsVoice} voice…` : 'Synthesizing response voice…');
      const ttsClient = createTtsServiceClient({ baseUrl: runtimeConfig.ttsServiceUrl, transport: createFetchSpeechServiceTransport() });
      const response = await ttsClient.synthesizeSpeech({
        text: spokenText,
        voice: runtimeConfig.ttsVoice,
        format: 'wav',
        metadata: { source: 'chatbot_response_playback', sessionId: activeSession?.id, providerId: selectedProviderId || runtimeConfig.defaultProviderId, modelId: selectedModelId || runtimeConfig.defaultModelId },
      });
      const audio = new Audio(getSynthesizedAudioSource(response));
      await audio.play();
      setAudioStatus(runtimeConfig.ttsVoice ? 'Playing cloned response voice.' : 'Playing response voice.');
    } catch (error) {
      setAudioStatus(error instanceof Error ? error.message : 'Response audio playback failed.');
    }
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
                  <button type="button" className="assistant-composer-chip" onClick={() => void playAssistantResponseAudio(latestAssistantMessage?.content ?? '')} disabled={!latestAssistantMessage}><span>Voice</span><strong>{runtimeConfig.ttsVoice ? `Clone: ${runtimeConfig.ttsVoice}` : 'Ready'}</strong></button>
                  <button className="assistant-composer-chip" type="button" onClick={() => showAssistantView('memory')}><span>Memory</span><strong>On</strong></button>
                  <button type="button" className="assistant-composer-chip" onClick={() => { showAssistantView('tools'); setActiveUtilityPanel('tools'); }}><span>Tools</span><strong>{runtimeConfig.features.toolExecution ? `${enabledToolCount} Active` : 'Off'}</strong></button>
                  <button type="button" className="assistant-composer-chip" onClick={refreshActivityPanel}><span>Context</span><strong>{activeMessageCount > 0 ? 'Project Brief' : 'Ready'}</strong></button>
                </div>
                <label className="assistant-message-input"><span>Message</span><textarea rows={3} aria-invalid={Boolean(errors.content)} placeholder="Message Omnix Assistant..." {...register('content', { required: true })} /></label>
                <div className="assistant-composer-actions"><button type="button" className="assistant-mic-button" aria-label="Start voice input" onClick={startLiveCall}>◉</button><button aria-label={sendMutation.isPending ? 'Generating response' : 'Queue response'} className="assistant-send-button" type="submit" disabled={sendMutation.isPending}>{sendMutation.isPending ? 'Generating response…' : 'Send message'}</button></div>
              </form>
            </>
          ) : (
            <AssistantWorkspaceView activeView={activeView} chatProviders={chatProviders} enabledToolCount={enabledToolCount} modelLabel={modelLabel} providerLabel={providerLabel} runtimeConfig={runtimeConfig} toolExecutionRows={toolExecutionRows.length} onStartLiveCall={startLiveCall} onShowTools={() => setActiveUtilityPanel('tools')} />
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
              <div className="assistant-voice-controls"><button type="button" disabled={!liveVoiceActive}>Mute</button><button type="button" className={liveVoiceActive ? 'danger' : undefined} onClick={liveVoiceActive ? stopLiveCall : startLiveCall}>{liveVoiceActive ? 'End Call' : 'Start Call'}</button></div>
              <div className="assistant-voice-transcript"><div className="assistant-voice-transcript-header"><h3>Transcript</h3><button type="button">Clear</button></div>{recentMessages.length ? recentMessages.map((message) => <p key={`transcript-${message.id}`} className={message.role === 'assistant' ? 'assistant' : 'user'}><span><strong>{message.role === 'assistant' ? 'Omnix' : 'You'}</strong><time dateTime={message.created_at}>{formatMessageTime(message.created_at)}</time></span>{message.content}</p>) : <p className="muted">Voice transcript will appear here during live calls.</p>}</div>
              <div className="assistant-audio-devices"><header><h3>Audio Devices</h3><button type="button" aria-label="Audio device settings">Settings</button></header><div><span>Input</span><strong>MacBook Pro Microphone</strong><i aria-hidden="true" /></div><div><span>Output</span><strong>MacBook Pro Speakers</strong><i aria-hidden="true" /></div></div>
              <footer className="assistant-voice-status"><span>Voice Status</span><strong>{liveVoiceState}</strong></footer>
            </section>
            <section className="assistant-tool-sidebar-card" aria-labelledby="assistant-tool-execution-heading"><ToolExecutionPanel rows={toolExecutionRows} title="Tool execution" description="Review approvals and monitor tool execution results." /></section>
          </div>
          <div className="assistant-supporting-panels">
            <AssistantWorkspaceDashboardPanel input={{ workspaceName: runtimeConfig.workspaceId, projectName: runtimeConfig.projectId ?? 'Chatbot', sessionTitle: activeSession?.title ?? 'New chat', sessionMode: 'text', providerLabel, modelLabel, messageCount: activeMessageCount, contextSourceCount: activeMessageCount > 0 ? 1 : 0, memoryCount: 0, knowledgeChunkCount: 0, enabledToolCount: runtimeConfig.features.toolExecution ? 1 : 0, qualitySignals: [{ id: 'session', label: 'Conversation session is available', passed: Boolean(activeSession?.id) || !selectedSessionId, severity: 'info' }, { id: 'provider', label: 'At least one chat provider is available', passed: providerQuery.isLoading || chatProviders.length > 0, severity: 'warning' }, { id: 'messages', label: 'Conversation projection can render messages', passed: Boolean(activeSession?.messages) || !activeSession, severity: 'info' }, { id: 'event-store', label: 'Workspace events are configured for persistence', passed: runtimeConfig.features.persistedEvents, severity: 'warning' }] }} />
            <AssistantWorkspaceActivityPanel events={activityEvents} />
          </div>
        </aside>
      </div>
    </WorkspacePanel>
  );
}

function AssistantWorkspaceView({ activeView, chatProviders, enabledToolCount, modelLabel, onShowTools, onStartLiveCall, providerLabel, runtimeConfig, toolExecutionRows }: { activeView: Exclude<AssistantView, 'chats'>; chatProviders: ReturnType<typeof chatCapableProviders>; enabledToolCount: number; modelLabel: string; onShowTools: () => void; onStartLiveCall: () => void; providerLabel: string; runtimeConfig: AssistantWorkspaceRuntimeConfig; toolExecutionRows: number }) {
  if (activeView === 'voice') return <section className="assistant-view-panel" aria-label="Voice Sessions view"><p className="eyebrow">Omnix Assistant</p><h2>Voice Sessions</h2><p>Manage live calls, speech input, transcript capture, cloned voice playback, and TTS/STT connectivity for the Omnix assistant.</p><div className="platform-grid"><article><h3>Live call</h3><p>Use the right-side Live Voice panel to start a WebSocket-backed call and capture the live transcript.</p><button type="button" onClick={onStartLiveCall}>Start Call</button></article><article><h3>Cloned voice playback</h3><p>{runtimeConfig.ttsVoice ? `Active cloned voice: ${runtimeConfig.ttsVoice}` : 'Configure VITE_ASSISTANT_TTS_VOICE to select the cloned response voice.'}</p></article></div></section>;
  if (activeView === 'tools') return <AssistantToolSettingsPanel enabledToolCount={enabledToolCount} toolExecutionRows={toolExecutionRows} onShowExecutionPanel={onShowTools} />;
  if (activeView === 'memory') return <section className="assistant-view-panel" aria-label="Memory view"><p className="eyebrow">Omnix Assistant</p><h2>Memory</h2><p>Review assistant-scoped memory and what is available to future chat, voice, tool, and context assembly flows.</p><div className="platform-grid"><article><h3>Project memory</h3><p>Project-scoped memories are enabled for this assistant workspace.</p></article><article><h3>Conversation memory</h3><p>Current session events are persisted and replayable through the assistant workspace event store.</p></article></div></section>;
  return <section className="assistant-view-panel" aria-label="Settings view"><p className="eyebrow">Omnix Assistant</p><h2>Settings</h2><p>Review runtime configuration used by this assistant workspace.</p><dl className="assistant-settings-list"><div><dt>Provider</dt><dd>{providerLabel}</dd></div><div><dt>Model</dt><dd>{modelLabel}</dd></div><div><dt>Event storage</dt><dd>{runtimeConfig.features.persistedEvents ? runtimeConfig.eventStorageKey : 'In-memory only'}</dd></div><div><dt>Live assistant</dt><dd>{runtimeConfig.features.liveAssistant ? 'Enabled' : 'Disabled'}</dd></div><div><dt>Tool execution</dt><dd>{runtimeConfig.features.toolExecution ? 'Enabled' : 'Disabled'}</dd></div><div><dt>Available chat providers</dt><dd>{chatProviders.length}</dd></div></dl></section>;
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
