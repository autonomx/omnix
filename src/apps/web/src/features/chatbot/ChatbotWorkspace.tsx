import { useQuery } from '@tanstack/react-query';
import type { KeyboardEvent, UIEvent } from 'react';
import { useEffect, useMemo, useRef, useState, useLayoutEffect } from 'react';
import { useForm, useWatch, type Control } from 'react-hook-form';
import { omnixApiClient, type CodingApprovalPolicy } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { WorkspacePanel } from '../../design/primitives';
import { VirtualList } from '../../design/VirtualList';
import { AssistantContextControls, createAssistantWorkspaceRuntimeConfig, createChatbotActivityEvents, createToolExecutionRows, DesktopCompanionControls, DesktopCompanionTextSurface, DesktopShareButton, DesktopShareStatusRow, LIVE_TASK_PRESETS, liveCallPresentationStore, liveCallVoiceMode, liveCaptureLabels, startLiveVoiceCall, toggleAssistantPcmStream, toggleLiveVoiceCall, ToolExecutionPanel, useAssistantPcmStream, useLiveCallPresentation, useLiveVoiceTranscript, type AssistantWorkspaceEvent, type AssistantWorkspaceRuntimeConfig } from '../assistant-workspace';
import { AssistantToolSettingsPanel } from './AssistantToolSettingsPanel';
import { CharacterManagementPanel } from './CharacterManagementPanel';
import { ChatIdentityModeControl } from './ChatIdentityModeControl';
import { LiveChatFullscreenShell, type LiveChatMessage } from './LiveChatFullscreenShell';
import { LiveChatPanel } from './LiveChatPanel';
import { VoiceSessionEvaluationPanel } from './VoiceSessionEvaluationPanel';
import { LiveCallVisual } from './LiveCallVisual';
import { ChatSidebarSessions } from './ChatSidebarSessions';
import { Live2DZoomControl } from './Live2DZoomControl';
import { Live2DMotionControl } from './Live2DMotionControl';
import { MemoryManagementPanel } from './MemoryManagementPanel';
import { enterLiveChatFullscreen } from './live-chat-fullscreen-controller';
import { characterClient } from './characterClient';
import { ResearchProgressCard } from './ResearchProgressCard';
import { ChatMessageItem, type ChatMessageActions } from './ChatMessageItem';
import { formatMessageTime } from './chatMessageModel';
import { AssistantMessageFeedback, AssistantSettings, AssistantView, ChatMessage, ChatbotFormValues, LIVE_VOICE_INTERRUPT_EVENT, PersonalityId, VoiceProfileAsset, assistantSidebarItems, chatCapableModels, chatCapableProviders, chatbotSubmitErrorMessage, clampLiveVoiceSensitivity, codingApprovalOptions, copyTextToClipboard, createChatbotWorkspaceEventStore, createWorkspaceEventFilter, dedicatedLiveVoiceControllerInstalled, defaultAssistantSettings, formatCallDuration, formatClockTime, getLatestAssistantMessage, getSpeechRecognitionConstructor, getVoiceProfileAssets, isScrolledNearBottom, loadAssistantSettings, personalityLabel, personalityOptions, readAssistantToolReturn, saveAssistantSettings, selectedModelLabel, selectedProviderLabel, suggestedPrompts, voiceCaptureLabel, voiceLabelForId, voiceProfileId, voiceProfileLabel } from './chatbotWorkspaceModel';
import { useChatLayout } from './useChatLayout';
import { useChatAttachments } from './useChatAttachments';
import { useVoiceTurnDiagnostics } from './useVoiceTurnDiagnostics';
import { useResponseAudio } from './useResponseAudio';
import { useChatSessions } from './useChatSessions';
import { useChatJob } from './useChatJob';
import { useLiveCallRuntime } from './useLiveCallRuntime';
import { useSendChatMessage } from './useSendChatMessage';
import { useLiveVoiceCall } from './useLiveVoiceCall';

