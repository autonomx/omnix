import { Button, Group, Text, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { ApiError, omnixApiClient, type ProviderFacadePayload } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixStatusPill, OmnixTranscriptView, WorkspacePanel } from '../../design/primitives';
import { AssistantWorkspaceDashboardPanel } from '../assistant-workspace/AssistantWorkspaceDashboard';
import { createAssistantWorkspaceRuntimeConfig } from '../assistant-workspace/runtime-config';

interface ChatbotFormValues {
  content: string;
  providerId: string;
  modelId: string;
}

export function ChatbotWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const runtimeConfig = useMemo(() => createAssistantWorkspaceRuntimeConfig(), []);
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
  });

  const activeSession = sendMutation.data?.session ?? sessionQuery.data;
  const generationComplete = Boolean(sendMutation.data?.session.messages?.some((message) => message.role === 'assistant'));
  const submitStatus = sendMutation.isPending ? 'generating' : sendMutation.isError ? 'error' : generationComplete ? 'completed' : sendMutation.data?.generation_status ?? 'ready';
  const activeMessageCount = activeSession?.messages?.length ?? 0;
  const providerLabel = selectedProviderLabel(providerPayload, selectedProviderId);
  const modelLabel = selectedModelLabel(providerPayload, selectedModelId);

  return (
    <WorkspacePanel>
      <div className="workspace-heading">
        <div>
          <p className="eyebrow">Feature module</p>
          <h2 id="module-title">{module.label}</h2>
        </div>
        <code>{module.route}</code>
      </div>

      <p className="workspace-summary">{module.summary}</p>

      <div className="feature-layout">
        <section className="feature-panel">
          <Group justify="space-between" align="start">
            <div>
              <Title order={4}>Conversation</Title>
              <Text size="sm">{activeSession?.title ?? 'New chat'}</Text>
            </div>
            <OmnixStatusPill>{submitStatus}</OmnixStatusPill>
          </Group>

          {activeSession?.messages?.length ? (
            <OmnixTranscriptView messages={activeSession.messages.map((message) => ({ role: message.role, content: message.content }))} />
          ) : (
            <div className="platform-empty" role="status">
              No chat messages yet.
            </div>
          )}

          <form className="feature-form" onSubmit={handleSubmit((values) => sendMutation.mutate(values))}>
            <label>
              Provider
              <select {...register('providerId')}>
                <option value="">Default provider</option>
                {chatProviders.map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Model
              <select {...register('modelId')}>
                <option value="">Default model</option>
                {chatModels.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="feature-form-wide">
              Message
              <textarea rows={4} aria-invalid={Boolean(errors.content)} {...register('content', { required: true })} />
            </label>
            <Button className="feature-form-action" type="submit" disabled={sendMutation.isPending} loading={sendMutation.isPending}>
              {sendMutation.isPending ? 'Generating response…' : 'Send message'}
            </Button>
          </form>

          {errors.content ? (
            <div className="platform-empty" role="alert">
              Enter a message before sending.
            </div>
          ) : null}

          {sendMutation.isPending ? (
            <div className="feature-job-link" role="status" aria-live="polite">
              Contacting the selected chat provider…
            </div>
          ) : null}

          {sendMutation.isError ? (
            <div className="platform-empty" role="alert">
              {chatbotSubmitErrorMessage(sendMutation.error)}
            </div>
          ) : null}

          {sendMutation.data ? (
            <div className="feature-job-link" role="status">
              {generationComplete ? 'Generation completed' : 'Generation job queued'}: {sendMutation.data.job.id}
            </div>
          ) : null}
        </section>

        <section className="feature-panel">
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

          <Title order={4}>Sessions</Title>
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

function selectedProviderLabel(payload: ProviderFacadePayload | undefined, providerId: string): string | undefined {
  if (!providerId) {
    return undefined;
  }

  return payload?.providers.find((provider) => provider.id === providerId)?.label ?? providerId;
}

function selectedModelLabel(payload: ProviderFacadePayload | undefined, modelId: string): string | undefined {
  if (!modelId) {
    return undefined;
  }

  return payload?.models.find((model) => model.id === modelId)?.label ?? modelId;
}

function chatbotSubmitErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return `Chat request failed with status ${error.status}. Check that the gateway and selected provider are running.`;
  }

  if (error instanceof Error && error.message) {
    return `Chat request failed: ${error.message}`;
  }

  return 'Chat request failed. Check that the gateway and selected provider are running.';
}
