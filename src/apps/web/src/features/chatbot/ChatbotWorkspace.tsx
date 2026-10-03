/* eslint-disable no-restricted-imports -- baseline WP-9.x */
/* eslint-disable react-hooks/exhaustive-deps -- baseline WP-9.x */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ClipboardEvent as ReactClipboardEvent, KeyboardEvent, UIEvent } from 'react';
import { useEffect, useMemo, useRef, useState, useLayoutEffect } from 'react';
import { useForm, useWatch, type Control } from 'react-hook-form';
import { ApiError, omnixApiClient, type ChatSession as ApiChatSession, type CodingApprovalPolicy } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { WorkspacePanel } from '../../design/primitives';
import { VirtualList } from '../../design/VirtualList';
import { openStream, statusError } from '../../api/transport';
import { ToolExecutionPanel, createFetchSpeechServiceTransport, createSttServiceClient, createToolExecutionRows, createTtsServiceClient, type AssistantWorkspaceEvent, type AssistantWorkspaceRuntimeConfig } from '../assistant-workspace';
import { createChatbotActivityEvents, createChatbotFailureEvent } from '../assistant-workspace/chatbot-activity';
import { createLiveCallDiagnosticsReporter, type LiveCallDiagnosticsReporter } from '../assistant-workspace/live-call-diagnostics-client';
import { liveChatSubmissionGateway } from '../assistant-workspace/live-chat-submission-gateway';
import { createAssistantWorkspaceRuntimeConfig } from '../assistant-workspace/runtime-config';
import { AssistantToolSettingsPanel } from './AssistantToolSettingsPanel';
import { CharacterManagementPanel } from './CharacterManagementPanel';
import { ChatIdentityModeControl } from './ChatIdentityModeControl';
import { LiveChatFullscreenShell, type LiveChatMessage } from './LiveChatFullscreenShell';
import { LiveChatPanel } from './LiveChatPanel';
import { VoiceSessionEvaluationPanel } from './VoiceSessionEvaluationPanel';
import { LiveCallVisual } from './LiveCallVisual';
import { ChatSidebarSessions } from './ChatSidebarSessions';
import { AssistantContextControls, DesktopShareButton, DesktopShareStatusRow } from '../assistant-workspace/assistant-context-controls';
import { assistantContextStore } from '../assistant-workspace/assistant-context-store';
import { DesktopCompanionControls } from '../assistant-workspace/desktop-companion-controls';
import { DesktopCompanionTextSurface } from '../assistant-workspace/desktop-companion-text-surface';
import { stopAssistantPcmStream, toggleAssistantPcmStream, useAssistantPcmStream } from '../assistant-workspace/assistant-pcm-stream-websocket-player';
import { Live2DZoomControl } from './Live2DZoomControl';
import { Live2DMotionControl } from './Live2DMotionControl';
import { MemoryManagementPanel } from './MemoryManagementPanel';
import { enterLiveChatFullscreen } from './live-chat-fullscreen-controller';
import { characterClient, type CharacterLiveCallRuntime, type LiveCallSpeechStyle } from './characterClient';
import { CHARACTER_AVATAR_RUNTIME_EVENT } from './liveCharacterAvatarBridge';
import { startLiveVoiceCall, toggleLiveVoiceCall } from '../assistant-workspace/live-voice-controller';
import { LIVE_TASK_PRESETS, liveCallPresentationStore, liveCallVoiceMode, liveCaptureLabels, useLiveCallPresentation } from '../assistant-workspace/live-call-presentation-store';
import { noteChatMessageSent, noteChatSession } from './researchProgressController';
import { ResearchProgressCard } from './ResearchProgressCard';
import { ChatMessageItem, type ChatMessageActions } from './ChatMessageItem';
import { MAX_CHAT_IMAGE_ATTACHMENTS, SUPPORTED_CHAT_IMAGE_TYPES, chatImageDataUrls, formatMessageTime } from './chatMessageModel';
import { visibleChatSessions } from './sessionTools';
import { liveVoiceTranscriptStore, useLiveVoiceTranscript } from '../assistant-workspace/live-voice-transcript-store';
import { ASSISTANT_SESSION_STORAGE_KEY, ASSISTANT_SIDEBAR_STORAGE_KEY, ASSISTANT_SIDE_PANEL_STORAGE_KEY, ASSISTANT_VIEW_STORAGE_KEY, AssistantMessageFeedback, AssistantSettings, AssistantView, BrowserSpeechRecognition, CALL_TIMER_TICK_MS, CHAT_JOB_ACTIVE_POLL_MS, CHAT_JOB_TERMINAL_STATUSES, ChatMessage, ChatbotFormValues, DEFAULT_SPEECH_LANGUAGE, LIVE_CALL_DIAGNOSTIC_EVENT, LIVE_SESSION_PROJECTION_FALLBACK_DELAY_MS, LIVE_VOICE_AUTO_SEND_DELAY_MS, LIVE_VOICE_INTERRUPT_EVENT, LIVE_VOICE_PERF_EVENT, LIVE_VOICE_STOP_EVENT, MAX_CHAT_IMAGE_BYTES, MAX_CHAT_TEXT_FILE_BYTES, PastedChatImage, PastedChatTextFile, PersonalityId, STREAMING_TTS_RECOVERY_DELAY_SECONDS, STREAMING_TTS_SAMPLE_RATE, SessionListEntry, StreamingTtsPlayback, StreamingTtsWindow, UtilityPanel, VoiceCaptureMode, VoicePerformanceStage, VoiceProfileAsset, VoiceTurnPerformance, VoiceTurnTimestampStage, appendWorkspaceEventIfMissing, assistantSidebarItems, attachmentDefaultMessage, audioSourceToArrayBuffer, canUseDecodedAudioPlayback, chatCapableModels, chatCapableProviders, chatbotSubmitErrorMessage, clampLiveVoiceSensitivity, codingApprovalOptions, copyTextToClipboard, createChatbotWorkspaceEventStore, createPersonalityPrompt, createWorkspaceEventFilter, dedicatedLiveVoiceControllerInstalled, defaultAssistantSettings, elapsedMs, finiteNumber, formatCallDuration, formatClockTime, getLatestAssistantMessage, getSpeechRecognitionConstructor, getSynthesizedAudioSource, getVoiceJobAudioSource, getVoiceProfileAssets, isScrolledNearBottom, liveVoiceSubmissionKey, loadAssistantSettings, loadSelectedSessionId, makePlayableAudioSource, mergeTranscript, parseChatStreamEvent, personalityLabel, personalityOptions, readAssistantToolReturn, readFileAsDataUrl, saveAssistantSettings, selectedModelLabel, selectedProviderLabel, shouldFlushStreamedSpeechBuffer, suggestedPrompts, unifiedLiveVoiceAudioInstalled, voiceCaptureLabel, voiceJobErrorMessage, voiceLabelForId, voiceProfileId, voiceProfileLabel, waitForAudioElementPlaying, waitForAudioElementToFinish, waitForStreamingPlaybackToFinish } from './chatbotWorkspaceModel';

