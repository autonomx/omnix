import { useMemo, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import type { OmnixModuleDefinition } from '../../app/modules';
import { WorkspacePanel } from '../../design/primitives';
import { VirtualList } from '../../design/VirtualList';
import { createAssistantWorkspaceRuntimeConfig, startLiveVoiceCall, toggleLiveVoiceCall, ToolExecutionPanel, useAssistantPcmStream, useLiveCallPresentation, useLiveVoiceTranscript } from '../assistant-workspace';
import { ChatIdentityModeControl } from './ChatIdentityModeControl';
import { LiveChatFullscreenShell } from './LiveChatFullscreenShell';
import { LiveChatPanel } from './LiveChatPanel';
import { ChatSidebarSessions } from './ChatSidebarSessions';
import { ResearchProgressCard } from './ResearchProgressCard';
import { ChatMessageItem } from './ChatMessageItem';
import { AssistantView, ChatbotFormValues, chatbotSubmitErrorMessage, codingApprovalOptions, dedicatedLiveVoiceControllerInstalled, getLatestAssistantMessage, getSpeechRecognitionConstructor, personalityLabel, readAssistantToolReturn, selectedModelLabel, selectedProviderLabel, voiceLabelForId, voiceProfileId, voiceProfileLabel } from './chatbotWorkspaceModel';
import { useChatLayout } from './useChatLayout';
import { useChatAttachments } from './useChatAttachments';
import { useVoiceTurnDiagnostics } from './useVoiceTurnDiagnostics';
import { useResponseAudio } from './useResponseAudio';
import { useChatSessions } from './useChatSessions';
import { useChatJob } from './useChatJob';
import { useLiveCallRuntime } from './useLiveCallRuntime';
import { useSendChatMessage } from './useSendChatMessage';
import { useLiveVoiceCall } from './useLiveVoiceCall';
import { ChatHeader, ChatNavigationSidebar, ChatUtilitySidebar } from './ChatFrame';
import { ChatLiveVoiceCard } from './ChatLiveVoiceCard';
import { ChatComposer } from './ChatComposer';
import { AssistantWorkspaceView } from './AssistantWorkspaceView';
import { selectFreshChatSession } from './chatMessageModel';
import { useAssistantSettings } from './useAssistantSettings';
import { useChatActivity } from './useChatActivity';
import { useStickToLatestMessage } from './useStickToLatestMessage';
import { liveChatMessagesFor } from './chatMessageModel';
import { useChatCatalog } from './useChatCatalog';
import { useChatMessageActions } from './useChatMessageActions';

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
  const liveVoiceActiveRef = useRef(false);
  const diagnostics = useVoiceTurnDiagnostics();
  const runtimeConfig = useMemo(() => createAssistantWorkspaceRuntimeConfig(), []);
  const { assistantSettings, settingsStatus, updateAssistantSettings, resetAssistantSettings } = useAssistantSettings(runtimeConfig, activeView);
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
    recordActivityEvent: (event, filter) => recordActivityEvent(event, filter),
    markVoiceTurnPerformance: diagnostics.markVoiceTurnPerformance,
  });
  const selectedProviderId = watch('providerId');
  const selectedModelId = watch('modelId');
  const { providerPayload, chatProviders, chatModels, interaction, selectedCharacter, voiceProfiles, voiceProfilesLoading } = useChatCatalog({
    activeView,
    sessionsPending: sessionsQuery.isPending,
    selectedSessionId,
    selectedSessionSummary,
    selectedProviderId,
  });
  const { liveCallRuntime, setLiveCallRuntime, liveCallRuntimeRef } = useLiveCallRuntime({
    selectedSessionId,
    selectedSessionSummary,
    interaction,
    liveVoiceActiveRef,
  });

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
  const { messagesContainerRef, messagesEndRef, handleMessagesScroll } = useStickToLatestMessage(displayedSessionId, displayedMessages.length);
  const liveVoiceTranscript = useLiveVoiceTranscript();
  const livePresentation = useLiveCallPresentation();
  const pcmStream = useAssistantPcmStream();
  const liveChatMessages = useMemo(() => liveChatMessagesFor(displayedMessages, liveVoiceTranscript), [displayedMessages, liveVoiceTranscript]);
  const liveCardRef = useRef<HTMLElement | null>(null);
  const { toolExecutionRows, refreshActivityPanel, recordActivityEvent } = useChatActivity(runtimeConfig, activeSession);
  const latestAssistantMessage = getLatestAssistantMessage(activeSession?.messages ?? []);
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
  const audio = useResponseAudio({
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
    ...diagnostics,
  });
  const { isAssistantSpeaking, playAssistantResponseAudio, currentLiveCallVoiceId } = audio;
  const {
    liveVoiceActive, callElapsedMs, voiceCaptureMode, liveDraftText, visibleVoiceTranscriptMessages,
    autoSpeakResponses, setAutoSpeakResponses, setLiveTranscript, setLiveInterimTranscript,
    startLiveCall, stopLiveCall, startVoiceInput, clearVoiceTranscript, sendVoiceTranscript, submitVoiceTranscriptContent,
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
    ...audio,
    ...diagnostics,
  });

  const { messageActions, assistantMessageFeedback, openMessageActionMenuId } = useChatMessageActions({
    setAudioStatus,
    ...audio,
    streamingMessageId: pcmStream.messageId,
    continueFrom: (message) => applySuggestedPrompt(`Continue from: ${message.content.slice(0, 120)}`),
    openTools: () => { showAssistantView('tools'); setActiveUtilityPanel('tools'); },
  });

  function applySuggestedPrompt(prompt: string): void {
    setActiveView('chats');
    setValue('content', prompt, { shouldDirty: true, shouldTouch: true, shouldValidate: true });
  }

  function showAssistantView(view: AssistantView): void {
    setActiveView(view);
    if (view === 'voice') setActiveUtilityPanel('voice');
    if (view === 'tools') setActiveUtilityPanel('tools');
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

  return (
    <WorkspacePanel labelledBy="module-title" className={`assistant-chat-page${isChatFullscreen ? ' assistant-chat-page-fullscreen' : ''}`}>
      <h2 id="module-title" className="workspace-module-heading">{module.label}</h2>
      <div className={`assistant-chat-layout${isAssistantSidebarMinimized ? ' assistant-chat-layout-sidebar-minimized' : ''}${isSidePanelMinimized ? ' assistant-chat-layout-side-minimized' : ''}`}>
        <ChatNavigationSidebar
          minimized={isAssistantSidebarMinimized}
          onToggleMinimized={() => setIsAssistantSidebarMinimized((current) => !current)}
          activeView={activeView}
          onShowView={showAssistantView}
        >
          <ChatSidebarSessions
            sessions={chatSessions}
            loading={sessionsLoading}
            failed={sessionsError}
            selectedSessionId={selectedSessionId}
            onSelect={selectSidebarSession}
            onDelete={(session) => deleteSessionMutation.mutateAsync(session.id)}
          />
        </ChatNavigationSidebar>

        <section className="assistant-chat-main" aria-labelledby="module-title">
          {activeView === 'chats' ? (
            <>
              <ChatHeader fullscreen={isChatFullscreen} onToggleFullscreen={() => setIsChatFullscreen((current) => !current)}>
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
              </ChatHeader>
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
              <ChatComposer
                onSubmit={handleSubmit(submitComposerMessage)}
                register={register}
                errors={errors}
                chatProviders={chatProviders}
                chatModels={chatModels}
                onApplyPrompt={applySuggestedPrompt}
                ttsOutputLabel={ttsOutputLabel}
                canPlayLatestReply={Boolean(latestAssistantMessage)}
                onPlayLatestReply={() => void playAssistantResponseAudio(latestAssistantMessage?.content ?? '')}
                personalityLabel={selectedPersonalityLabel}
                permissionsLabel={codingApprovalOptions.find((option) => option.value === assistantSettings.codingApprovalPolicy)?.label}
                toolsLabel={runtimeConfig.features.toolExecution ? `${enabledToolCount} Active` : 'Off'}
                contextLabel={activeMessageCount > 0 ? 'Project Brief' : 'Ready'}
                onOpenSettings={() => showAssistantView('settings')}
                onOpenTools={() => { showAssistantView('tools'); setActiveUtilityPanel('tools'); }}
                onRefreshContext={refreshActivityPanel}
                pastedChatImages={pastedChatImages}
                pastedChatTextFile={pastedChatTextFile}
                chatImageError={chatImageError}
                onRemoveImage={(index) => {
                  setPastedChatImages((current) => current.filter((_, candidateIndex) => candidateIndex !== index));
                  setChatImageError(null);
                }}
                onRemoveTextFile={() => {
                  setPastedChatTextFile(null);
                  setChatImageError(null);
                }}
                onPaste={handleComposerPaste}
                liveVoiceActive={liveVoiceActive}
                onToggleCall={toggleLiveCallFromControls}
                sendPending={sendMutation.isPending}
                chatJobInProgress={chatJobInProgress}
              />
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
              voiceProfilesLoading={voiceProfilesLoading}
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
        <ChatUtilitySidebar
          minimized={isSidePanelMinimized}
          onToggleMinimized={() => setIsSidePanelMinimized((current) => !current)}
          activePanel={activeUtilityPanel}
          onShowVoice={() => setActiveUtilityPanel('voice')}
        >
          <ChatLiveVoiceCard
            cardRef={liveCardRef}
            voiceId={currentLiveCallVoiceId()}
            liveCallRuntime={liveCallRuntime}
            identityLabel={liveIdentityLabel}
            liveVoiceActive={liveVoiceActive}
            voiceCaptureMode={voiceCaptureMode}
            isAssistantSpeaking={isAssistantSpeaking}
            callElapsedMs={callElapsedMs}
            thinking={sendMutation.isPending || chatJobInProgress}
            control={control}
            liveDraftText={liveDraftText}
            sendPending={sendMutation.isPending}
            transcriptMessages={visibleVoiceTranscriptMessages}
            autoSpeakResponses={autoSpeakResponses}
            speechInputLabel={speechInputLabel}
            ttsOutputLabel={ttsOutputLabel}
            onToggleCall={toggleLiveCallFromControls}
            onClear={clearVoiceTranscript}
            onSendVoiceText={sendVoiceTranscript}
            onAutoSpeakChange={setAutoSpeakResponses}
            onTestInput={() => void startVoiceInput()}
          />
            <section className="assistant-tool-sidebar-card" aria-labelledby="assistant-tool-execution-heading"><ToolExecutionPanel rows={toolExecutionRows} title="Tool execution" description="Review approvals and monitor tool execution results." /></section>
        </ChatUtilitySidebar>
      </div>
      <LiveChatFullscreenShell messages={liveChatMessages} onSendMessage={sendFromLiveChat} onToggleCall={toggleLiveCallFromControls} />
    </WorkspacePanel>
  );
}