export function ChatbotWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const assistantToolReturn = useMemo(() => readAssistantToolReturn(), []);
  const {
    activeView, setActiveView,
    isChatFullscreen, setIsChatFullscreen,
    activeUtilityPanel, setActiveUtilityPanel,
    isAssistantSidebarMinimized, setIsAssistantSidebarMinimized,
    isSidePanelMinimized, setIsSidePanelMinimized,
  } = useChatLayout(assistantToolReturn.toolId);
  const {
    pastedChatImages, setPastedChatImages,
    pastedChatTextFile, setPastedChatTextFile,
    chatImageError, setChatImageError,
    handleComposerPaste,
  } = useChatAttachments();
  const [audioStatus, setAudioStatus] = useState<string | null>(null);
  const {
    selectedSessionId, setSelectedSessionId,
    sessionsQuery, sessionQuery,
    selectedSessionSummary,
    chatSessions, sessionsLoading, sessionsError,
    activeSessionLoading, activeSessionError,
    deleteSessionMutation,
    selectSidebarSession,
  } = useChatSessions({ setActiveView, setAudioStatus });
  const { setActiveChatJobId, chatJobError, setChatJobError, chatJobQuery, chatJobInProgress } = useChatJob(selectedSessionId);
  const [assistantMessageFeedback, setAssistantMessageFeedback] = useState<Record<string, AssistantMessageFeedback>>({});
  const [openMessageActionMenuId, setOpenMessageActionMenuId] = useState<string | null>(null);
  const [settingsStatus, setSettingsStatus] = useState<string | null>(null);
  const liveVoiceActiveRef = useRef(false);
  const messagesContainerRef = useRef<HTMLDivElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const lastMessageScrollKeyRef = useRef('');
  const shouldStickToLatestMessageRef = useRef(true);
  const { voiceTurnPerformanceRef, markVoiceTurnPerformance, recordVoiceTurnDiagnostic, logVoiceTurnPerformance } = useVoiceTurnDiagnostics();
  const runtimeConfig = useMemo(() => createAssistantWorkspaceRuntimeConfig(), []);
  const [assistantSettings, setAssistantSettings] = useState<AssistantSettings>(() => loadAssistantSettings(runtimeConfig));
  const eventStore = useMemo(() => createChatbotWorkspaceEventStore(runtimeConfig), [runtimeConfig]);
  const [activityEvents, setActivityEvents] = useState<AssistantWorkspaceEvent[]>(() =>
    eventStore.list(createWorkspaceEventFilter(runtimeConfig)),
  );
  const providerQuery = useQuery({ queryKey: ['platform', 'providers'], queryFn: () => omnixApiClient.listProviders() });
  const assetsQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'voice-library'],
    queryFn: async () => {
      try {
        return await omnixApiClient.listVoiceLibrary();
      } catch {
        // Older gateways do not expose the narrow route yet. Preserve the
        // compatibility path without making the aggregate catalog part of
        // the chat-history request when the direct route is available.
        return omnixApiClient.listAssets();
      }
    },
    // Voice profiles are a settings/voice concern. Defer even the narrow
    // voice-library request until chat history has settled.
    enabled: !sessionsQuery.isPending && (activeView === 'chats' || activeView === 'settings' || activeView === 'voice'),
  });
  const interactionQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'interaction', selectedSessionId],
    queryFn: () => characterClient.session(selectedSessionId ?? ''),
    // Character identity is needed by the Chat view's right rail as well as
    // the dedicated Voice view. System chats stay off this endpoint.
    enabled: Boolean(
      selectedSessionId
      && (activeView === 'voice' || selectedSessionSummary?.interaction_mode === 'character'),
    ),
  });
  const { liveCallRuntime, setLiveCallRuntime, liveCallRuntimeRef } = useLiveCallRuntime({
    selectedSessionId,
    selectedSessionSummary,
    interaction: interactionQuery.data,
    liveVoiceActiveRef,
  });
  const { register, handleSubmit, reset, setValue, getValues, watch, control, formState: { errors } } = useForm<ChatbotFormValues>({
    defaultValues: { content: '', providerId: runtimeConfig.defaultProviderId ?? '', modelId: runtimeConfig.defaultModelId ?? '' },
  });
  const { sendMutation, sendChatMessage, quickSearchProgress, pendingUserMessage } = useSendChatMessage({
    runtimeConfig,
    assistantSettings,
    selectedSessionId,
    setSelectedSessionId,
    pastedChatImages,
    pastedChatTextFile,
    setPastedChatImages,
    setPastedChatTextFile,
    setChatImageError,
    setActiveChatJobId,
    setChatJobError,
    reset,
    onSent: () => {
      setLiveTranscript('');
      setLiveInterimTranscript('');
    },
    eventStore,
    setActivityEvents,
    markVoiceTurnPerformance,
  });
  const selectedProviderId = watch('providerId');
  const selectedModelId = watch('modelId');
  const providerPayload = providerQuery.data;
  const chatProviders = useMemo(() => chatCapableProviders(providerPayload), [providerPayload]);
  const chatModels = useMemo(() => chatCapableModels(providerPayload, selectedProviderId), [providerPayload, selectedProviderId]);
  const selectedCharacterId = selectedSessionSummary?.interaction_mode === 'character'
    ? selectedSessionSummary.character_id
    : null;
  const charactersQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'characters'],
    queryFn: () => characterClient.list(),
    enabled: Boolean(selectedCharacterId && (activeView === 'chats' || activeView === 'voice')),
  });
  const selectedCharacter = charactersQuery.data?.characters.find((character) => character.id === selectedCharacterId);
  const voiceProfiles = useMemo(() => getVoiceProfileAssets(assetsQuery.data), [assetsQuery.data]);

  useEffect(() => {
    if (activeView !== 'settings') return;
    void import('./assistantSettingsBootstrap')
      .then(({ bootstrapCentralAssistantSettings }) => bootstrapCentralAssistantSettings())
      .then(() => setAssistantSettings(loadAssistantSettings(runtimeConfig)))
      .catch(() => undefined);
  }, [activeView, runtimeConfig]);

  const activeSession = selectFreshChatSession(sendMutation.data?.session, sessionQuery.data);
  const activeMessageCount = activeSession?.messages?.length ?? 0;
  const providerLabel = selectedProviderLabel(providerPayload, selectedProviderId);
  const modelLabel = selectedModelLabel(providerPayload, selectedModelId);
  const recentMessages = activeSession?.messages?.slice(-4) ?? [];
  const sessionMessages = activeSession?.messages;
  const displayedMessages = useMemo(
    () => pendingUserMessage ? [...(sessionMessages ?? []), pendingUserMessage] : sessionMessages ?? [],
    [sessionMessages, pendingUserMessage],
  );
  const displayedSessionId = activeSession?.id ?? selectedSessionId ?? 'pending-session';
  const liveVoiceTranscript = useLiveVoiceTranscript();
  const livePresentation = useLiveCallPresentation();
  const pcmStream = useAssistantPcmStream();
  // Message buttons call the latest handlers through one stable object, so messages stay memoized.
  const messageActionsRef = useRef<ChatMessageActions | null>(null);
  const messageActions = useMemo<ChatMessageActions>(() => ({
    toggleFeedback: (messageId, feedback) => messageActionsRef.current?.toggleFeedback(messageId, feedback),
    copy: (message) => messageActionsRef.current?.copy(message),
    play: (text) => messageActionsRef.current?.play(text),
    stream: (message) => messageActionsRef.current?.stream(message),
    toggleMenu: (messageId) => messageActionsRef.current?.toggleMenu(messageId),
    closeMenu: () => messageActionsRef.current?.closeMenu(),
    continueFrom: (message) => messageActionsRef.current?.continueFrom(message),
    openTools: () => messageActionsRef.current?.openTools(),
  }), []);
  // Immersive Live Chat shows the chat when it has messages, the live transcript otherwise.
  const liveChatMessages = useMemo<LiveChatMessage[]>(() => {
    if (displayedMessages.length) {
      return displayedMessages.map((message) => ({
        id: message.id,
        role: message.role === 'user' ? 'user' : message.role === 'assistant' ? 'assistant' : 'system',
        text: message.content,
        timestamp: message.created_at,
      }));
    }
    const transcript: LiveChatMessage[] = liveVoiceTranscript.rows.map((row) => ({
      id: row.id,
      role: row.speaker === 'You' ? 'user' : 'assistant',
      text: row.text,
      timestamp: row.at,
    }));
    if (liveVoiceTranscript.delivery) {
      transcript.push({ id: 'live-voice-delivery', role: 'assistant', text: liveVoiceTranscript.delivery.text, timestamp: null });
    }
    return transcript;
  }, [displayedMessages, liveVoiceTranscript]);
  const liveCardRef = useRef<HTMLElement | null>(null);
  const latestAssistantMessage = getLatestAssistantMessage(activeSession?.messages ?? []);
  const toolExecutionRows = useMemo(() => createToolExecutionRows(activityEvents), [activityEvents]);
  const enabledToolCount = runtimeConfig.features.toolExecution ? Math.max(toolExecutionRows.length, 3) : 0;
  const liveCharacterName = liveCallRuntime?.interaction_mode === 'character'
    ? liveCallRuntime.display_name
    : selectedCharacter?.display_name;
  const liveIdentityLabel = liveCharacterName
    ? `Character Mode · ${liveCharacterName}`
    : 'System Assistant';
  const configuredVoiceId = assistantSettings.voiceId || runtimeConfig.ttsVoice || '';
  const activeVoiceId = liveCallRuntime?.voice_asset_id || configuredVoiceId;
  const activeVoiceLabel = voiceLabelForId(activeVoiceId, voiceProfiles);
  const selectedPersonalityLabel = personalityLabel(assistantSettings.personalityId);
  const speechInputLabel = runtimeConfig.sttServiceUrl ? 'STT service recording' : getSpeechRecognitionConstructor() ? 'Browser speech-to-text' : 'No STT input configured';
  const ttsOutputLabel = `${runtimeConfig.ttsServiceUrl ? 'TTS service' : 'Voice Studio TTS job'}${activeVoiceLabel ? ` · ${activeVoiceLabel}` : ''}`;
  const {
    isAssistantSpeaking,
    playAssistantResponseAudio,
    stopAssistantResponseAudio,
    currentLiveCallVoiceId,
    currentLiveCallSpeechStyle,
  } = useResponseAudio({
    runtimeConfig,
    assistantSettings,
    liveCallRuntimeRef,
    voiceProfiles,
    activeVoiceId,
    activeVoiceLabel,
    activeSessionId: activeSession?.id,
    selectedProviderId,
    selectedModelId,
    selectedPersonalityLabel,
    setAudioStatus,
    markVoiceTurnPerformance,
    recordVoiceTurnDiagnostic,
    logVoiceTurnPerformance,
  });
  const {
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
  } = useLiveVoiceCall({
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
  });
  // With the capture controller installed, the card shows its microphone stream.
  const captureLabels = livePresentation.captureOwned ? liveCaptureLabels(livePresentation.captureStatus) : null;
  const liveVoiceState = captureLabels ? captureLabels.state : liveVoiceActive ? voiceCaptureLabel(voiceCaptureMode) : voiceCaptureMode === 'error' ? 'Error' : 'Idle';
  const liveConnectionLabel = captureLabels ? captureLabels.connection : liveVoiceActive ? 'Connected' : 'Disconnected';
  const liveInputLabel = captureLabels ? (livePresentation.hearing ? 'Hearing you' : captureLabels.input) : liveVoiceActive ? 'Listening' : 'Idle';
  const liveVoiceInputMode = livePresentation.captureOwned
    ? livePresentation.hearing ? 'active' : livePresentation.captureStatus === 'connected' ? 'listening' : livePresentation.captureStatus
    : undefined;
  const liveCallButtonActive = livePresentation.captureOwned ? livePresentation.captureActive : liveVoiceActive;
  const liveCallTimerLabel = formatCallDuration(callElapsedMs);
  const liveVoiceVisualMode = isAssistantSpeaking ? 'speaking'
    : livePresentation.captureOwned || livePresentation.speaking ? liveCallVoiceMode(livePresentation, liveVoiceActive)
      : liveVoiceActive ? 'listening' : voiceCaptureMode === 'error' ? 'error' : 'idle';
  const voiceTranscriptRef = useRef<HTMLDivElement | null>(null);
  const lastVoiceTranscriptMessageId = visibleVoiceTranscriptMessages.at(-1)?.id;
  // The newest words stay in view as the transcript grows.
  useLayoutEffect(() => {
    const transcript = voiceTranscriptRef.current;
    if (transcript) transcript.scrollTop = transcript.scrollHeight;
  }, [lastVoiceTranscriptMessageId, liveVoiceTranscript]);

  useEffect(() => {
    if (displayedMessages.length === 0) return;
    const scrollKey = `${displayedSessionId}:${displayedMessages.length}`;
    const alreadyInSession = lastMessageScrollKeyRef.current.startsWith(`${displayedSessionId}:`);
    lastMessageScrollKeyRef.current = scrollKey;
    if (alreadyInSession && !shouldStickToLatestMessageRef.current) return;
    const scheduleFrame: (callback: FrameRequestCallback) => number = typeof window.requestAnimationFrame === 'function'
      ? window.requestAnimationFrame.bind(window)
      : (callback: FrameRequestCallback) => Number(window.setTimeout(() => callback(performance.now()), 0));
    const cancelFrame = typeof window.cancelAnimationFrame === 'function'
      ? window.cancelAnimationFrame.bind(window)
      : (id: number) => window.clearTimeout(id);
    const frameId = scheduleFrame(() => {
      messagesEndRef.current?.scrollIntoView({ block: 'end', behavior: 'auto' });
      shouldStickToLatestMessageRef.current = true;
    });
    return () => cancelFrame(frameId);
  }, [displayedSessionId, displayedMessages.length]);

  useEffect(() => {
    const filter = createWorkspaceEventFilter(runtimeConfig, activeSession?.id);
    const currentEvents = eventStore.list(filter);
    const currentEventIds = new Set(currentEvents.map((event) => event.id));
    const sessionEvents = createChatbotActivityEvents(activeSession, { workspaceId: runtimeConfig.workspaceId, projectId: runtimeConfig.projectId });
    eventStore.appendMany(sessionEvents.filter((event) => !currentEventIds.has(event.id)));
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

  function handleMessagesScroll(event: UIEvent<HTMLDivElement>): void {
    shouldStickToLatestMessageRef.current = isScrolledNearBottom(event.currentTarget);
  }

  function updateAssistantSettings(next: AssistantSettings): void {
    setAssistantSettings(next);
    saveAssistantSettings(next);
    setSettingsStatus('Assistant settings saved. They apply to new chat sessions and response audio.');
  }

  function resetAssistantSettings(): void {
    const next = defaultAssistantSettings(runtimeConfig);
    setAssistantSettings(next);
    saveAssistantSettings(next);
    setSettingsStatus('Assistant settings reset to defaults.');
  }

  // The call controls start or end both the capture controller's microphone
  // stream (when installed) and Chat's call session.
  function toggleLiveCallFromControls(): void {
    const card = liveCardRef.current;
    if (card && dedicatedLiveVoiceControllerInstalled()) toggleLiveVoiceCall(card);
    void (liveVoiceActive ? stopLiveCall() : startLiveCall());
  }

  function sendFromLiveChat(text: string): boolean {
    const content = text.trim();
    if (!content) return false;
    setValue('content', content, { shouldDirty: true, shouldTouch: true, shouldValidate: true });
    void handleSubmit(submitComposerMessage)();
    return true;
  }

  function startLiveCallFromControls(): Promise<void> {
    const card = liveCardRef.current;
    if (card && dedicatedLiveVoiceControllerInstalled()) startLiveVoiceCall(card);
    return startLiveCall();
  }

  function submitComposerMessage(values: ChatbotFormValues): void {
    if (liveVoiceActiveRef.current) {
      void submitVoiceTranscriptContent(values.content, { manual: true });
      return;
    }
    sendChatMessage(values);
  }

  function handleComposerTextareaKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key !== 'Enter' || event.shiftKey || event.altKey || event.ctrlKey || event.metaKey || event.nativeEvent.isComposing) return;

    event.preventDefault();
    event.currentTarget.form?.requestSubmit();
  }

  messageActionsRef.current = {
    toggleFeedback: toggleAssistantMessageFeedback,
    copy: (message) => void copyAssistantResponse(message),
    play: (text) => void playAssistantResponseAudio(text),
    stream: streamAssistantResponseAudio,
    toggleMenu: (messageId) => setOpenMessageActionMenuId((current) => current === messageId ? null : messageId),
    closeMenu: () => setOpenMessageActionMenuId(null),
    continueFrom: (message) => applySuggestedPrompt(`Continue from: ${message.content.slice(0, 120)}`),
    openTools: () => { showAssistantView('tools'); setActiveUtilityPanel('tools'); },
  };

  function toggleAssistantMessageFeedback(messageId: string, feedback: AssistantMessageFeedback): void {
    setAssistantMessageFeedback((current) => {
      const next = { ...current };
      if (next[messageId] === feedback) delete next[messageId];
      else next[messageId] = feedback;
      return next;
    });
    setAudioStatus(feedback === 'liked' ? 'Response marked as helpful.' : 'Response marked for review.');
  }

  async function copyAssistantResponse(message: ChatMessage): Promise<void> {
    const copied = await copyTextToClipboard(message.content);
    setAudioStatus(copied ? 'Assistant response copied.' : 'Copy failed. Select the message text and copy it manually.');
    setOpenMessageActionMenuId(null);
  }

  // Low-latency playback of one reply over the TTS WebSocket; pressing it again stops it.
  function streamAssistantResponseAudio(message: ChatMessage): void {
    if (pcmStream.messageId !== message.id) {
      window.dispatchEvent(new CustomEvent(LIVE_VOICE_INTERRUPT_EVENT, {
        detail: { source: 'manual-stream-button', intent: 'audio-preempt', confidence: 1 },
      }));
      stopAssistantResponseAudio(undefined, { cancelPending: false });
    }
    void toggleAssistantPcmStream(message.id, message.content, currentLiveCallVoiceId() || null);
  }

  return (
    <WorkspacePanel labelledBy="module-title" className={`assistant-chat-page${isChatFullscreen ? ' assistant-chat-page-fullscreen' : ''}`}>
      <h2 id="module-title" className="workspace-module-heading">{module.label}</h2>
      <div className={`assistant-chat-layout${isAssistantSidebarMinimized ? ' assistant-chat-layout-sidebar-minimized' : ''}${isSidePanelMinimized ? ' assistant-chat-layout-side-minimized' : ''}`}>
        <aside className={`assistant-chat-sidebar${isAssistantSidebarMinimized ? ' assistant-chat-sidebar-minimized' : ''}`} aria-label="Omnix assistant navigation">
          <div role="group" className="assistant-chat-sidebar-controls" aria-label="Assistant navigation controls">
            <button
              type="button"
              className="assistant-chat-sidebar-minimize"
              aria-label={isAssistantSidebarMinimized ? 'Expand assistant sidebar' : 'Minimize assistant sidebar'}
              aria-pressed={isAssistantSidebarMinimized}
              title={isAssistantSidebarMinimized ? 'Expand assistant sidebar' : 'Minimize assistant sidebar'}
              onClick={() => setIsAssistantSidebarMinimized((current) => !current)}
            >
              <span aria-hidden="true" data-direction={isAssistantSidebarMinimized ? 'right' : 'left'}>{isAssistantSidebarMinimized ? '›' : '‹'}</span>
            </button>
          </div>
          <nav className="assistant-sidebar-nav" aria-label="Assistant workspace">
            {assistantSidebarItems.map((item) => (
              <button aria-label={`Open ${item.label} view`} className={activeView === item.id ? 'active' : undefined} key={item.id} onClick={() => showAssistantView(item.id)} title={item.label} type="button">
                <span aria-hidden="true">{item.icon}</span>
                <span>{item.label}</span>
              </button>
            ))}
          </nav>

          <ChatSidebarSessions
            sessions={chatSessions}
            loading={sessionsLoading}
            failed={sessionsError}
            selectedSessionId={selectedSessionId}
            onSelect={selectSidebarSession}
            onDelete={(session) => deleteSessionMutation.mutateAsync(session.id)}
          />
        </aside>

        <section className="assistant-chat-main" aria-labelledby="module-title">
          {activeView === 'chats' ? (
            <>
              <header className="assistant-chat-header">
                <div className="assistant-chat-header-actions assistant-chat-integrated-actions">
                  <ChatIdentityModeControl
                    sessionId={selectedSessionId}
                    systemVoiceId={assistantSettings.voiceId}
                    defaultVoiceLabel={runtimeConfig.ttsVoice ? `Default (${runtimeConfig.ttsVoice})` : 'Default voice'}
                    voiceOptions={voiceProfiles.map((asset) => ({
                      assetId: asset.id,
                      value: voiceProfileId(asset),
                      label: voiceProfileLabel(asset),
                    }))}
                    onSystemVoiceChange={(voiceId) => updateAssistantSettings({ ...assistantSettings, voiceId })}
                    onSessionResolved={(sessionId) => setSelectedSessionId(sessionId)}
                    onOpenSystemSettings={() => showAssistantView('settings')}
                    onOpenCharacterSettings={() => showAssistantView('characters')}
                  />
                  <button
                    type="button"
                    className="assistant-header-pill assistant-chat-fullscreen-button"
                    aria-label={isChatFullscreen ? 'Exit full screen chat' : 'Enter full screen chat'}
                    aria-pressed={isChatFullscreen}
                    title={isChatFullscreen ? 'Exit full screen chat' : 'Enter full screen chat'}
                    onClick={() => setIsChatFullscreen((current) => !current)}
                  >
                    {isChatFullscreen ? '↙' : '⛶'}
                  </button>
                </div>
              </header>
              <div className="assistant-chat-messages" role="log" aria-live="polite" ref={messagesContainerRef} onScroll={handleMessagesScroll}>
                {displayedMessages.length ? <VirtualList items={displayedMessages} getKey={(message) => message.id} scrollRef={messagesContainerRef} estimateSize={180} renderItem={(message) => (
                  <ChatMessageItem
                    key={message.id}
                    message={message}
                    sessionId={displayedSessionId}
                    feedback={assistantMessageFeedback[message.id]}
                    menuOpen={openMessageActionMenuId === message.id}
                    streaming={pcmStream.messageId === message.id}
                    actions={messageActions}
                  />
                )} /> : activeSessionLoading || sessionsLoading ? <div className="platform-empty" role="status">Loading chat messages...</div> : activeSessionError ? <div className="platform-empty" role="status">Chat messages failed to load.</div> : <div className="platform-empty" role="status">No chat messages yet.</div>}
                {quickSearchProgress ? <div className="assistant-quick-search-progress" role="status" aria-live="polite"><span className="assistant-quick-search-icon" aria-hidden="true">◎</span><span>Searching {quickSearchProgress}</span></div> : null}
                {sendMutation.isPending || chatJobInProgress ? <div className="assistant-thinking-indicator" role="status" aria-live="polite"><span className="assistant-thinking-orb" aria-hidden="true" /><span className="assistant-thinking-label">Thinking<span className="assistant-thinking-dots" aria-hidden="true"><i /><i /><i /></span></span></div> : null}
                <div ref={messagesEndRef} aria-hidden="true" />
              </div>
              <ResearchProgressCard />
              <form className="assistant-composer" onSubmit={handleSubmit(submitComposerMessage)}>
                <div role="group" className="assistant-suggestion-row" aria-label="Suggested prompts">
                  {suggestedPrompts.map((prompt) => <button key={prompt} type="button" onClick={() => applySuggestedPrompt(prompt)}>{prompt}</button>)}
                  <button type="button" onClick={() => applySuggestedPrompt('Give me more options for this conversation')}>More</button>
                </div>
                <div role="group" className="assistant-composer-controls" aria-label="Conversation controls">
                  <label><span>Provider</span><select {...register('providerId')} aria-label="Provider"><option value="">Default provider</option>{chatProviders.map((provider) => <option key={provider.id} value={provider.id}>{provider.label}</option>)}</select></label>
                  <label><span>Model</span><select {...register('modelId')} aria-label="Model"><option value="">Default model</option>{chatModels.map((model) => <option key={model.id} value={model.id}>{model.label}</option>)}</select></label>
                  <button type="button" className="assistant-composer-chip" onClick={() => void playAssistantResponseAudio(latestAssistantMessage?.content ?? '')} disabled={!latestAssistantMessage}><span>Voice</span><strong>{ttsOutputLabel}</strong></button>
                  <button className="assistant-composer-chip" type="button" onClick={() => showAssistantView('settings')}><span>Personality</span><strong>{selectedPersonalityLabel}</strong></button>
                  <button className="assistant-composer-chip" type="button" onClick={() => showAssistantView('settings')}><span>Permissions</span><strong>{codingApprovalOptions.find((option) => option.value === assistantSettings.codingApprovalPolicy)?.label}</strong></button>
                  <button type="button" className="assistant-composer-chip" onClick={() => { showAssistantView('tools'); setActiveUtilityPanel('tools'); }}><span>Tools</span><strong>{runtimeConfig.features.toolExecution ? `${enabledToolCount} Active` : 'Off'}</strong></button>
                  <button type="button" className="assistant-composer-chip" onClick={refreshActivityPanel}><span>Context</span><strong>{activeMessageCount > 0 ? 'Project Brief' : 'Ready'}</strong></button>
                </div>
                {pastedChatImages.length ? <div className="assistant-chat-image-attachments" role="status" aria-label={`${pastedChatImages.length} image attachment${pastedChatImages.length === 1 ? '' : 's'}`}>{pastedChatImages.map((image, index) => <div className="assistant-chat-image-attachment" key={`${image.dataUrl.slice(-24)}:${index}`}><img src={image.dataUrl} alt={`Attached image preview ${index + 1}`} /><div><strong>Image {index + 1}</strong><small>{image.mimeType.replace('image/', '').toUpperCase()} · {(image.size / 1024).toFixed(0)} KB</small></div><button type="button" aria-label={`Remove attached image ${index + 1}`} onClick={() => { setPastedChatImages((current) => current.filter((_, candidateIndex) => candidateIndex !== index)); setChatImageError(null); }}>×</button></div>)}</div> : null}
                {pastedChatTextFile ? <div className="assistant-chat-file-attachment" role="status"><span aria-hidden="true">📄</span><div><strong>{pastedChatTextFile.filename}</strong><small>{pastedChatTextFile.mimeType} · {(pastedChatTextFile.size / 1024).toFixed(0)} KB</small></div><button type="button" aria-label="Remove attached file" onClick={() => { setPastedChatTextFile(null); setChatImageError(null); }}>×</button></div> : null}
                {chatImageError ? <p className="assistant-chat-image-error" role="alert">{chatImageError}</p> : null}
                <label className="assistant-message-input"><span>Message <small className="assistant-chat-paste-hint">Paste an image, or use + to add a photo or text file</small></span><textarea rows={3} aria-label="Message" aria-invalid={Boolean(errors.content)} placeholder="Message Omnix Assistant, or use the microphone…" onKeyDown={handleComposerTextareaKeyDown} onPaste={handleComposerPaste} {...register('content', { validate: (value) => (value.trim() || pastedChatImages.length > 0 || pastedChatTextFile) ? true : 'Enter a message, paste an image, or add a file before sending.' })} /></label>
                <div className="assistant-composer-actions"><DesktopShareButton /><button type="button" className="assistant-mic-button" aria-label={liveVoiceActive ? 'Stop voice input' : 'Start voice input'} onClick={toggleLiveCallFromControls}>{liveVoiceActive ? '■' : '◉'}</button><button aria-label={sendMutation.isPending ? 'Queueing response' : chatJobInProgress ? 'Interrupt and send' : 'Queue response'} className="assistant-send-button" type="submit" disabled={sendMutation.isPending}>{sendMutation.isPending ? 'Queueing response…' : chatJobInProgress ? 'Interrupt & send' : 'Send message'}</button></div>
              <AssistantContextControls />
              </form>
            </>
          ) : activeView === 'live' ? (
            <LiveChatPanel sessionId={selectedSessionId} onSessionResolved={setSelectedSessionId} onToggleCall={toggleLiveCallFromControls} />
          ) : (
            <AssistantWorkspaceView
              activeView={activeView}
              assistantSettings={assistantSettings}
              chatProviders={chatProviders}
              enabledToolCount={enabledToolCount}
              initialToolConnectionMessage={assistantToolReturn.message}
              initialToolId={assistantToolReturn.toolId}
              modelLabel={modelLabel}
              providerLabel={providerLabel}
              runtimeConfig={runtimeConfig}
              settingsStatus={settingsStatus}
              speechInputLabel={speechInputLabel}
              toolExecutionRows={toolExecutionRows.length}
              ttsOutputLabel={ttsOutputLabel}
              voiceProfiles={voiceProfiles}
              voiceProfilesLoading={assetsQuery.isLoading}
              onResetAssistantSettings={resetAssistantSettings}
              onSessionResolved={setSelectedSessionId}
              onStartLiveCall={startLiveCallFromControls}
              onUpdateAssistantSettings={updateAssistantSettings}
              onShowTools={() => setActiveUtilityPanel('tools')}
              selectedSessionId={selectedSessionId}
            />
          )}
          <div className="assistant-inline-status" aria-live="polite">
            {errors.content ? <span role="alert">Enter a message or paste an image before sending.</span> : null}
            {sendMutation.isPending ? <span role="status">Submitting the message to the response queue...</span> : null}
            {sendMutation.isError ? <span role="alert">{chatbotSubmitErrorMessage(sendMutation.error)}</span> : null}
            {chatJobQuery.isError ? <span role="alert">The response job could not be tracked. Refresh to check its status.</span> : null}
            {chatJobError ? <span role="alert">{chatJobError}</span> : null}
            {audioStatus ? <span role="status">{audioStatus}</span> : null}
            {pcmStream.status ? <span role="status">{pcmStream.status}</span> : null}
            {livePresentation.streamStatus ? <span role="status" data-omnix-live-voice-stream-status="true">{livePresentation.streamStatus}</span> : null}
            {settingsStatus && activeView === 'settings' ? <span role="status">{settingsStatus}</span> : null}
            {sendMutation.data ? <span role="status">{chatJobQuery.data?.status === 'completed' ? 'Response ready' : chatJobQuery.data?.status === 'failed' ? 'Response failed' : chatJobQuery.data?.status === 'canceled' ? 'Response canceled' : 'Response job accepted'}: {sendMutation.data.job.id}</span> : null}
          </div>
        </section>

        <aside className={`assistant-chat-side${isSidePanelMinimized ? ' assistant-chat-side-minimized' : ''}`} aria-label="Live voice and tool execution">
          <div role="group" className="assistant-side-panel-toggle" aria-label="Assistant utility panel">
            <button type="button" className={activeUtilityPanel === 'voice' ? 'assistant-side-panel-option active' : 'assistant-side-panel-option'} onClick={() => setActiveUtilityPanel('voice')}>Live Voice</button>
            <button
              type="button"
              className="assistant-side-panel-minimize"
              aria-label={isSidePanelMinimized ? 'Expand side panel' : 'Minimize side panel'}
              aria-pressed={isSidePanelMinimized}
              title={isSidePanelMinimized ? 'Expand side panel' : 'Minimize side panel'}
              onClick={() => setIsSidePanelMinimized((current) => !current)}
            >
              <span aria-hidden="true">{isSidePanelMinimized ? '‹' : '›'}</span>
            </button>
          </div>
          <div className="assistant-live-tools-grid" data-active-panel={activeUtilityPanel}>
            <section className="assistant-live-card" ref={liveCardRef} data-live-voice-id={currentLiveCallVoiceId()} data-live-voice-status={livePresentation.captureOwned ? livePresentation.captureStatus : undefined} data-voice-input={liveVoiceInputMode} data-live-voice-output-kind={livePresentation.outputKind ?? undefined}>
              <header><div><p className="eyebrow">Live Voice</p><span className={liveCallRuntime?.interaction_mode === 'character' ? 'assistant-live-identity active' : 'assistant-live-identity'}>{liveIdentityLabel}</span></div><div className="assistant-live-header-actions"><strong>{liveConnectionLabel}</strong><button type="button" className="assistant-live-fullscreen-button" aria-label="Enter fullscreen Live Voice" onClick={() => enterLiveChatFullscreen('call-card')}>Fullscreen</button></div>{livePresentation.captureOwned ? <select aria-label="Live task" data-live-task-instruction="true" value={livePresentation.taskInstruction} onChange={(event) => liveCallPresentationStore.setTaskInstruction(event.currentTarget.value)}>{LIVE_TASK_PRESETS.map((preset) => <option key={preset.label} value={preset.value}>{preset.label}</option>)}</select> : null}</header>
              {liveCallRuntime?.avatar_pack?.renderer === 'live2d'
                ? <Live2DMotionControl rigAssetId={liveCallRuntime.avatar_pack.rig_asset_id} />
                : <div className="assistant-live-state" role="status" aria-label="Live voice state"><span>{liveVoiceState}</span><span aria-hidden="true">v</span></div>}
              <LiveCallVisual voiceMode={liveVoiceVisualMode} thinking={sendMutation.isPending || chatJobInProgress} />
              {liveCallRuntime?.avatar_pack?.renderer === 'live2d' ? <Live2DZoomControl /> : null}
              <div className="assistant-voice-input-indicator" aria-live="polite">
                <span>Mic input</span>
                <strong className="assistant-voice-input-status">{liveInputLabel}</strong>
                <i aria-hidden="true"><b /></i>
              </div>
              <time className="assistant-call-timer" dateTime={`PT${Math.floor(callElapsedMs / 1000)}S`}>{liveCallTimerLabel}</time>
              <div className="assistant-voice-controls" role="group" aria-label="Live voice controls"><button type="button" onClick={clearVoiceTranscript}>Clear</button><button type="button" className={liveCallButtonActive ? 'danger' : undefined} disabled={livePresentation.captureOwned && livePresentation.captureStatus === 'connecting'} onClick={toggleLiveCallFromControls}>{liveCallButtonActive ? 'End Call' : 'Start Call'}</button><SendVoiceTextButton control={control} draft={liveDraftText} pending={sendMutation.isPending} onSend={sendVoiceTranscript} /></div>
              <div className="assistant-voice-transcript" ref={voiceTranscriptRef} role="region" aria-label="Live voice transcript"><div className="assistant-voice-transcript-header"><h3>Transcript</h3><button type="button" onClick={clearVoiceTranscript}>Clear</button></div>{visibleVoiceTranscriptMessages.map((message) => <p key={`transcript-${message.id}`} className={message.role === 'assistant' ? 'assistant' : 'user'}><span><strong>{message.role === 'assistant' ? 'Omnix' : 'You'}</strong><time dateTime={message.created_at}>{formatMessageTime(message.created_at)}</time></span>{message.content}</p>)}{liveVoiceTranscript.rows.map((row) => <p key={row.id} className={row.speaker === 'Omnix' ? 'assistant' : 'user'} data-live-voice-id={row.draft ? 'live-voice-draft' : row.id}><span><strong>{row.speaker}</strong><time dateTime={row.at}>{formatClockTime(row.at)}</time></span>{row.text}</p>)}{liveVoiceTranscript.delivery ? <p className="assistant" data-omnix-live-delivery="true">{`Assistant: ${liveVoiceTranscript.delivery.text}${liveVoiceTranscript.delivery.partial ? ' [partial]' : ''}`}</p> : null}{!visibleVoiceTranscriptMessages.length && !liveVoiceTranscript.rows.length && !liveVoiceTranscript.delivery ? <p className="muted">Voice transcript will appear here during live calls.</p> : null}</div>
              <label className="assistant-voice-toggle"><input type="checkbox" checked={autoSpeakResponses} onChange={(event) => setAutoSpeakResponses(event.currentTarget.checked)} /> Auto-speak assistant replies</label>
              <div className="assistant-live-draft" aria-live="polite"><strong>Voice draft</strong><p>{liveDraftText || 'Start Live Voice and speak. Final speech is copied into the message composer.'}</p></div>
              <div className="assistant-audio-devices"><header><h3>Audio Services</h3><button type="button" onClick={() => void startVoiceInput()}>Test input</button></header><div><span>Input</span><strong>{speechInputLabel}</strong><i aria-hidden="true" /></div><div><span>Output</span><strong>{ttsOutputLabel}</strong><i aria-hidden="true" /></div><DesktopShareStatusRow /><DesktopCompanionControls /><DesktopCompanionTextSurface /></div>
              <footer className="assistant-voice-status"><span>Voice Status</span><strong>{liveVoiceState}</strong></footer>
            </section>
            <section className="assistant-tool-sidebar-card" aria-labelledby="assistant-tool-execution-heading"><ToolExecutionPanel rows={toolExecutionRows} title="Tool execution" description="Review approvals and monitor tool execution results." /></section>
          </div>
        </aside>
      </div>
      <LiveChatFullscreenShell messages={liveChatMessages} onSendMessage={sendFromLiveChat} onToggleCall={toggleLiveCallFromControls} />
    </WorkspacePanel>
  );
}