export function ChatbotWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const assistantToolReturn = useMemo(() => readAssistantToolReturn(), []);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(() => loadSelectedSessionId());
  const [isChatFullscreen, setIsChatFullscreen] = useState(false);
  const [activeView, setActiveView] = useState<AssistantView>(() => {
    if (assistantToolReturn.toolId) return 'tools';
    const stored = window.localStorage.getItem(ASSISTANT_VIEW_STORAGE_KEY);
    return assistantSidebarItems.some((item) => item.id === stored) ? stored as AssistantView : 'chats';
  });
  const [activeUtilityPanel, setActiveUtilityPanel] = useState<UtilityPanel>('voice');
  const [isAssistantSidebarMinimized, setIsAssistantSidebarMinimized] = useState(() => {
    try {
      return window.localStorage.getItem(ASSISTANT_SIDEBAR_STORAGE_KEY) === 'true';
    } catch {
      return false;
    }
  });
  const [isSidePanelMinimized, setIsSidePanelMinimized] = useState(() => {
    try {
      return window.localStorage.getItem(ASSISTANT_SIDE_PANEL_STORAGE_KEY) === 'true';
    } catch {
      return false;
    }
  });
  const [audioStatus, setAudioStatus] = useState<string | null>(null);
  const [assistantMessageFeedback, setAssistantMessageFeedback] = useState<Record<string, AssistantMessageFeedback>>({});
  const [openMessageActionMenuId, setOpenMessageActionMenuId] = useState<string | null>(null);
  const [isAssistantSpeaking, setIsAssistantSpeaking] = useState(false);
  const [settingsStatus, setSettingsStatus] = useState<string | null>(null);
  const [quickSearchProgress, setQuickSearchProgress] = useState<string | null>(null);
  const [pendingUserMessage, setPendingUserMessage] = useState<ChatMessage | null>(null);
  const [activeChatJobId, setActiveChatJobId] = useState<string | null>(null);
  const [chatJobError, setChatJobError] = useState<string | null>(null);
  const [pastedChatImages, setPastedChatImages] = useState<PastedChatImage[]>([]);
  const [pastedChatTextFile, setPastedChatTextFile] = useState<PastedChatTextFile | null>(null);
  const [chatImageError, setChatImageError] = useState<string | null>(null);
  const [callStartedAt, setCallStartedAt] = useState<number | null>(null);
  const [callElapsedMs, setCallElapsedMs] = useState(0);
  const [voiceCaptureMode, setVoiceCaptureMode] = useState<VoiceCaptureMode>('idle');
  const [liveTranscript, setLiveTranscript] = useState('');
  const [liveInterimTranscript, setLiveInterimTranscript] = useState('');
  const [clearedVoiceTranscriptMessageIds, setClearedVoiceTranscriptMessageIds] = useState<Record<string, true>>({});
  const [autoSpeakResponses, setAutoSpeakResponses] = useState(true);
  const [spokenMessageIds, setSpokenMessageIds] = useState<Record<string, true>>({});
  const speechRecognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const assistantAudioRef = useRef<HTMLAudioElement | null>(null);
  const streamingTtsRef = useRef<StreamingTtsPlayback | null>(null);
  const assistantPlaybackTokenRef = useRef(0);
  const streamedSpeechQueueRef = useRef<Promise<void>>(Promise.resolve());
  const liveVoiceAutoSendTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const liveVoiceSubmissionInFlightRef = useRef(false);
  const liveVoiceActiveRef = useRef(false);
  const pendingCreatedSessionIdRef = useRef<string | null>(null);
  const reconciledChatJobIdRef = useRef<string | null>(null);
  const pendingLiveSessionProjectionRef = useRef<ApiChatSession | null>(null);
  const pendingLiveComposerResetRef = useRef(false);
  const pendingLiveProjectionCommitTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingChatSubmissionRef = useRef<{ fingerprint: string; id: string } | null>(null);
  const lastSubmittedVoiceTextRef = useRef('');
  const voiceTurnPerformanceRef = useRef<VoiceTurnPerformance | null>(null);
  const voiceTurnDiagnosticsRef = useRef<LiveCallDiagnosticsReporter | null>(null);
  const messagesContainerRef = useRef<HTMLDivElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const lastMessageScrollKeyRef = useRef('');
  const shouldStickToLatestMessageRef = useRef(true);
  const recordingChunksRef = useRef<Blob[]>([]);
  const queryClient = useQueryClient();
  const runtimeConfig = useMemo(() => createAssistantWorkspaceRuntimeConfig(), []);
  const [assistantSettings, setAssistantSettings] = useState<AssistantSettings>(() => loadAssistantSettings(runtimeConfig));
  const [liveCallRuntime, setLiveCallRuntime] = useState<CharacterLiveCallRuntime | null>(null);
  const liveCallRuntimeRef = useRef<CharacterLiveCallRuntime | null>(null);
  const eventStore = useMemo(() => createChatbotWorkspaceEventStore(runtimeConfig), [runtimeConfig]);
  const [activityEvents, setActivityEvents] = useState<AssistantWorkspaceEvent[]>(() =>
    eventStore.list(createWorkspaceEventFilter(runtimeConfig)),
  );
  const providerQuery = useQuery({ queryKey: ['platform', 'providers'], queryFn: () => omnixApiClient.listProviders() });
  const sessionsQuery = useQuery({ queryKey: ['feature', 'chatbot', 'sessions'], queryFn: async () => visibleChatSessions(await omnixApiClient.listChatSessions()) });
  const selectedSessionSummary = sessionsQuery.data?.sessions.find((session) => session.id === selectedSessionId);
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
  const sessionQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'session', selectedSessionId],
    queryFn: async () => noteChatSession(await omnixApiClient.getChatSession(selectedSessionId ?? '')),
    enabled: Boolean(selectedSessionId),
  });
  const chatJobQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'generation-job', activeChatJobId],
    queryFn: () => omnixApiClient.getJob(activeChatJobId ?? ''),
    enabled: Boolean(activeChatJobId),
    retry: false,
    refetchInterval: (query) => (
      CHAT_JOB_TERMINAL_STATUSES.has(String(query.state.data?.status ?? ''))
        ? false
        : CHAT_JOB_ACTIVE_POLL_MS
    ),
  });
  const chatJobInProgress = Boolean(
    activeChatJobId
    && !chatJobQuery.isError
    && (!chatJobQuery.data || !CHAT_JOB_TERMINAL_STATUSES.has(String(chatJobQuery.data.status))),
  );
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
  const liveCallRuntimeQuery = useQuery({
    queryKey: [
      'feature',
      'chatbot',
      'live-call-runtime',
      selectedSessionId,
      interactionQuery.data?.interaction_mode,
      interactionQuery.data?.character_id,
      interactionQuery.data?.character_profile_version,
    ],
    queryFn: () => characterClient.liveCallRuntime(selectedSessionId ?? ''),
    // Runtime preload includes the selected character's avatar/voice/memory.
    // Keep it out of ordinary system chats, but make it available in
    // Character mode so the right rail reflects the selected identity before
    // a call starts.
    enabled: Boolean(
      selectedSessionId
      && selectedSessionSummary?.interaction_mode === 'character'
      && interactionQuery.data?.interaction_mode === 'character',
    ),
  });
  const { register, handleSubmit, reset, setValue, getValues, watch, control, formState: { errors } } = useForm<ChatbotFormValues>({
    defaultValues: { content: '', providerId: runtimeConfig.defaultProviderId ?? '', modelId: runtimeConfig.defaultModelId ?? '' },
  });
  const selectedProviderId = watch('providerId');
  const selectedModelId = watch('modelId');
  const providerPayload = providerQuery.data;
  const chatProviders = useMemo(() => chatCapableProviders(providerPayload), [providerPayload]);
  const chatModels = useMemo(() => chatCapableModels(providerPayload, selectedProviderId), [providerPayload, selectedProviderId]);
  const chatSessions = sessionsQuery.data?.sessions ?? [];
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
  const sessionsLoading = sessionsQuery.isPending;
  const sessionsError = sessionsQuery.isError;
  const activeSessionLoading = Boolean(selectedSessionId) && sessionQuery.isPending;
  const activeSessionError = Boolean(selectedSessionId) && sessionQuery.isError;

  useEffect(() => {
    if (activeView !== 'settings') return;
    void import('./assistantSettingsBootstrap')
      .then(({ bootstrapCentralAssistantSettings }) => bootstrapCentralAssistantSettings())
      .then(() => setAssistantSettings(loadAssistantSettings(runtimeConfig)))
      .catch(() => undefined);
  }, [activeView, runtimeConfig]);

  useEffect(() => {
    const sessions = sessionsQuery.data?.sessions;
    if (!sessions) return;
    if (selectedSessionId && pendingCreatedSessionIdRef.current === selectedSessionId) {
      if (sessions.some((session) => session.id === selectedSessionId)) {
        pendingCreatedSessionIdRef.current = null;
      } else {
        // The create response selects the new session before the invalidated
        // list query can include it. Do not fall back to the previous chat
        // while that authoritative list catches up.
        return;
      }
    }
    // A newly created session can be selected before the invalidated list has
    // finished refetching. Keep it while the list is temporarily empty.
    if (selectedSessionId && (sessions.length === 0 || sessions.some((session) => session.id === selectedSessionId))) return;
    setSelectedSessionId(sessions[0]?.id ?? null);
  }, [selectedSessionId, sessionsQuery.data]);

  useEffect(() => {
    try {
      if (selectedSessionId) window.localStorage.setItem(ASSISTANT_SESSION_STORAGE_KEY, selectedSessionId);
      else window.localStorage.removeItem(ASSISTANT_SESSION_STORAGE_KEY);
    } catch {
      // Ignore local storage failures; the server remains the session authority.
    }
  }, [selectedSessionId]);

  useEffect(() => {
    const session = sessionQuery.data
      ?? sessionsQuery.data?.sessions.find((candidate) => candidate.id === selectedSessionId);
    window.dispatchEvent(new CustomEvent('omnix:chat-session-selected', {
      detail: {
        sessionId: selectedSessionId,
        session,
      },
    }));
  }, [selectedSessionId, sessionQuery.data, sessionsQuery.data]);

  useEffect(() => {
    const syncLiveChatSession = (event: Event) => {
      const sessionId = (event as CustomEvent<{ sessionId?: string }>).detail?.sessionId;
      if (!sessionId) return;
      if (pendingCreatedSessionIdRef.current && pendingCreatedSessionIdRef.current !== sessionId) {
        pendingCreatedSessionIdRef.current = null;
      }
      setSelectedSessionId(sessionId);
    };
    const syncCreatedChatSession = (event: Event) => {
      const session = (event as CustomEvent<{ session?: { id?: unknown; [key: string]: unknown } }>).detail?.session;
      const sessionId = typeof session?.id === 'string' ? session.id.trim() : '';
      if (!sessionId) return;

      pendingCreatedSessionIdRef.current = sessionId;
      queryClient.setQueryData(['feature', 'chatbot', 'session', sessionId], session);
      setSelectedSessionId(sessionId);
      setActiveView('chats');
    };
    window.addEventListener('omnix:live-chat-session-changed', syncLiveChatSession);
    window.addEventListener('omnix:chat-session-created', syncCreatedChatSession);
    return () => {
      window.removeEventListener('omnix:live-chat-session-changed', syncLiveChatSession);
      window.removeEventListener('omnix:chat-session-created', syncCreatedChatSession);
    };
  }, [queryClient]);

  useEffect(() => {
    window.localStorage.setItem(ASSISTANT_VIEW_STORAGE_KEY, activeView);
  }, [activeView]);

  useEffect(() => {
    try {
      window.localStorage.setItem(ASSISTANT_SIDE_PANEL_STORAGE_KEY, String(isSidePanelMinimized));
    } catch {
      // Ignore local storage failures; the panel remains usable for this session.
    }
  }, [isSidePanelMinimized]);

  useEffect(() => {
    try {
      window.localStorage.setItem(ASSISTANT_SIDEBAR_STORAGE_KEY, String(isAssistantSidebarMinimized));
    } catch {
      // Ignore local storage failures; the navigation remains usable for this session.
    }
  }, [isAssistantSidebarMinimized]);

  useEffect(() => {
    const handleSelectedChatImage = (event: Event): void => {
      const detail = (event as CustomEvent<Partial<PastedChatImage>>).detail;
      if (!detail || typeof detail.dataUrl !== 'string' || typeof detail.mimeType !== 'string' || !SUPPORTED_CHAT_IMAGE_TYPES.has(detail.mimeType) || chatImageDataUrls({ image_data_url: detail.dataUrl }).length !== 1) {
        setChatImageError('The selected file is not a supported image.');
        return;
      }
      const image = {
        dataUrl: detail.dataUrl,
        mimeType: detail.mimeType,
        size: typeof detail.size === 'number' && Number.isFinite(detail.size) ? detail.size : 0,
      };
      if (pastedChatImages.length >= MAX_CHAT_IMAGE_ATTACHMENTS && !pastedChatImages.some((candidate) => candidate.dataUrl === image.dataUrl)) {
        setChatImageError(`You can attach up to ${MAX_CHAT_IMAGE_ATTACHMENTS} images.`);
        return;
      }
      setPastedChatImages((current) => {
        if (current.some((candidate) => candidate.dataUrl === image.dataUrl)) return current;
        return [...current, image].slice(0, MAX_CHAT_IMAGE_ATTACHMENTS);
      });
      setPastedChatTextFile(null);
      setChatImageError(null);
    };
    const handleSelectedChatTextFile = (event: Event): void => {
      const detail = (event as CustomEvent<Partial<PastedChatTextFile>>).detail;
      if (!detail || typeof detail.filename !== 'string' || typeof detail.mimeType !== 'string' || typeof detail.text !== 'string' || !detail.filename.trim() || !detail.mimeType.trim() || !detail.text.trim() || detail.text.length > MAX_CHAT_TEXT_FILE_BYTES) {
        setChatImageError('The selected file is empty or too large. Choose a text file smaller than 100 KB.');
        return;
      }
      setPastedChatTextFile({
        filename: detail.filename.trim(),
        mimeType: detail.mimeType.trim(),
        size: typeof detail.size === 'number' && Number.isFinite(detail.size) ? detail.size : detail.text.length,
        text: detail.text,
      });
      setPastedChatImages([]);
      setChatImageError(null);
    };
    const handleChatImageError = (event: Event): void => {
      const detail = (event as CustomEvent<{ message?: unknown }>).detail;
      setChatImageError(typeof detail?.message === 'string' ? detail.message : 'Unable to attach the selected image.');
    };
    window.addEventListener('omnix:chat-image-selected', handleSelectedChatImage);
    window.addEventListener('omnix:chat-text-file-selected', handleSelectedChatTextFile);
    window.addEventListener('omnix:chat-image-error', handleChatImageError);
    return () => {
      window.removeEventListener('omnix:chat-image-selected', handleSelectedChatImage);
      window.removeEventListener('omnix:chat-text-file-selected', handleSelectedChatTextFile);
      window.removeEventListener('omnix:chat-image-error', handleChatImageError);
    };
  }, [pastedChatImages.length]);

  useEffect(() => {
    if (activeView !== 'chats') setIsChatFullscreen(false);
  }, [activeView]);

  useEffect(() => {
    if (!isChatFullscreen) return;
    const previousOverflow = document.body.style.overflow;
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') setIsChatFullscreen(false);
    };
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [isChatFullscreen]);

  useEffect(() => {
    if (!liveCallRuntimeQuery.data || liveVoiceActiveRef.current) return;
    liveCallRuntimeRef.current = liveCallRuntimeQuery.data;
    setLiveCallRuntime(liveCallRuntimeQuery.data);
  }, [liveCallRuntimeQuery.data]);

  useEffect(() => {
    const runtime = liveCallRuntimeRef.current;
    if (!runtime) return;
    const sameSession = runtime.session_id === selectedSessionId;
    const sameCharacter = selectedSessionSummary?.interaction_mode === 'character'
      && runtime.interaction_mode === 'character'
      && runtime.character_id === selectedSessionSummary.character_id;
    if (!sameSession || !sameCharacter) {
      liveCallRuntimeRef.current = null;
      setLiveCallRuntime(null);
    }
  }, [selectedSessionId, selectedSessionSummary?.character_id, selectedSessionSummary?.interaction_mode]);

  // Avatar selection can update the live runtime without changing the chat
  // session or interaction query key. Keep the React-owned runtime in sync
  // with the bridge so the visible Live Voice controls and fullscreen surface
  // switch rigs immediately instead of retaining the previous model.
  useEffect(() => {
    const syncSelectedAvatar = (event: Event): void => {
      const runtime = (event as CustomEvent<CharacterLiveCallRuntime | null>).detail;
      if (!runtime || runtime.session_id !== selectedSessionId) return;
      liveCallRuntimeRef.current = runtime;
      setLiveCallRuntime(runtime);
    };
    window.addEventListener(CHARACTER_AVATAR_RUNTIME_EVENT, syncSelectedAvatar);
    return () => window.removeEventListener(CHARACTER_AVATAR_RUNTIME_EVENT, syncSelectedAvatar);
  }, [selectedSessionId]);

  const sendMutation = useMutation({
    mutationFn: async (values: ChatbotFormValues) => {
      const providerId = values.providerId || undefined;
      const modelId = values.modelId || undefined;
      const content = values.content.trim() || attachmentDefaultMessage(pastedChatImages, pastedChatTextFile);
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
      return noteChatMessageSent(sessionId, await omnixApiClient.sendChatMessage(sessionId, {
        content,
        user_turn_id: values.userTurnId,
        provider_id: providerId,
        model_id: modelId,
        coding_approval_policy: assistantSettings.codingApprovalPolicy,
        image_data_urls: pastedChatImages.map((image) => image.dataUrl),
        text_attachment: pastedChatTextFile
          ? { filename: pastedChatTextFile.filename, mime_type: pastedChatTextFile.mimeType, text: pastedChatTextFile.text }
          : undefined,
      }));
    },
    onMutate: (values) => {
      markVoiceTurnPerformance('chatSubmitStartedAt');
      setChatJobError(null);
      const researchMode = assistantContextStore.getState().researchMode;
      const content = values.content.trim() || attachmentDefaultMessage(pastedChatImages, pastedChatTextFile);
      setQuickSearchProgress(researchMode === 'quick' ? content : null);
      setPendingUserMessage({
        id: `optimistic-user-${Date.now()}`,
        role: 'user',
        content,
        created_at: new Date().toISOString(),
        metadata: {
          ...(pastedChatImages.length > 0 ? {
            image_data_urls: pastedChatImages.map((image) => image.dataUrl),
            image_data_url: pastedChatImages[0].dataUrl,
          } : {}),
          ...(pastedChatTextFile ? { text_attachment: { filename: pastedChatTextFile.filename, mime_type: pastedChatTextFile.mimeType, text: pastedChatTextFile.text } } : {}),
        },
      });
    },
    onSuccess: (_result, values) => {
      markVoiceTurnPerformance('chatResponseReceivedAt');
      if (pendingChatSubmissionRef.current?.id === values.userTurnId) {
        pendingChatSubmissionRef.current = null;
      }
      setActiveChatJobId(_result.job.id);
      setChatJobError(null);
      setQuickSearchProgress(null);
      setPendingUserMessage(null);
      reset({ content: '', providerId: values.providerId, modelId: values.modelId });
      setPastedChatImages([]);
      setPastedChatTextFile(null);
      setChatImageError(null);
      setLiveTranscript('');
      setLiveInterimTranscript('');
      void queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot'] });
      void queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] });
    },
    onError: (error, values) => {
      setQuickSearchProgress(null);
      setPendingUserMessage(null);
      // Keep the submission identity after an ambiguous transport/server error.
      // Retrying the same payload must reuse the same idempotency key.
      setActiveChatJobId(null);
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

  useEffect(() => {
    const job = chatJobQuery.data;
    if (!job) return;
    const status = String(job.status);
    const jobSessionId = typeof job.input_payload?.session_id === 'string'
      ? job.input_payload.session_id
      : selectedSessionId;
    if (status === 'completed') {
      setChatJobError(null);
      if (reconciledChatJobIdRef.current === job.id) return;
      reconciledChatJobIdRef.current = job.id;
      void queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'session', jobSessionId] });
      void queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'sessions'] });
      void queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] });
      return;
    }
    if (status === 'failed') {
      const error = job.error as { message?: unknown } | null | undefined;
      setChatJobError(typeof error?.message === 'string' ? error.message : 'Chat generation failed.');
    }
    if (status === 'canceled' || status === 'stale') {
      setChatJobError('Chat generation was canceled.');
    }
    if (CHAT_JOB_TERMINAL_STATUSES.has(status)) {
      void queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'session', jobSessionId] });
      void queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'sessions'] });
      void queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] });
    }
  }, [chatJobQuery.data, queryClient, selectedSessionId]);

  const deleteSessionMutation = useMutation({
    mutationFn: (sessionId: string) => omnixApiClient.deleteChatSession(sessionId),
    onSuccess: async (_result, sessionId) => {
      queryClient.removeQueries({ queryKey: ['feature', 'chatbot', 'session', sessionId] });
      if (selectedSessionId === sessionId) {
        const remaining = chatSessions.filter((session) => session.id !== sessionId);
        setSelectedSessionId(remaining[0]?.id ?? null);
      }
      setAudioStatus('Chat session deleted.');
      await queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'sessions'] });
    },
    onError: (error) => {
      setAudioStatus(error instanceof Error ? error.message : 'Chat session delete failed.');
    },
  });

  const activeSession = selectFreshChatSession(sendMutation.data?.session, sessionQuery.data);
  const activeMessageCount = activeSession?.messages?.length ?? 0;
  const providerLabel = selectedProviderLabel(providerPayload, selectedProviderId);
  const modelLabel = selectedModelLabel(providerPayload, selectedModelId);
  const recentMessages = activeSession?.messages?.slice(-4) ?? [];
  const displayedMessages = pendingUserMessage
    ? [...(activeSession?.messages ?? []), pendingUserMessage]
    : activeSession?.messages ?? [];
  const displayedSessionId = activeSession?.id ?? selectedSessionId ?? 'pending-session';
  const visibleVoiceTranscriptMessages = recentMessages.filter((message) => !clearedVoiceTranscriptMessageIds[message.id]);
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
  useEffect(() => {
    liveCallPresentationStore.update({ autoSpeak: autoSpeakResponses });
    return () => liveCallPresentationStore.update({ autoSpeak: false });
  }, [autoSpeakResponses]);
  const voiceTranscriptRef = useRef<HTMLDivElement | null>(null);
  const lastVoiceTranscriptMessageId = visibleVoiceTranscriptMessages.at(-1)?.id;
  // The newest words stay in view as the transcript grows.
  useLayoutEffect(() => {
    const transcript = voiceTranscriptRef.current;
    if (transcript) transcript.scrollTop = transcript.scrollHeight;
  }, [lastVoiceTranscriptMessageId, liveVoiceTranscript]);
  const latestAssistantMessage = getLatestAssistantMessage(activeSession?.messages ?? []);
  const toolExecutionRows = useMemo(() => createToolExecutionRows(activityEvents), [activityEvents]);
  const enabledToolCount = runtimeConfig.features.toolExecution ? Math.max(toolExecutionRows.length, 3) : 0;
  const liveVoiceActive = callStartedAt !== null;
  // With the capture controller installed, the card shows its microphone stream.
  const captureLabels = livePresentation.captureOwned ? liveCaptureLabels(livePresentation.captureStatus) : null;
  const liveVoiceState = captureLabels ? captureLabels.state : liveVoiceActive ? voiceCaptureLabel(voiceCaptureMode) : voiceCaptureMode === 'error' ? 'Error' : 'Idle';
  const liveConnectionLabel = captureLabels ? captureLabels.connection : liveVoiceActive ? 'Connected' : 'Disconnected';
  const liveInputLabel = captureLabels ? (livePresentation.hearing ? 'Hearing you' : captureLabels.input) : liveVoiceActive ? 'Listening' : 'Idle';
  const liveVoiceInputMode = livePresentation.captureOwned
    ? livePresentation.hearing ? 'active' : livePresentation.captureStatus === 'connected' ? 'listening' : livePresentation.captureStatus
    : undefined;
  const liveCallButtonActive = livePresentation.captureOwned ? livePresentation.captureActive : liveVoiceActive;
  const liveCharacterName = liveCallRuntime?.interaction_mode === 'character'
    ? liveCallRuntime.display_name
    : selectedCharacter?.display_name;
  const liveIdentityLabel = liveCharacterName
    ? `Character Mode · ${liveCharacterName}`
    : 'System Assistant';
  const liveVoiceVisualMode = isAssistantSpeaking ? 'speaking'
    : livePresentation.captureOwned || livePresentation.speaking ? liveCallVoiceMode(livePresentation, liveVoiceActive)
      : liveVoiceActive ? 'listening' : voiceCaptureMode === 'error' ? 'error' : 'idle';
  const liveCallTimerLabel = formatCallDuration(callElapsedMs);
  const liveDraftText = [liveTranscript, liveInterimTranscript].filter(Boolean).join(' ').trim();
  const configuredVoiceId = assistantSettings.voiceId || runtimeConfig.ttsVoice || '';
  const activeVoiceId = liveCallRuntime?.voice_asset_id || configuredVoiceId;
  const activeVoiceLabel = voiceLabelForId(activeVoiceId, voiceProfiles);
  const selectedPersonalityLabel = personalityLabel(assistantSettings.personalityId);
  const speechInputLabel = runtimeConfig.sttServiceUrl ? 'STT service recording' : getSpeechRecognitionConstructor() ? 'Browser speech-to-text' : 'No STT input configured';
  const ttsOutputLabel = `${runtimeConfig.ttsServiceUrl ? 'TTS service' : 'Voice Studio TTS job'}${activeVoiceLabel ? ` · ${activeVoiceLabel}` : ''}`;

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
    eventStore.appendMany(sessionEvents.filter((event) => !currentEventIds.has(event.id)));
    setActivityEvents(eventStore.list(filter));
  }, [activeSession, eventStore, runtimeConfig]);

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
      void voiceTurnDiagnosticsRef.current?.close('workspace_unmounted');
      voiceTurnDiagnosticsRef.current = null;
    };
  }, []);

  useEffect(() => {
    const handleInterrupt = () => stopAssistantResponseAudio('Interrupted. Listening for your next message.');
    window.addEventListener(LIVE_VOICE_INTERRUPT_EVENT, handleInterrupt);
    return () => window.removeEventListener(LIVE_VOICE_INTERRUPT_EVENT, handleInterrupt);
  }, []);

  useEffect(() => {
    const handleDiagnostic = (event: Event) => {
      const detail = (event as CustomEvent<{ event?: unknown }>).detail;
      if (detail?.event === 'turn_finished') commitPendingLiveSessionProjection();
    };
    window.addEventListener(LIVE_CALL_DIAGNOSTIC_EVENT, handleDiagnostic);
    return () => window.removeEventListener(LIVE_CALL_DIAGNOSTIC_EVENT, handleDiagnostic);
  }, [autoSpeakResponses, queryClient]);

  useEffect(() => {
    const handlePerfEvent = (event: Event) => {
      const detail = (event as CustomEvent<VoicePerformanceStage>).detail;
      if (!detail || typeof detail.stage !== 'string' || typeof detail.turnId !== 'string') return;
      if (detail.stage === 'semantic_turn_assessed' || detail.stage === 'stt_final_requested') {
        if (voiceTurnDiagnosticsRef.current?.traceId !== `live-call:${detail.turnId}`) {
          void voiceTurnDiagnosticsRef.current?.close('turn_superseded');
          voiceTurnDiagnosticsRef.current = createLiveCallDiagnosticsReporter(`live-call:${detail.turnId}`);
        }
        recordVoiceTurnDiagnostic(detail.stage, {
          delay_ms: finiteNumber(detail.delayMs),
          pace: typeof detail.pace === 'string' ? detail.pace : undefined,
          probability_done: finiteNumber(detail.probabilityDone),
          reason: typeof detail.reason === 'string' ? detail.reason : undefined,
        });
      }
      if (detail.stage !== 'stt_final_received') return;
      if (!voiceTurnDiagnosticsRef.current) {
        voiceTurnDiagnosticsRef.current = createLiveCallDiagnosticsReporter(`live-call:${detail.turnId}`);
      }
      voiceTurnPerformanceRef.current = {
        turnId: detail.turnId,
        sttFinalReceivedAt: performance.now(),
        transcriptChars: typeof detail.transcriptChars === 'number' ? detail.transcriptChars : undefined,
        sttFinalizeMs: typeof detail.sttFinalizeMs === 'number' ? detail.sttFinalizeMs : undefined,
      };
      console.info('[Omnix Voice Perf] voice turn accepted', {
        turnId: detail.turnId,
        transcriptChars: voiceTurnPerformanceRef.current.transcriptChars,
        sttFinalizeMs: voiceTurnPerformanceRef.current.sttFinalizeMs,
      });
      recordVoiceTurnDiagnostic('stt_final_received', {
        stt_finalize_ms: voiceTurnPerformanceRef.current.sttFinalizeMs,
        input_chars: voiceTurnPerformanceRef.current.transcriptChars,
      });
    };
    window.addEventListener(LIVE_VOICE_PERF_EVENT, handlePerfEvent);
    return () => window.removeEventListener(LIVE_VOICE_PERF_EVENT, handlePerfEvent);
  }, []);

  useEffect(() => {
    if (unifiedLiveVoiceAudioInstalled()) return;
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

  function currentLiveCallVoiceId(): string {
    const runtimeVoiceAssetId = liveCallRuntimeRef.current?.voice_asset_id;
    if (runtimeVoiceAssetId) {
      const asset = voiceProfiles.find((candidate) => candidate.id === runtimeVoiceAssetId);
      return asset ? voiceProfileId(asset) : runtimeVoiceAssetId.replace(/^voice-cloning:/, '');
    }
    return assistantSettings.voiceId || runtimeConfig.ttsVoice || '';
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

  async function startVoiceInput(): Promise<void> {
    setActiveUtilityPanel('voice');
    setLiveTranscript('');
    setLiveInterimTranscript('');
    if (runtimeConfig.sttServiceUrl) {
      await startSttRecordingFallback();
      return;
    }
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
              scheduleLiveVoiceAutoSend(next);
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
        scheduleLiveVoiceAutoSend(next);
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
    clearLiveVoiceAutoSendTimer();
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

  function submitComposerMessage(values: ChatbotFormValues): void {
    if (liveVoiceActiveRef.current) {
      void submitVoiceTranscriptContent(values.content, { manual: true });
      return;
    }
    sendMutation.mutate({ ...values, userTurnId: chatSubmissionId(values) });
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
    const values = { content: trimmed, providerId: selectedProviderId, modelId: selectedModelId };
    sendMutation.mutate({ ...values, userTurnId: chatSubmissionId(values) });
  }

  function chatSubmissionId(values: ChatbotFormValues): string {
    const fingerprint = JSON.stringify([
      values.content.trim(),
      values.providerId,
      values.modelId,
      pastedChatImages.map((image) => image.dataUrl),
      pastedChatTextFile?.filename ?? null,
      pastedChatTextFile?.text ?? null,
    ]);
    if (pendingChatSubmissionRef.current?.fingerprint === fingerprint) {
      return pendingChatSubmissionRef.current.id;
    }
    const id = `web-user-turn:${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;
    pendingChatSubmissionRef.current = { fingerprint, id };
    return id;
  }

  useEffect(() => liveChatSubmissionGateway.register(async (input) => {
    if (input.sessionId !== selectedSessionId) throw new Error('live_chat_session_mismatch');
    await sendStreamingVoiceTranscript(input.text);
  }), [selectedSessionId, selectedProviderId, selectedModelId, assistantSettings, autoSpeakResponses]);

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

  function selectSidebarSession(session: SessionListEntry): void {
    setSelectedSessionId(session.id);
    setActiveView('chats');
    window.dispatchEvent(new CustomEvent('omnix:live-chat-session-changed', { detail: { sessionId: session.id } }));
  }


  function handleComposerTextareaKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key !== 'Enter' || event.shiftKey || event.altKey || event.ctrlKey || event.metaKey || event.nativeEvent.isComposing) return;

    event.preventDefault();
    event.currentTarget.form?.requestSubmit();
  }

  function handleComposerPaste(event: ReactClipboardEvent<HTMLTextAreaElement>): void {
    const imageItems = Array.from(event.clipboardData.items).filter((item) => item.type.startsWith('image/'));
    if (!imageItems.length) return;

    event.preventDefault();
    const files = imageItems.map((item) => item.getAsFile()).filter((file): file is File => Boolean(file));
    if (files.length !== imageItems.length) {
      setChatImageError('Unable to read one or more pasted images.');
      return;
    }
    if (files.some((file) => !SUPPORTED_CHAT_IMAGE_TYPES.has(file.type))) {
      setChatImageError('Paste PNG, JPEG, or WebP images.');
      return;
    }
    if (files.some((file) => file.size > MAX_CHAT_IMAGE_BYTES)) {
      setChatImageError('Each image must be 5 MB or smaller.');
      return;
    }
    if (files.length > MAX_CHAT_IMAGE_ATTACHMENTS - pastedChatImages.length) {
      setChatImageError(`You can attach up to ${MAX_CHAT_IMAGE_ATTACHMENTS} images.`);
      return;
    }

    setChatImageError(null);
    void Promise.all(files.map(async (file) => ({
      dataUrl: await readFileAsDataUrl(file),
      mimeType: file.type,
      size: file.size,
    })))
      .then((images) => {
        setPastedChatImages((current) => {
          const next = [...current];
          for (const image of images) {
            if (next.length >= MAX_CHAT_IMAGE_ATTACHMENTS) break;
            if (!next.some((candidate) => candidate.dataUrl === image.dataUrl)) next.push(image);
          }
          return next;
        });
        setPastedChatTextFile(null);
      })
      .catch(() => setChatImageError('Unable to read one or more pasted images.'));
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

  async function playAssistantResponseAudio(text: string): Promise<void> {
    stopAssistantPcmStream();
    const spokenText = text.trim();
    if (!spokenText) {
      setAudioStatus('No assistant response is ready to play.');
      return;
    }
    const playbackToken = assistantPlaybackTokenRef.current + 1;
    assistantPlaybackTokenRef.current = playbackToken;
    let revokePlayableAudioSource: (() => void) | undefined;
    try {
      markVoiceTurnPerformance('ttsStartedAt');
      recordVoiceTurnDiagnostic('tts_request_started', {
        text_chars: spokenText.length,
      });
      setAudioStatus(activeVoiceId ? `Synthesizing ${activeVoiceLabel || activeVoiceId} voice…` : 'Synthesizing response voice…');
      if (assistantPlaybackTokenRef.current !== playbackToken) return;
      const audioSource = runtimeConfig.ttsServiceUrl
        ? await synthesizeWithTtsService(spokenText)
        : await synthesizeWithVoiceJob(spokenText);
      if (assistantPlaybackTokenRef.current !== playbackToken) return;
      markVoiceTurnPerformance('ttsReadyAt');
      recordVoiceTurnDiagnostic('tts_output_ready', { playback_mode: 'batch' });
      if (canUseDecodedAudioPlayback()) {
        await playDecodedAssistantResponseAudio(audioSource, playbackToken);
        return;
      }
      stopAssistantResponseAudio(undefined, { cancelPending: false });
      const playableAudio = makePlayableAudioSource(audioSource);
      revokePlayableAudioSource = playableAudio.revoke;
      console.info('[Omnix Voice Perf] batch TTS audio source ready', {
        sourceKind: playableAudio.revoke ? 'blob-url' : audioSource.startsWith('data:') ? 'data-url' : 'url',
        sourceLength: audioSource.length,
      });
      const audio = new Audio(playableAudio.url);
      assistantAudioRef.current = audio;
      const clearSpeakingState = () => {
        if (assistantAudioRef.current === audio) assistantAudioRef.current = null;
        revokePlayableAudioSource?.();
        revokePlayableAudioSource = undefined;
        setIsAssistantSpeaking(false);
      };
      if (typeof audio.addEventListener === 'function') {
        audio.addEventListener('ended', clearSpeakingState, { once: true });
        audio.addEventListener('pause', clearSpeakingState, { once: true });
        audio.addEventListener('error', () => {
          console.info('[Omnix Voice Perf] batch TTS audio element error', {
            code: audio.error?.code,
            message: audio.error?.message,
            networkState: audio.networkState,
            readyState: audio.readyState,
          });
          clearSpeakingState();
        }, { once: true });
      }
      setIsAssistantSpeaking(true);
      audio.preload = 'auto';
      audio.playbackRate = currentLiveCallSpeechStyle().speed;
      const playing = waitForAudioElementPlaying(audio);
      await audio.play();
      await playing;
      if (assistantPlaybackTokenRef.current !== playbackToken) return;
      markVoiceTurnPerformance('audioPlayStartedAt');
      recordVoiceTurnDiagnostic('audio_playback_started', { playback_mode: 'audio_element' });
      console.info('[Omnix Voice Perf] batch TTS audio playing', {
        duration: Number.isFinite(audio.duration) ? Math.round(audio.duration * 1000) : null,
        readyState: audio.readyState,
        networkState: audio.networkState,
      });
      logVoiceTurnPerformance();
      setAudioStatus(activeVoiceId ? 'Playing cloned response voice.' : 'Playing response voice.');
      await waitForAudioElementToFinish(audio);
    } catch (error) {
      assistantAudioRef.current = null;
      revokePlayableAudioSource?.();
      setIsAssistantSpeaking(false);
      setAudioStatus(error instanceof Error ? error.message : 'Response audio playback failed.');
    }
  }

  function stopAssistantResponseAudio(status?: string, options: { cancelPending?: boolean } = {}): void {
    if (options.cancelPending !== false) assistantPlaybackTokenRef.current += 1;
    const audio = assistantAudioRef.current;
    assistantAudioRef.current = null;
    stopStreamingTtsPlayback();
    if (audio) {
      try { audio.pause(); } catch { /* ignore playback cleanup failures */ }
      try { audio.currentTime = 0; } catch { /* ignore playback cleanup failures */ }
    }
    setIsAssistantSpeaking(false);
    if (status) setAudioStatus(status);
  }

  async function playDecodedAssistantResponseAudio(audioSource: string, playbackToken: number): Promise<void> {
    const liveWindow = window as StreamingTtsWindow;
    const AudioContextCtor = liveWindow.AudioContext ?? liveWindow.webkitAudioContext;
    if (!AudioContextCtor) throw new Error('Decoded TTS playback requires AudioContext support.');

    stopAssistantResponseAudio(undefined, { cancelPending: false });
    const audioContext = new AudioContextCtor({ latencyHint: 'interactive', sampleRate: STREAMING_TTS_SAMPLE_RATE });
    const playback: StreamingTtsPlayback = { audioContext, abortController: new AbortController(), sources: [], closed: false };
    streamingTtsRef.current = playback;

    try {
      const bytes = await audioSourceToArrayBuffer(audioSource);
      const audioBuffer = await audioContext.decodeAudioData(bytes.slice(0));
      if (audioContext.state !== 'running') await audioContext.resume();
      if (assistantPlaybackTokenRef.current !== playbackToken) return;

      const source = audioContext.createBufferSource();
      source.buffer = audioBuffer;
      source.playbackRate.value = currentLiveCallSpeechStyle().speed;
      source.connect(audioContext.destination);
      const startAt = audioContext.currentTime + STREAMING_TTS_RECOVERY_DELAY_SECONDS;
      source.start(startAt);
      playback.sources.push(source);
      setIsAssistantSpeaking(true);
      setAudioStatus(activeVoiceId ? 'Playing cloned response voice.' : 'Playing response voice.');
      console.info('[Omnix Voice Perf] decoded TTS audio scheduled', {
        bytes: bytes.byteLength,
        durationMs: Math.round(audioBuffer.duration * 1000),
        sampleRate: audioBuffer.sampleRate,
        scheduledLeadMs: Math.round((startAt - audioContext.currentTime) * 1000),
      });

      source.addEventListener('ended', () => {
        playback.sources = playback.sources.filter((entry) => entry !== source);
        if (streamingTtsRef.current === playback) {
          streamingTtsRef.current = null;
          setIsAssistantSpeaking(false);
          void audioContext.close().catch(() => undefined);
        }
      }, { once: true });

      window.setTimeout(() => {
        if (assistantPlaybackTokenRef.current !== playbackToken || playback.closed) return;
        markVoiceTurnPerformance('audioPlayStartedAt');
        recordVoiceTurnDiagnostic('audio_playback_started', { playback_mode: 'decoded_audio_context' });
        console.info('[Omnix Voice Perf] decoded TTS audio start', {
          audioContextTime: Number(audioContext.currentTime.toFixed(3)),
          activeSources: playback.sources.length,
        });
        logVoiceTurnPerformance();
      }, Math.max(0, (startAt - audioContext.currentTime) * 1000));

      await waitForStreamingPlaybackToFinish(playback, () => assistantPlaybackTokenRef.current !== playbackToken);
    } catch (error) {
      stopStreamingTtsPlayback();
      throw error;
    }
  }

  function stopStreamingTtsPlayback(): void {
    const playback = streamingTtsRef.current;
    streamingTtsRef.current = null;
    if (!playback) return;
    playback.closed = true;
    try { playback.abortController.abort(); } catch { /* ignore stream cleanup failures */ }
    playback.sources.forEach((source) => {
      try { source.stop(); } catch { /* ignore stream cleanup failures */ }
      try { source.disconnect(); } catch { /* ignore stream cleanup failures */ }
    });
    void playback.audioContext.close().catch(() => undefined);
  }

  function dispatchLiveVoiceStop(): void {
    window.dispatchEvent(new CustomEvent(LIVE_VOICE_STOP_EVENT));
  }

  function markVoiceTurnPerformance(stage: VoiceTurnTimestampStage): void {
    const current = voiceTurnPerformanceRef.current;
    if (!current) return;
    if (current[stage] === undefined) current[stage] = performance.now();
  }

  function recordVoiceTurnDiagnostic(event: string, details: Record<string, unknown> = {}): void {
    const reporter = voiceTurnDiagnosticsRef.current;
    const performanceState = voiceTurnPerformanceRef.current;
    if (!reporter) return;
    const reporterTurnId = reporter.traceId.startsWith('live-call:voice-turn:')
      ? reporter.traceId.slice('live-call:'.length)
      : performanceState?.turnId;
    const performanceMatchesReporter = Boolean(
      performanceState && reporterTurnId && performanceState.turnId === reporterTurnId,
    );
    reporter.record(event, {
      turn_id: reporterTurnId,
      elapsed_from_stt_final_ms: performanceMatchesReporter && performanceState
        ? Math.round(performance.now() - performanceState.sttFinalReceivedAt)
        : undefined,
      ...details,
    }, 'chatbot_workspace');
  }

  function logVoiceTurnPerformance(): void {
    const current = voiceTurnPerformanceRef.current;
    if (!current?.audioPlayStartedAt || current.turnaroundLogged) return;
    current.turnaroundLogged = true;

    const totalMs = Math.round(current.audioPlayStartedAt - current.sttFinalReceivedAt);
    const rows = [
      { segment: 'STT finalize request -> final transcript', ms: current.sttFinalizeMs ?? null },
      { segment: 'Final transcript -> chat submit', ms: elapsedMs(current.sttFinalReceivedAt, current.chatSubmitStartedAt) },
      { segment: 'Chat submit -> chat response', ms: elapsedMs(current.chatSubmitStartedAt, current.chatResponseReceivedAt) },
      { segment: 'Chat response -> TTS start', ms: elapsedMs(current.chatResponseReceivedAt, current.ttsStartedAt) },
      { segment: 'TTS synth/output ready', ms: elapsedMs(current.ttsStartedAt, current.ttsReadyAt) },
      { segment: 'TTS ready -> first audio scheduled', ms: elapsedMs(current.ttsReadyAt, current.audioFirstScheduledAt) },
      { segment: 'First audio scheduled -> playback started', ms: elapsedMs(current.audioFirstScheduledAt, current.audioPlayStartedAt) },
      { segment: 'Audio ready -> playback started', ms: elapsedMs(current.ttsReadyAt, current.audioPlayStartedAt) },
      { segment: 'Total final transcript -> audio playback', ms: totalMs },
    ];

    console.info('[Omnix Voice Perf] voice audio turnaround', {
      turnId: current.turnId,
      totalMs,
      targetMs: 1000,
      withinTarget: totalMs < 1000,
      transcriptChars: current.transcriptChars,
    });
    console.table(rows);
    recordVoiceTurnDiagnostic('voice_audio_turnaround', {
      total_ms: totalMs,
      target_ms: 1000,
      within_target: totalMs < 1000,
      stt_finalize_ms: current.sttFinalizeMs,
      final_to_chat_submit_ms: elapsedMs(current.sttFinalReceivedAt, current.chatSubmitStartedAt),
      chat_submit_to_response_open_ms: elapsedMs(current.chatSubmitStartedAt, current.chatResponseReceivedAt),
      response_open_to_first_chunk_ms: elapsedMs(current.chatResponseReceivedAt, current.llmFirstChunkReceivedAt),
      first_chunk_to_llm_complete_ms: elapsedMs(current.llmFirstChunkReceivedAt, current.llmCompletedAt),
      tts_start_to_ready_ms: elapsedMs(current.ttsStartedAt, current.ttsReadyAt),
      tts_ready_to_playback_ms: elapsedMs(current.ttsReadyAt, current.audioPlayStartedAt),
    });
  }

  async function synthesizeWithTtsService(text: string): Promise<string> {
    if (!runtimeConfig.ttsServiceUrl) throw new Error('TTS service URL is not configured.');
    const ttsClient = createTtsServiceClient({ baseUrl: runtimeConfig.ttsServiceUrl, transport: createFetchSpeechServiceTransport() });
    const response = await ttsClient.synthesizeSpeech({
      text,
      voice: currentLiveCallVoiceId() || undefined,
      format: 'wav',
      metadata: { source: 'chatbot_response_playback', sessionId: activeSession?.id, providerId: selectedProviderId || runtimeConfig.defaultProviderId, modelId: selectedModelId || runtimeConfig.defaultModelId, speechStyle: currentLiveCallSpeechStyle(), characterId: liveCallRuntimeRef.current?.character_id, characterProfileVersion: liveCallRuntimeRef.current?.character_profile_version },
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
        speaker: currentLiveCallDisplayName(),
        voice_id: currentLiveCallVoiceId() || null,
        script_mode: 'single_speaker',
        script_speakers: [{ name: currentLiveCallDisplayName(), count: 1 }],
        script_segments: [{ index: 0, speaker: currentLiveCallDisplayName(), text }],
        character_voice_assignments: [{ speaker: currentLiveCallDisplayName(), voice_id: currentLiveCallVoiceId() || null, style: liveCallRuntimeRef.current?.speech_style.expressiveness || selectedPersonalityLabel, line_count: 1 }],
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
