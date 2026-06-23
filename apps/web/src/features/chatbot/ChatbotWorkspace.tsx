import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { ApiError, omnixApiClient, type ProviderFacadePayload } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { WorkspacePanel } from '../../design/primitives';
import {
  AssistantWorkspaceActivityPanel,
  AssistantWorkspaceDashboardPanel,
  createInMemoryAssistantWorkspaceEventStore,
  createStoredAssistantWorkspaceEventStore,
  type AssistantWorkspaceEvent,
  type AssistantWorkspaceEventStore,
  type AssistantWorkspaceEventStoreFilter,
  type AssistantWorkspaceEventStorage,
  type AssistantWorkspaceRuntimeConfig,
} from '../assistant-workspace';
import { createChatbotActivityEvents, createChatbotFailureEvent } from '../assistant-workspace/chatbot-activity';
import { createAssistantWorkspaceRuntimeConfig } from '../assistant-workspace/runtime-config';

interface ChatbotFormValues {
  content: string;
  providerId: string;
  modelId: string;
}

const assistantSidebarItems = [
  { label: 'Chats', route: '/chatbot', icon: '▣' },
  { label: 'Voice Sessions', route: '/voice', icon: '◉' },
  { label: 'Tools', route: '/providers', icon: '⚒' },
  { label: 'Memory', route: '/assets', icon: '▦' },
  { label: 'Settings', route: '/settings', icon: '⚙' },
] as const;
const pinnedItems = ['Product Roadmap Q2', 'Marketing Strategy', 'Customer Interview Prep'];
const recentItems: Array<{ title: string; time: string; active?: boolean }> = [
  { title: 'Hey! How are you today?', time: '10:24 AM', active: true },
  { title: 'Write a project update email', time: 'Yesterday' },
  { title: 'Explain quantum computing', time: 'Yesterday' },
  { title: 'Brainstorm startup ideas', time: 'May 10' },
  { title: 'Summarize meeting notes', time: 'May 9' },
  { title: 'Design a landing page', time: 'May 8' },
  { title: 'Budget planning 2025', time: 'May 7' },
] as const;