// Watches the composer here, so typing re-renders this button rather than all of Chat.
function SendVoiceTextButton({ control, draft, pending, onSend }: { control: Control<ChatbotFormValues>; draft: string; pending: boolean; onSend: () => void }) {
  const content = useWatch({ control, name: 'content' }) ?? '';
  return <button type="button" onClick={onSend} disabled={pending || !(draft || content).trim()}>Send text</button>;
}

export function selectFreshChatSession<T extends { id?: string; message_count?: number; messages?: unknown[] } | null | undefined>(
  mutationSession: T,
  queriedSession: T,
): T {
  if (!mutationSession) return queriedSession;
  if (!queriedSession) return mutationSession;
  // A mutation result remains available after the user switches sessions.
  // It must never replace the newly selected session, even when it is newer.
  if (mutationSession.id !== queriedSession.id) return queriedSession;
  const mutationCount = mutationSession.message_count ?? mutationSession.messages?.length ?? 0;
  const queryCount = queriedSession.message_count ?? queriedSession.messages?.length ?? 0;
  if (queryCount !== mutationCount) return queryCount > mutationCount ? queriedSession : mutationSession;

  // Some responses carry the total message_count but only a partial messages
  // projection. When the reported counts tie, prefer the snapshot that can
  // actually render more of the transcript.
  const mutationMessageLength = mutationSession.messages?.length ?? 0;
  const queryMessageLength = queriedSession.messages?.length ?? 0;
  return queryMessageLength >= mutationMessageLength ? queriedSession : mutationSession;
}

function AssistantWorkspaceView({ activeView, assistantSettings, selectedSessionId, chatProviders, enabledToolCount, initialToolConnectionMessage, initialToolId, modelLabel, onResetAssistantSettings, onSessionResolved, onShowTools, onStartLiveCall, onUpdateAssistantSettings, providerLabel, runtimeConfig, settingsStatus, speechInputLabel, toolExecutionRows, ttsOutputLabel, voiceProfiles, voiceProfilesLoading }: { activeView: Exclude<AssistantView, 'chats' | 'live'>; assistantSettings: AssistantSettings; selectedSessionId: string | null; chatProviders: ReturnType<typeof chatCapableProviders>; enabledToolCount: number; initialToolConnectionMessage: string | null; initialToolId: string | null; modelLabel: string; onResetAssistantSettings: () => void; onSessionResolved: (sessionId: string) => void; onShowTools: () => void; onStartLiveCall: () => void | Promise<void>; onUpdateAssistantSettings: (settings: AssistantSettings) => void; providerLabel: string; runtimeConfig: AssistantWorkspaceRuntimeConfig; settingsStatus: string | null; speechInputLabel: string; toolExecutionRows: number; ttsOutputLabel: string; voiceProfiles: VoiceProfileAsset[]; voiceProfilesLoading: boolean }) {
  if (activeView === 'voice') return <section className="assistant-view-panel" aria-label="Voice Sessions view"><p className="eyebrow">Omnix Assistant</p><h2>Voice Sessions</h2><p>Use browser speech-to-text or the configured STT service to draft messages, then play assistant replies through the TTS service or local Voice Studio jobs.</p><div className="platform-grid"><article><h3>Live call</h3><p>Input: {speechInputLabel}. Output: {ttsOutputLabel}.</p><button type="button" onClick={() => void onStartLiveCall()}>Start Call</button></article><article><h3>Response playback</h3><p>{assistantSettings.voiceId ? `Active cloned voice: ${voiceLabelForId(assistantSettings.voiceId, voiceProfiles) || assistantSettings.voiceId}` : runtimeConfig.ttsVoice ? `Configured voice: ${runtimeConfig.ttsVoice}` : 'Chatbot will synthesize assistant replies with the default configured voice.'}</p></article></div><VoiceSessionEvaluationPanel /></section>;
  if (activeView === 'tools') return <AssistantToolSettingsPanel enabledToolCount={enabledToolCount} initialConnectionMessage={initialToolConnectionMessage} initialToolId={initialToolId} toolExecutionRows={toolExecutionRows} onShowExecutionPanel={onShowTools} />;
  if (activeView === 'characters') return <section className="assistant-view-panel" aria-label="Characters view"><header><p className="eyebrow">Omnix Assistant</p><h2>Characters</h2><p>Create, version, and govern character identities independently from their linked voices and memory.</p></header><CharacterManagementPanel sessionId={selectedSessionId} onSessionResolved={onSessionResolved} /></section>;
  if (activeView === 'memory') return <MemoryManagementPanel sessionId={selectedSessionId} />;
  return <section className="assistant-view-panel" aria-label="Settings view"><p className="eyebrow">Omnix Assistant</p><h2>Settings</h2><p>Select the assistant personality and cloned voice used by Chatbot sessions and response audio.</p><div className="assistant-settings-list"><div><label htmlFor="assistant-personality">Personality</label><select id="assistant-personality" aria-label="Personality" value={assistantSettings.personalityId} onChange={(event) => onUpdateAssistantSettings({ ...assistantSettings, personalityId: event.currentTarget.value as PersonalityId })}>{personalityOptions.map((personality) => <option key={personality.id} value={personality.id}>{personality.label}</option>)}</select></div><div><label htmlFor="coding-approval-policy">Coding agent permissions</label><select id="coding-approval-policy" aria-label="Coding agent permissions" value={assistantSettings.codingApprovalPolicy} onChange={(event) => onUpdateAssistantSettings({ ...assistantSettings, codingApprovalPolicy: event.currentTarget.value as CodingApprovalPolicy })}>{codingApprovalOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select><small>{codingApprovalOptions.find((option) => option.value === assistantSettings.codingApprovalPolicy)?.description}</small></div><div><label htmlFor="assistant-custom-personality">Custom personality</label><textarea id="assistant-custom-personality" aria-label="Custom personality" rows={4} value={assistantSettings.customPersonality} disabled={assistantSettings.personalityId !== 'custom'} placeholder="Describe how the assistant should behave, speak, and prioritize responses." onChange={(event) => onUpdateAssistantSettings({ ...assistantSettings, customPersonality: event.currentTarget.value })} /></div><div><label htmlFor="assistant-voice">Cloned voice</label><select id="assistant-voice" aria-label="Cloned voice" value={assistantSettings.voiceId} onChange={(event) => onUpdateAssistantSettings({ ...assistantSettings, voiceId: event.currentTarget.value })}><option value="">{runtimeConfig.ttsVoice ? `Default configured voice (${runtimeConfig.ttsVoice})` : 'Default voice'}</option>{voiceProfiles.map((asset) => <option key={asset.id} value={voiceProfileId(asset)}>{voiceProfileLabel(asset)}</option>)}</select></div><div><label htmlFor="assistant-live-sensitivity">Live mic sensitivity</label><input id="assistant-live-sensitivity" aria-label="Live mic sensitivity" type="range" min="1" max="100" step="1" value={assistantSettings.liveVoiceSensitivity} onChange={(event) => onUpdateAssistantSettings({ ...assistantSettings, liveVoiceSensitivity: clampLiveVoiceSensitivity(event.currentTarget.value) })} /><strong>{assistantSettings.liveVoiceSensitivity}%</strong></div><div><span>Voice profiles</span><strong>{voiceProfilesLoading ? 'Loading cloned voices…' : voiceProfiles.length ? `${voiceProfiles.length} cloned voices available` : 'No cloned voices indexed'}</strong></div><div><span>TTS output</span><strong>{ttsOutputLabel}</strong></div><div><span>Provider</span><strong>{providerLabel}</strong></div><div><span>Model</span><strong>{modelLabel}</strong></div><div><span>Speech input</span><strong>{speechInputLabel}</strong></div><div><span>Event storage</span><strong>{runtimeConfig.features.persistedEvents ? runtimeConfig.eventStorageKey : 'In-memory only'}</strong></div><div><span>Live assistant</span><strong>{runtimeConfig.features.liveAssistant ? 'Enabled' : 'Disabled'}</strong></div><div><span>Tool execution</span><strong>{runtimeConfig.features.toolExecution ? 'Enabled' : 'Disabled'}</strong></div><div><span>Available chat providers</span><strong>{chatProviders.length}</strong></div></div><div className="assistant-settings-actions"><button type="button" onClick={onResetAssistantSettings}>Reset assistant settings</button></div>{settingsStatus ? <p className="assistant-view-note" role="status">{settingsStatus}</p> : null}<p className="assistant-view-note">Personality is sent as the system prompt when a new chat session is created. Coding agent permissions apply to new coding Agent runs. Existing runs keep their original policy.</p></section>;
}