export function ChatbotWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const messageLogRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();
  const runtimeConfig = useMemo(() => createAssistantWorkspaceRuntimeConfig(), []);
  const eventStore = useMemo(() => createChatbotWorkspaceEventStore(runtimeConfig), [runtimeConfig]);
  const [activityEvents, setActivityEvents] = useState<AssistantWorkspaceEvent[]>(() =>
    eventStore.list(createWorkspaceEventFilter(runtimeConfig)),
  );
  const providerQuery = useQuery({
    queryKey: ['platform', 'providers'],
    queryFn: () => omnixApiClient.listProviders(),
  });
  const sessionsQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'sessions'],
    queryFn: () => omnixApiClient.listChatSessions(),
  });
  const sessionQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'session', selectedSessionId],
    queryFn: () => omnixApiClient.getChatSession(selectedSessionId ?? ''),
    enabled: Boolean(selectedSessionId),
  });
  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<ChatbotFormValues>({
    defaultValues: {
      content: '',
      providerId: runtimeConfig.defaultProviderId ?? '',
      modelId: runtimeConfig.defaultModelId ?? '',
    },
  });
  const selectedProviderId = watch('providerId');
  const selectedModelId = watch('modelId');
  const providerPayload = providerQuery.data;
  const chatProviders = useMemo(() => chatCapableProviders(providerPayload), [providerPayload]);
  const chatModels = useMemo(() => chatCapableModels(providerPayload, selectedProviderId), [providerPayload, selectedProviderId]);

  useEffect(() => {
    if (!selectedSessionId && sessionsQuery.data?.sessions[0]) {
      setSelectedSessionId(sessionsQuery.data.sessions[0].id);
    }
  }, [selectedSessionId, sessionsQuery.data]);

  const sendMutation = useMutation({
    mutationFn: async (values: ChatbotFormValues) => {
      const providerId = values.providerId || undefined;
      const modelId = values.modelId || undefined;
      let sessionId = selectedSessionId;

      if (!sessionId) {
        const created = await omnixApiClient.createChatSession({
          title: values.content.slice(0, 48) || 'New chat',
          provider_id: providerId,
          model_id: modelId,
        });
        sessionId = created.id;
        setSelectedSessionId(sessionId);
      }

      return omnixApiClient.sendChatMessage(sessionId, {
        content: values.content,
        provider_id: providerId,
        model_id: modelId,
      });
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

  useEffect(() => {
    const messageLog = messageLogRef.current;
    if (!messageLog) return;

    messageLog.scrollTop = messageLog.scrollHeight;
  }, [activeSession?.id, activeSession?.messages?.length]);

  useEffect(() => {
    const filter = createWorkspaceEventFilter(runtimeConfig, activeSession?.id);
    const currentEvents = eventStore.list(filter);
    const currentEventIds = new Set(currentEvents.map((event) => event.id));
    const sessionEvents = createChatbotActivityEvents(activeSession, {
      workspaceId: runtimeConfig.workspaceId,
      projectId: runtimeConfig.projectId,
    });

    for (const event of sessionEvents) {
      if (!currentEventIds.has(event.id)) {
        eventStore.append(event);
        currentEventIds.add(event.id);
      }
    }

    setActivityEvents(eventStore.list(filter));
  }, [activeSession, eventStore, runtimeConfig]);

  return (
    <WorkspacePanel className="assistant-chat-page">
      <h2 id="module-title" className="workspace-module-heading">{module.label}</h2>
      <div className="assistant-chat-layout">
        <aside className="assistant-chat-sidebar" aria-label="Chat workspace">
          <nav className="assistant-sidebar-nav" aria-label="Assistant workspace">
            {assistantSidebarItems.map((item) => (
              <a
                aria-label={`Open ${item.label} from chat panel`}
                className={item.route === '/chatbot' ? 'active' : undefined}
                href={item.route}
                key={item.label}
                title={item.label}
              >
                <span aria-hidden="true">{item.icon}</span>
                <span>{item.label}</span>
              </a>
            ))}
          </nav>

          <section className="assistant-sidebar-section" aria-labelledby="assistant-chat-pinned">
            <header>
              <h2 id="assistant-chat-pinned">Pinned</h2>
              <button type="button" aria-label="Add pinned chat">+</button>
            </header>
            <div className="assistant-sidebar-list">
              {pinnedItems.map((item) => (
                <button key={item} type="button">
                  <span aria-hidden="true">▤</span>
                  <span>{item}</span>
                  <small aria-hidden="true">◆</small>
                </button>
              ))}
            </div>
          </section>

          <section className="assistant-sidebar-section" aria-labelledby="assistant-chat-recent">
            <header>
              <h2 id="assistant-chat-recent">Recent</h2>
            </header>
            <div className="assistant-sidebar-list">
              {recentItems.map((item) => (
                <button className={item.active ? 'active' : undefined} key={item.title} type="button">
                  <span aria-hidden="true">▱</span>
                  <span>{item.title}</span>
                  <time>{item.time}</time>
                </button>
              ))}
            </div>
          </section>

          <section className="assistant-workspace-usage" aria-labelledby="assistant-chat-usage">
            <h2 id="assistant-chat-usage">Workspace Usage</h2>
            <p>42% of 100GB used</p>
            <meter min="0" max="100" value="42">42%</meter>
            <button type="button">Upgrade Plan</button>
          </section>
        </aside>

        <section className="assistant-chat-main" aria-labelledby="module-title">
          <header className="assistant-chat-header">
            <div>
              <p className="eyebrow">Current chat</p>
              <h2>{activeSession?.title ?? 'Hey! How are you today?'}</h2>
            </div>
            <div className="assistant-chat-header-actions">
              <button type="button">Share</button>
              <button type="button" aria-label="Star conversation">☆</button>
              <button type="button" aria-label="More actions">⋮</button>
            </div>
          </header>

          <div className="assistant-chat-messages" ref={messageLogRef} role="log" aria-live="polite">
            {activeSession?.messages?.length ? (
              activeSession.messages.map((message) => (
                <article key={message.id} className={`assistant-chat-message ${message.role}`}>
                  {message.role !== 'user' ? <span className="assistant-chat-avatar" aria-hidden="true" /> : null}
                  <div className="assistant-chat-bubble">
                    <header>
                      <strong>{message.role === 'assistant' ? 'Omnix Assistant' : message.role === 'user' ? 'You' : message.role}</strong>
                      <time dateTime={message.created_at}>{formatMessageTime(message.created_at)}</time>
                    </header>
                    <p>{message.content}</p>
                    {message.role === 'assistant' ? (
                      <div className="assistant-message-actions" aria-label="Assistant message actions">
                        <button type="button" aria-label="Like response">♡</button>
                        <button type="button" aria-label="Dislike response">↯</button>
                        <button type="button" aria-label="Copy response">□</button>
                        <button type="button" aria-label="More response actions">⋮</button>
                      </div>
                    ) : null}
                  </div>
                </article>
              ))
            ) : (
              <div className="platform-empty" role="status">
                No chat messages yet.
              </div>
            )}
          </div>

          <form className="assistant-composer" onSubmit={handleSubmit((values) => sendMutation.mutate(values))}>
            <div className="assistant-suggestion-row" aria-label="Suggested prompts">
              <button type="button">Tell me a fun fact</button>
              <button type="button">Recommend a movie</button>
              <button type="button">Give me productivity tips</button>
              <button type="button">More</button>
            </div>
            <div className="assistant-composer-controls" aria-label="Conversation controls">
              <label>
                <span>Provider</span>
                <select {...register('providerId')} aria-label="Provider">
                  <option value="">Default provider</option>
                  {chatProviders.map((provider) => (
                    <option key={provider.id} value={provider.id}>
                      {provider.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Model</span>
                <select {...register('modelId')} aria-label="Model">
                  <option value="">Default model</option>
                  {chatModels.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.label}
                    </option>
                  ))}
                </select>
              </label>
              <span className="assistant-composer-chip">Voice Ready</span>
              <span className="assistant-composer-chip">Memory On</span>
              <span className="assistant-composer-chip">Tools {runtimeConfig.features.toolExecution ? '3 Active' : 'Off'}</span>
              <span className="assistant-composer-chip">Context</span>
            </div>
            <label className="assistant-message-input">
              <span>Message</span>
              <textarea
                rows={3}
                aria-invalid={Boolean(errors.content)}
                placeholder="Message Omnix Assistant..."
                {...register('content', { required: true })}
              />
            </label>
            <div className="assistant-composer-actions">
              <button type="button" className="assistant-mic-button" aria-label="Start voice input">
                ◉
              </button>
              <button
                aria-label={sendMutation.isPending ? 'Generating response' : 'Queue response'}
                className="assistant-send-button"
                type="submit"
                disabled={sendMutation.isPending}
              >
                {sendMutation.isPending ? 'Generating response…' : 'Send message'}
              </button>
            </div>
          </form>

          <div className="assistant-mode-switch" aria-label="Chat mode">
            <button type="button" className="active">Regular Chat</button>
            <button type="button">Live Voice</button>
          </div>

          <div className="assistant-inline-status" aria-live="polite">
            {errors.content ? <span role="alert">Enter a message before sending.</span> : null}
            {sendMutation.isPending ? <span role="status">Contacting the selected chat provider…</span> : null}
            {sendMutation.isError ? <span role="alert">{chatbotSubmitErrorMessage(sendMutation.error)}</span> : null}
            {sendMutation.data ? (
              <span role="status">
                {generationComplete ? 'Generation completed' : 'Generation job queued'}: {sendMutation.data.job.id}
              </span>
            ) : null}
          </div>
        </section>

        <aside className="assistant-chat-side" aria-label="Live voice and workspace activity">
          <section className="assistant-live-card">
            <header>
              <div>
                <p className="eyebrow">Live Voice</p>
              </div>
              <strong>Connected</strong>
            </header>
            <div className="assistant-live-state" aria-label="Live voice state">
              <span>Listening</span>
              <span aria-hidden="true">v</span>
            </div>
            <div className="assistant-voice-orb" aria-hidden="true">
              <span />
            </div>
            <time className="assistant-call-timer">00:01:24</time>
            <div className="assistant-voice-controls">
              <button type="button">Mute</button>
              <button type="button" className="danger">End Call</button>
            </div>
            <div className="assistant-voice-transcript">
              <div className="assistant-voice-transcript-header">
                <h3>Transcript</h3>
                <button type="button">Clear</button>
              </div>
              {recentMessages.length ? (
                recentMessages.map((message) => (
                  <p key={`transcript-${message.id}`} className={message.role === 'assistant' ? 'assistant' : 'user'}>
                    <span>
                      <strong>{message.role === 'assistant' ? 'Omnix' : 'You'}</strong>
                      <time dateTime={message.created_at}>{formatMessageTime(message.created_at)}</time>
                    </span>
                    {message.content}
                  </p>
                ))
              ) : (
                <p className="muted">Voice transcript will appear here.</p>
              )}
            </div>
            <div className="assistant-audio-devices">
              <header>
                <h3>Audio Devices</h3>
                <button type="button" aria-label="Audio device settings">Settings</button>
              </header>
              <div>
                <span>Input</span>
                <strong>MacBook Pro Microphone</strong>
                <i aria-hidden="true" />
              </div>
              <div>
                <span>Output</span>
                <strong>MacBook Pro Speakers</strong>
                <i aria-hidden="true" />
              </div>
            </div>
            <footer className="assistant-voice-status">
              <span>Voice Status</span>
              <strong>Listening</strong>
            </footer>
          </section>

          <div className="assistant-supporting-panels" aria-hidden="true">
            <AssistantWorkspaceDashboardPanel
              input={{
                workspaceName: runtimeConfig.workspaceId,
                projectName: runtimeConfig.projectId ?? 'Chatbot',
                sessionTitle: activeSession?.title ?? 'New chat',
                sessionMode: 'text',
                providerLabel,
                modelLabel,
                messageCount: activeMessageCount,
                contextSourceCount: activeMessageCount > 0 ? 1 : 0,
                memoryCount: 0,
                knowledgeChunkCount: 0,
                enabledToolCount: runtimeConfig.features.toolExecution ? 1 : 0,
                qualitySignals: [
                  {
                    id: 'session',
                    label: 'Conversation session is available',
                    passed: Boolean(activeSession?.id) || !selectedSessionId,
                    severity: 'info',
                  },
                  {
                    id: 'provider',
                    label: 'At least one chat provider is available',
                    passed: providerQuery.isLoading || chatProviders.length > 0,
                    severity: 'warning',
                  },
                  {
                    id: 'messages',
                    label: 'Conversation projection can render messages',
                    passed: Boolean(activeSession?.messages) || !activeSession,
                    severity: 'info',
                  },
                  {
                    id: 'event-store',
                    label: 'Workspace events are configured for persistence',
                    passed: runtimeConfig.features.persistedEvents,
                    severity: 'warning',
                  },
                ],
              }}
            />

            <AssistantWorkspaceActivityPanel events={activityEvents} />

            <section className="assistant-sessions-card">
              <h3>Sessions</h3>
              {sessionsQuery.data?.sessions.length ? (
                <div className="feature-list">
                  {sessionsQuery.data.sessions.map((session) => (
                    <button
                      className={session.id === selectedSessionId ? 'active' : undefined}
                      key={session.id}
                      type="button"
                      onClick={() => setSelectedSessionId(session.id)}
                    >
                      <span>{session.title}</span>
                      <small>{session.message_count} messages</small>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="platform-empty" role="status">
                  No chat sessions yet.
                </div>
              )}
            </section>
          </div>
        </aside>
      </div>
    </WorkspacePanel>
  );
}

function chatCapableProviders(payload: ProviderFacadePayload | undefined) {
  return payload?.providers.filter((provider) => provider.capabilities.includes('chat')) ?? [];
}

function chatCapableModels(payload: ProviderFacadePayload | undefined, providerId: string) {
  return (
    payload?.models.filter((model) => {
      const providerMatches = providerId ? model.provider_id === providerId : true;
      return providerMatches && model.capabilities.includes('chat');
    }) ?? []
  );
}

function selectedProviderLabel(payload: ProviderFacadePayload | undefined, providerId: string) {
  if (!providerId) return 'Default provider';
  return payload?.providers.find((provider) => provider.id === providerId)?.label ?? providerId;
}

function selectedModelLabel(payload: ProviderFacadePayload | undefined, modelId: string) {
  if (!modelId) return 'Default model';
  return payload?.models.find((model) => model.id === modelId)?.label ?? modelId;
}

function chatbotSubmitErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return `Chat request failed with status ${error.status}`;
  if (error instanceof Error) return error.message;
  return 'Chat request failed';
}

function formatMessageTime(value: string): string {
  if (value.includes('T')) return value.slice(11, 16);
  return value;
}

function createChatbotWorkspaceEventStore(config: AssistantWorkspaceRuntimeConfig): AssistantWorkspaceEventStore {
  const storage = getAssistantWorkspaceEventStorage();

  if (config.features.persistedEvents && storage) {
    return createStoredAssistantWorkspaceEventStore(storage, config.eventStorageKey);
  }

  return createInMemoryAssistantWorkspaceEventStore();
}

function appendWorkspaceEventIfMissing(
  eventStore: AssistantWorkspaceEventStore,
  event: AssistantWorkspaceEvent,
  filter: AssistantWorkspaceEventStoreFilter,
): void {
  const currentEventIds = new Set(eventStore.list(filter).map((currentEvent) => currentEvent.id));

  if (!currentEventIds.has(event.id)) {
    eventStore.append(event);
  }
}

function getAssistantWorkspaceEventStorage(): AssistantWorkspaceEventStorage | undefined {
  try {
    return typeof window === 'undefined' ? undefined : window.localStorage;
  } catch {
    return undefined;
  }
}

function createWorkspaceEventFilter(config: AssistantWorkspaceRuntimeConfig, sessionId?: string): AssistantWorkspaceEventStoreFilter {
  return {
    workspaceId: config.workspaceId,
    projectId: config.projectId,
    sessionId,
  };
}
