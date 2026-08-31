import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ClipboardEvent as ReactClipboardEvent, CSSProperties, KeyboardEvent, UIEvent } from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import {
  ApiError,
  omnixApiClient,
  type AssetListResponse,
  type ChatSession as ApiChatSession,
  type CodingApprovalPolicy,
  type JobRecord,
  type ProviderFacadePayload,
} from '../../api/client';
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
import {
  createLiveCallDiagnosticsReporter,
  type LiveCallDiagnosticsReporter,
} from '../assistant-workspace/live-call-diagnostics-client';
import { liveChatSubmissionGateway } from '../assistant-workspace/live-chat-submission-gateway';
import { createAssistantWorkspaceRuntimeConfig } from '../assistant-workspace/runtime-config';
import { AssistantToolSettingsPanel } from './AssistantToolSettingsPanel';
import { CharacterManagementPanel } from './CharacterManagementPanel';
import { ChatIdentityModeControl } from './ChatIdentityModeControl';
import { LiveAgentToolProposalCard, liveAgentToolProposals } from './LiveAgentToolProposalCard';
import { LiveChatFullscreenShell } from './LiveChatFullscreenShell';
import { Live2DZoomControl } from './Live2DZoomControl';
import { Live2DMotionControl } from './Live2DMotionControl';
import { MemoryManagementPanel } from './MemoryManagementPanel';
import { OmnixRunCard } from './OmnixRunCard';
import { enterLiveChatFullscreen } from './live-chat-fullscreen-controller';
import { characterClient, type CharacterLiveCallRuntime, type LiveCallSpeechStyle } from './characterClient';
import { CHARACTER_AVATAR_RUNTIME_EVENT } from './liveCharacterAvatarBridge';
import { isDeepResearchMessage, renderMarkdownHtml, renderResearchReportHtml } from './markdownRenderer';

interface ChatbotFormValues {
  content: string;
  providerId: string;
  modelId: string;
}

type PastedChatImage = {
  dataUrl: string;
  mimeType: string;
  size: number;
};

type PastedChatTextFile = {
  filename: string;
  mimeType: string;
  size: number;
  text: string;
};

const MAX_CHAT_IMAGE_BYTES = 5 * 1024 * 1024;
const MAX_CHAT_TEXT_FILE_BYTES = 100 * 1024;
const SUPPORTED_CHAT_IMAGE_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp']);
const DEFAULT_IMAGE_MESSAGE = 'Please analyze the attached image.';
const DEFAULT_TEXT_FILE_MESSAGE = 'Please analyze the attached file.';

type AssistantView = 'chats' | 'voice' | 'tools' | 'characters' | 'memory' | 'settings';
type UtilityPanel = 'voice' | 'tools';
type VoiceCaptureMode = 'idle' | 'listening' | 'recording' | 'transcribing' | 'error';
type VoiceProfileAsset = AssetListResponse['assets'][number];
type PersonalityId = 'default' | 'concise' | 'coach' | 'technical' | 'creative' | 'custom';
type AssistantMessageFeedback = 'liked' | 'disliked';

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

type AssistantSettings = {
  voiceId: string;
  personalityId: PersonalityId;
  customPersonality: string;
  liveVoiceSensitivity: number;
  codingApprovalPolicy: CodingApprovalPolicy;
};

const assistantSidebarItems: Array<{ id: AssistantView; label: string; icon: string }> = [
  { id: 'chats', label: 'Chats', icon: '▣' },
  { id: 'voice', label: 'Voice Sessions', icon: '◉' },
  { id: 'tools', label: 'Tools', icon: '⚒' },
  { id: 'characters', label: 'Characters', icon: '♙' },
  { id: 'memory', label: 'Memory', icon: '▦' },
  { id: 'settings', label: 'Settings', icon: '⚙' },
];

const suggestedPrompts = ['Tell me a fun fact', 'Recommend a movie', 'Give me productivity tips'] as const;
const CALL_TIMER_TICK_MS = 1_000;
const DEFAULT_SPEECH_LANGUAGE = 'en-US';
const DEFAULT_LIVE_VOICE_SENSITIVITY = 55;
const DEFAULT_CODING_APPROVAL_POLICY: CodingApprovalPolicy = 'ask_sensitive';
const codingApprovalOptions: Array<{ value: CodingApprovalPolicy; label: string; description: string }> = [
  { value: 'always_ask', label: 'Ask for approval', description: 'Approve coding commands and file edits before they run.' },
  { value: 'ask_sensitive', label: 'Approve for me', description: 'Run safe coding actions automatically and ask only for higher-risk actions.' },
  { value: 'allow_automatic', label: 'Full access', description: 'Run workspace-scoped coding actions without approval prompts.' },
];
const ASSISTANT_SETTINGS_STORAGE_KEY = 'omnix.chatbot.assistantSettings';
const ASSISTANT_VIEW_STORAGE_KEY = 'omnix.chatbot.activeView';
const ASSISTANT_SESSION_STORAGE_KEY = 'omnix.chatbot.activeSession';
const LIVE_VOICE_INTERRUPT_EVENT = 'omnix:assistant-voice-interrupt';
const LIVE_VOICE_PERF_EVENT = 'omnix:assistant-voice-perf';
const LIVE_VOICE_STOP_EVENT = 'omnix:assistant-live-voice-stop';
const LIVE_CALL_DIAGNOSTIC_EVENT = 'omnix:live-call-diagnostic';
const STREAMING_TTS_SAMPLE_RATE = 24_000;
const STREAMING_TTS_START_DELAY_SECONDS = 0.09;
const STREAMING_TTS_RECOVERY_DELAY_SECONDS = 0.05;
const STREAMED_TTS_MIN_PHRASE_CHARS = 90;
const LIVE_VOICE_AUTO_SEND_DELAY_MS = 600;
const LIVE_SESSION_PROJECTION_FALLBACK_DELAY_MS = 0;

function liveVoiceSubmissionKey(content: string): string {
  return content.trim().toLocaleLowerCase().replace(/[^\p{L}\p{N}']+/gu, ' ').trim();
}

function finiteNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function dedicatedLiveVoiceControllerInstalled(): boolean {
  return Boolean((window as StreamingTtsWindow).__omnixLiveVoiceControllerInstalled);
}

function unifiedLiveVoiceAudioInstalled(): boolean {
  return Boolean((window as StreamingTtsWindow).__omnixLiveVoiceUnifiedAudioInstalled);
}

type VoicePerformanceStage = {
  stage?: unknown;
  turnId?: unknown;
  transcriptChars?: unknown;
  sttFinalizeMs?: unknown;
  delayMs?: unknown;
  pace?: unknown;
  probabilityDone?: unknown;
  reason?: unknown;
};

type ChatStreamEvent = {
  type?: string;
  text?: string;
  message?: unknown;
  session?: ApiChatSession;
};

type VoiceTurnPerformance = {
  turnId: string;
  sttFinalReceivedAt: number;
  transcriptChars?: number;
  sttFinalizeMs?: number;
  chatSubmitStartedAt?: number;
  chatResponseReceivedAt?: number;
  llmFirstChunkReceivedAt?: number;
  llmCompletedAt?: number;
  ttsStartedAt?: number;
  ttsReadyAt?: number;
  ttsFirstChunkReceivedAt?: number;
  audioFirstScheduledAt?: number;
  audioPlayStartedAt?: number;
  turnaroundLogged?: boolean;
};

type VoiceTurnTimestampStage = Exclude<
  keyof VoiceTurnPerformance,
  'turnId' | 'sttFinalReceivedAt' | 'transcriptChars' | 'sttFinalizeMs' | 'turnaroundLogged'
>;

type StreamingTtsPlayback = {
  audioContext: AudioContext;
  abortController: AbortController;
  sources: AudioBufferSourceNode[];
  closed: boolean;
};

type StreamingTtsWindow = Window & typeof globalThis & {
  AudioContext?: typeof AudioContext;
  webkitAudioContext?: typeof AudioContext;
  __omnixLiveVoiceControllerInstalled?: boolean;
  __omnixLiveVoiceUnifiedAudioInstalled?: boolean;
};

const personalityOptions: Array<{ id: PersonalityId; label: string; prompt: string }> = [
  {
    id: 'default',
    label: 'Omnix Default',
    prompt: 'You are Omnix Assistant. Be helpful, clear, and practical.',
  },
  {
    id: 'concise',
    label: 'Concise operator',
    prompt: 'You are Omnix Assistant. Be direct, concise, and action-oriented. Prefer short answers unless detail is requested.',
  },
  {
    id: 'coach',
    label: 'Friendly coach',
    prompt: 'You are Omnix Assistant. Be warm, encouraging, and practical. Ask at most one clarifying question when needed.',
  },
  {
    id: 'technical',
    label: 'Technical expert',
    prompt: 'You are Omnix Assistant. Be precise, technical, and implementation-focused. Include concrete steps and caveats.',
  },
  {
    id: 'creative',
    label: 'Creative collaborator',
    prompt: 'You are Omnix Assistant. Be imaginative, collaborative, and vivid while staying useful and grounded.',
  },
  {
    id: 'custom',
    label: 'Custom personality',
    prompt: '',
  },
];

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
  const [audioStatus, setAudioStatus] = useState<string | null>(null);
  const [assistantMessageFeedback, setAssistantMessageFeedback] = useState<Record<string, AssistantMessageFeedback>>({});
  const [openMessageActionMenuId, setOpenMessageActionMenuId] = useState<string | null>(null);
  const [isAssistantSpeaking, setIsAssistantSpeaking] = useState(false);
  const [settingsStatus, setSettingsStatus] = useState<string | null>(null);
  const [quickSearchProgress, setQuickSearchProgress] = useState<string | null>(null);
  const [pendingUserMessage, setPendingUserMessage] = useState<ChatMessage | null>(null);
  const [pastedChatImage, setPastedChatImage] = useState<PastedChatImage | null>(null);
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
  const pendingLiveSessionProjectionRef = useRef<ApiChatSession | null>(null);
  const pendingLiveComposerResetRef = useRef(false);
  const pendingLiveProjectionCommitTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
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
  const sessionsQuery = useQuery({ queryKey: ['feature', 'chatbot', 'sessions'], queryFn: () => omnixApiClient.listChatSessions() });
  const assetsQuery = useQuery({
    queryKey: ['platform', 'assets', 'chatbot-settings'],
    queryFn: () => omnixApiClient.listAssets(),
    enabled: activeView === 'chats' || activeView === 'settings',
  });
  const sessionQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'session', selectedSessionId],
    queryFn: () => omnixApiClient.getChatSession(selectedSessionId ?? ''),
    enabled: Boolean(selectedSessionId),
  });
  const interactionQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'interaction', selectedSessionId],
    queryFn: () => characterClient.session(selectedSessionId ?? ''),
    enabled: Boolean(selectedSessionId),
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
    enabled: Boolean(selectedSessionId && interactionQuery.data),
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
  const voiceProfiles = useMemo(() => getVoiceProfileAssets(assetsQuery.data), [assetsQuery.data]);
  const sessionsLoading = sessionsQuery.isPending;
  const sessionsError = sessionsQuery.isError;
  const activeSessionLoading = Boolean(selectedSessionId) && sessionQuery.isPending;
  const activeSessionError = Boolean(selectedSessionId) && sessionQuery.isError;

  useEffect(() => {
    const sessions = sessionsQuery.data?.sessions;
    if (!sessions) return;
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
      if (sessionId) setSelectedSessionId(sessionId);
    };
    window.addEventListener('omnix:live-chat-session-changed', syncLiveChatSession);
    return () => window.removeEventListener('omnix:live-chat-session-changed', syncLiveChatSession);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(ASSISTANT_VIEW_STORAGE_KEY, activeView);
  }, [activeView]);

  useEffect(() => {
    const handleSelectedChatImage = (event: Event): void => {
      const detail = (event as CustomEvent<Partial<PastedChatImage>>).detail;
      if (!detail || typeof detail.dataUrl !== 'string' || typeof detail.mimeType !== 'string' || !SUPPORTED_CHAT_IMAGE_TYPES.has(detail.mimeType) || !chatImageDataUrl({ image_data_url: detail.dataUrl })) {
        setChatImageError('The selected file is not a supported image.');
        return;
      }
      setPastedChatImage({
        dataUrl: detail.dataUrl,
        mimeType: detail.mimeType,
        size: typeof detail.size === 'number' && Number.isFinite(detail.size) ? detail.size : 0,
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
      setPastedChatImage(null);
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
  }, []);

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
      const content = values.content.trim() || attachmentDefaultMessage(pastedChatImage, pastedChatTextFile);
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
      return omnixApiClient.sendChatMessage(sessionId, {
        content,
        provider_id: providerId,
        model_id: modelId,
        coding_approval_policy: assistantSettings.codingApprovalPolicy,
        image_data_url: pastedChatImage?.dataUrl,
        text_attachment: pastedChatTextFile
          ? { filename: pastedChatTextFile.filename, mime_type: pastedChatTextFile.mimeType, text: pastedChatTextFile.text }
          : undefined,
      });
    },
    onMutate: (values) => {
      markVoiceTurnPerformance('chatSubmitStartedAt');
      const researchMode = document.querySelector<HTMLSelectElement>('select[aria-label="Web research mode"]')?.value;
      const content = values.content.trim() || attachmentDefaultMessage(pastedChatImage, pastedChatTextFile);
      setQuickSearchProgress(researchMode === 'quick' ? content : null);
      setPendingUserMessage({
        id: `optimistic-user-${Date.now()}`,
        role: 'user',
        content,
        created_at: new Date().toISOString(),
        ...((pastedChatImage || pastedChatTextFile) ? {
          metadata: {
            ...(pastedChatImage ? { image_data_url: pastedChatImage.dataUrl } : {}),
            ...(pastedChatTextFile ? { text_attachment: { filename: pastedChatTextFile.filename, mime_type: pastedChatTextFile.mimeType, text: pastedChatTextFile.text } } : {}),
          },
        } : {}),
      });
    },
    onSuccess: (_result, values) => {
      markVoiceTurnPerformance('chatResponseReceivedAt');
      setQuickSearchProgress(null);
      setPendingUserMessage(null);
      reset({ content: '', providerId: values.providerId, modelId: values.modelId });
      setPastedChatImage(null);
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
  const generationComplete = Boolean(activeSession?.messages?.some((message) => message.role === 'assistant'));
  const activeMessageCount = activeSession?.messages?.length ?? 0;
  const providerLabel = selectedProviderLabel(providerPayload, selectedProviderId);
  const modelLabel = selectedModelLabel(providerPayload, selectedModelId);
  const recentMessages = activeSession?.messages?.slice(-4) ?? [];
  const displayedMessages = pendingUserMessage
    ? [...(activeSession?.messages ?? []), pendingUserMessage]
    : activeSession?.messages ?? [];
  const displayedSessionId = activeSession?.id ?? selectedSessionId ?? 'pending-session';
  const visibleVoiceTranscriptMessages = recentMessages.filter((message) => !clearedVoiceTranscriptMessageIds[message.id]);
  const latestAssistantMessage = getLatestAssistantMessage(activeSession?.messages ?? []);
  const toolExecutionRows = useMemo(() => createToolExecutionRows(activityEvents), [activityEvents]);
  const enabledToolCount = runtimeConfig.features.toolExecution ? Math.max(toolExecutionRows.length, 3) : 0;
  const liveVoiceActive = callStartedAt !== null;
  const liveVoiceState = liveVoiceActive ? voiceCaptureLabel(voiceCaptureMode) : voiceCaptureMode === 'error' ? 'Error' : 'Idle';
  const liveConnectionLabel = liveVoiceActive ? 'Connected' : 'Disconnected';
  const liveIdentityLabel = liveCallRuntime?.interaction_mode === 'character'
    ? `Character Mode · ${liveCallRuntime.display_name}`
    : 'System Assistant';
  const liveVoiceVisualMode = isAssistantSpeaking ? 'speaking' : liveVoiceActive ? 'listening' : voiceCaptureMode === 'error' ? 'error' : 'idle';
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
    for (const event of sessionEvents) {
      if (!currentEventIds.has(event.id)) {
        eventStore.append(event);
        currentEventIds.add(event.id);
      }
    }
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
    document.querySelectorAll('.assistant-voice-transcript p[data-live-voice-id]').forEach((row) => row.remove());
    setAudioStatus('Voice transcript cleared.');
  }

  function sendVoiceTranscript(): void {
    const content = (liveDraftText || composerContent).trim();
    void submitVoiceTranscriptContent(content, { manual: true });
  }

  function submitComposerMessage(values: ChatbotFormValues): void {
    if (liveVoiceActiveRef.current) {
      void submitVoiceTranscriptContent(values.content, { manual: true });
      return;
    }
    sendMutation.mutate(values);
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
    sendMutation.mutate({ content: trimmed, providerId: selectedProviderId, modelId: selectedModelId });
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
      const response = await fetch(`/api/chat/sessions/${encodeURIComponent(sessionId)}/messages/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content,
          provider_id: providerId,
          model_id: modelId,
          coding_approval_policy: assistantSettings.codingApprovalPolicy,
          live_voice_turn_id: voiceTurnPerformanceRef.current?.turnId,
        }),
      });
      if (!response.ok || !response.body) throw new Error(`Chat stream failed with status ${response.status}.`);
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

  function deleteChatSession(session: ApiChatSession): void {
    const title = sessionTitle(session);
    if (!window.confirm(`Delete "${title}"? This removes the chat history from this device.`)) return;
    deleteSessionMutation.mutate(session.id);
  }

  function handleComposerTextareaKeyDown(event: KeyboardEvent<HTMLTextAreaElement>): void {
    if (event.key !== 'Enter' || event.shiftKey || event.altKey || event.ctrlKey || event.metaKey || event.nativeEvent.isComposing) return;

    event.preventDefault();
    event.currentTarget.form?.requestSubmit();
  }

  function handleComposerPaste(event: ReactClipboardEvent<HTMLTextAreaElement>): void {
    const imageItem = Array.from(event.clipboardData.items).find((item) => item.type.startsWith('image/'));
    if (!imageItem) return;

    event.preventDefault();
    const file = imageItem.getAsFile();
    if (!file) {
      setChatImageError('Unable to read the pasted image.');
      return;
    }
    if (!SUPPORTED_CHAT_IMAGE_TYPES.has(file.type)) {
      setChatImageError('Paste a PNG, JPEG, or WebP image.');
      return;
    }
    if (file.size > MAX_CHAT_IMAGE_BYTES) {
      setChatImageError('That image is larger than 5 MB. Paste a smaller image.');
      return;
    }

    setChatImageError(null);
    void readFileAsDataUrl(file)
      .then((dataUrl) => {
        setPastedChatImage({ dataUrl, mimeType: file.type, size: file.size });
        setPastedChatTextFile(null);
      })
      .catch(() => setChatImageError('Unable to read the pasted image.'));
  }

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

  async function playAssistantResponseAudio(text: string): Promise<void> {
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
        streaming_requested: liveVoiceActive && canUseStreamingTts(),
      });
      setAudioStatus(activeVoiceId ? `Synthesizing ${activeVoiceLabel || activeVoiceId} voice…` : 'Synthesizing response voice…');
      if (liveVoiceActive && canUseStreamingTts()) {
        try {
          stopAssistantResponseAudio(undefined, { cancelPending: false });
          await playStreamingAssistantResponseAudio(spokenText, playbackToken);
          setAudioStatus(activeVoiceId ? 'Streaming cloned response voice.' : 'Streaming response voice.');
          return;
        } catch (streamError) {
          stopStreamingTtsPlayback();
          if (assistantPlaybackTokenRef.current !== playbackToken) return;
          console.info('[Omnix Voice Perf] streaming TTS failed without batch fallback', {
            reason: streamError instanceof Error ? streamError.message : 'Streaming TTS failed.',
          });
          recordVoiceTurnDiagnostic('tts_stream_failed', {
            error_name: streamError instanceof Error ? streamError.name : 'unknown',
          });
          setAudioStatus(streamError instanceof Error ? streamError.message : 'Streaming TTS failed.');
          return;
        }
      }
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

  async function playStreamingAssistantResponseAudio(text: string, playbackToken: number): Promise<void> {
    const liveWindow = window as StreamingTtsWindow;
    const AudioContextCtor = liveWindow.AudioContext ?? liveWindow.webkitAudioContext;
    if (!AudioContextCtor || typeof window.fetch !== 'function' || typeof window.ReadableStream === 'undefined') throw new Error('Streaming TTS requires browser streaming fetch and AudioContext support.');

    const requestId = `tts:${Date.now().toString(36)}:${Math.random().toString(36).slice(2, 8)}`;
    const requestStartedAt = performance.now();
    const speechStyle = currentLiveCallSpeechStyle();
    const resolvedVoiceId = currentLiveCallVoiceId();
    const audioContext = new AudioContextCtor({ latencyHint: 'interactive', sampleRate: STREAMING_TTS_SAMPLE_RATE });
    if (audioContext.state !== 'running') await audioContext.resume();
    const abortController = new AbortController();
    const streamingUrl = '/api/tts/stream/server-sent-events';
    console.info('[Omnix Voice Perf] streaming TTS connect', {
      requestId,
      url: streamingUrl,
      textChars: text.length,
      speaker: resolvedVoiceId || null,
      nonStreamingMode: false,
      parityMode: true,
      chunkSize: 8,
      audioContextState: audioContext.state,
    });
    recordVoiceTurnDiagnostic('tts_stream_connecting', {
      request_id: requestId,
      text_chars: text.length,
      playback_mode: 'sse_audio_context',
    });
    const playback: StreamingTtsPlayback = { audioContext, abortController, sources: [], closed: false };
    streamingTtsRef.current = playback;
    setIsAssistantSpeaking(true);

    let nextStartAt = audioContext.currentTime + STREAMING_TTS_START_DELAY_SECONDS;
    let firstAudioScheduled = false;
    let receivedChunkCount = 0;
    let scheduledAudioSeconds = 0;

    const response = await fetch(streamingUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text,
        speaker: resolvedVoiceId || null,
        language: 'English',
        chunk_size: 8,
        temperature: speechStyle.temperature,
        top_k: speechStyle.top_k,
        top_p: speechStyle.top_p,
        repetition_penalty: speechStyle.repetition_penalty,
        append_silence: false,
        max_new_tokens: 180,
        non_streaming_mode: false,
        parity_mode: true,
        request_id: requestId,
      }),
      signal: abortController.signal,
    });
    if (!response.ok || !response.body) throw new Error(`Streaming TTS SSE failed with status ${response.status}.`);
    console.info('[Omnix Voice Perf] streaming TTS response opened', {
      requestId,
      status: response.status,
      openMs: Math.round(performance.now() - requestStartedAt),
      contentType: response.headers.get('content-type'),
    });
    recordVoiceTurnDiagnostic('tts_stream_opened', {
      request_id: requestId,
      status: response.status,
      open_ms: Math.round(performance.now() - requestStartedAt),
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = '';
    let streamDone = false;

    while (!playback.closed && !streamDone) {
      const { value, done } = await reader.read();
      if (assistantPlaybackTokenRef.current !== playbackToken) return;
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      const events = pending.split(/\n\n/);
      pending = events.pop() ?? '';

      for (const eventText of events) {
        const message = parseStreamingTtsSseEvent(eventText);
        if (!message) continue;
        if (message.type === 'error') {
          console.info('[Omnix Voice Perf] streaming TTS error event', {
            requestId,
            elapsedMs: Math.round(performance.now() - requestStartedAt),
            message: message.message || 'Streaming TTS failed.',
            chunks: receivedChunkCount,
          });
          throw new Error(message.message || 'Streaming TTS failed.');
        }
        if (message.type === 'done') {
          console.info('[Omnix Voice Perf] streaming TTS done event', {
            requestId,
            elapsedMs: Math.round(performance.now() - requestStartedAt),
            chunks: receivedChunkCount,
            scheduledAudioMs: Math.round(scheduledAudioSeconds * 1000),
            partial: Boolean(message.partial),
            message: typeof message.message === 'string' ? message.message : undefined,
          });
          streamDone = true;
          break;
        }
        if (message.type !== 'chunk' || typeof message.audio_b64 !== 'string') continue;

        const pcm = base64ToArrayBuffer(message.audio_b64);
        if (!pcm.byteLength) continue;
        receivedChunkCount += 1;
        const sampleRate = typeof message.sample_rate === 'number' && message.sample_rate > 0 ? message.sample_rate : STREAMING_TTS_SAMPLE_RATE;
        const audioBuffer = pcm16ArrayBufferToAudioBuffer(audioContext, pcm, sampleRate);
        const source = audioContext.createBufferSource();
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
        source.addEventListener('ended', () => {
          playback.sources = playback.sources.filter((entry) => entry !== source);
          if (playback.sources.length === 0 && streamingTtsRef.current === playback) {
            setIsAssistantSpeaking(false);
          }
        }, { once: true });

        if (!firstAudioScheduled) {
          firstAudioScheduled = true;
          if (assistantPlaybackTokenRef.current !== playbackToken) return;
          markVoiceTurnPerformance('ttsFirstChunkReceivedAt');
          markVoiceTurnPerformance('ttsReadyAt');
          markVoiceTurnPerformance('audioFirstScheduledAt');
          const delayMs = Math.max(0, (startAt - audioContext.currentTime) * 1000);
          console.info('[Omnix Voice Perf] streaming TTS first audio scheduled', {
            requestId,
            elapsedMs: Math.round(performance.now() - requestStartedAt),
            chunkBytes: pcm.byteLength,
            sampleRate,
            bufferDurationMs: Math.round(audioBuffer.duration * 1000),
            scheduledLeadMs: Math.round(delayMs),
            audioContextTime: Number(audioContext.currentTime.toFixed(3)),
            startAt: Number(startAt.toFixed(3)),
          });
          recordVoiceTurnDiagnostic('tts_first_audio_scheduled', {
            request_id: requestId,
            first_frame_ms: Math.round(performance.now() - requestStartedAt),
            scheduled_lead_ms: Math.round(delayMs),
            chunk_bytes: pcm.byteLength,
          });
          window.setTimeout(() => {
            if (assistantPlaybackTokenRef.current !== playbackToken || playback.closed) return;
            markVoiceTurnPerformance('audioPlayStartedAt');
            recordVoiceTurnDiagnostic('audio_playback_started', {
              request_id: requestId,
              playback_mode: 'sse_audio_context',
              playback_start_ms: Math.round(performance.now() - requestStartedAt),
            });
            console.info('[Omnix Voice Perf] streaming TTS first audio start', {
              requestId,
              elapsedMs: Math.round(performance.now() - requestStartedAt),
              chunkCountAtStart: receivedChunkCount,
              scheduledAudioMs: Math.round(scheduledAudioSeconds * 1000),
              audioContextTime: Number(audioContext.currentTime.toFixed(3)),
            });
            logVoiceTurnPerformance();
          }, delayMs);
        } else if (underrunSeconds > 0.005) {
          console.info('[Omnix Voice Perf] streaming TTS underrun recovery', {
            requestId,
            chunkIndex: receivedChunkCount - 1,
            underrunMs: Math.round(underrunSeconds * 1000),
            activeSources: playback.sources.length,
          });
        }
      }
    }
    console.info('[Omnix Voice Perf] streaming TTS stream done', {
      requestId,
      elapsedMs: Math.round(performance.now() - requestStartedAt),
      chunks: receivedChunkCount,
      scheduledAudioMs: Math.round(scheduledAudioSeconds * 1000),
      activeSources: playback.sources.length,
      audioContextTime: Number(audioContext.currentTime.toFixed(3)),
    });
    recordVoiceTurnDiagnostic('tts_stream_completed', {
      request_id: requestId,
      elapsed_ms: Math.round(performance.now() - requestStartedAt),
      chunks: receivedChunkCount,
      scheduled_audio_ms: Math.round(scheduledAudioSeconds * 1000),
    });
    await waitForStreamingPlaybackToFinish(playback, () => assistantPlaybackTokenRef.current !== playbackToken);
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
    <WorkspacePanel className={`assistant-chat-page${isChatFullscreen ? ' assistant-chat-page-fullscreen' : ''}`}>
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
                <div className={session.id === selectedSessionId ? 'assistant-sidebar-session-row active' : 'assistant-sidebar-session-row'} key={session.id}>
                <button type="button" onClick={() => { setSelectedSessionId(session.id); setActiveView('chats'); }}>
                  <span aria-hidden="true">▱</span>
                  <span>{sessionTitle(session)}</span>
                  <small>{session.message_count} messages</small>
                </button>
                <button aria-label={`Delete ${sessionTitle(session)}`} className="assistant-sidebar-delete" disabled={deleteSessionMutation.isPending} title="Delete chat session" type="button" onClick={() => deleteChatSession(session)}>x</button>
                </div>
              )) : sessionsLoading ? <p className="assistant-sidebar-empty">Loading chat sessions...</p> : sessionsError ? <p className="assistant-sidebar-empty">Chat sessions failed to load.</p> : <p className="assistant-sidebar-empty">No chat sessions yet.</p>}
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
              )) : sessionsLoading ? <p className="assistant-sidebar-empty">Loading recent chats...</p> : sessionsError ? <p className="assistant-sidebar-empty">Recent chats failed to load.</p> : <p className="assistant-sidebar-empty">Recent chats appear after your first message.</p>}
            </div>
          </section>
        </aside>

        <section className="assistant-chat-main" aria-labelledby="module-title">
          {activeView === 'chats' ? (
            <>
              <header className="assistant-chat-header">
                <div><p className="eyebrow">Current chat</p><h2>{activeSession?.title ?? 'Hey! How are you today?'}</h2></div>
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
                    className="assistant-chat-fullscreen-button"
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
                {displayedMessages.length ? displayedMessages.map((message) => (
                  <article key={message.id} className={`assistant-chat-message ${message.role}`}>
                    {message.role !== 'user' ? <span className="assistant-chat-avatar" aria-hidden="true" /> : null}
                    <div className="assistant-chat-bubble">
                      <header><strong>{message.role === 'assistant' ? 'Omnix Assistant' : message.role === 'user' ? 'You' : message.role}</strong><time dateTime={message.created_at}>{formatMessageTime(message.created_at)}</time></header>
                      {chatImageDataUrl(message.metadata) ? <img className="assistant-chat-message-image" src={chatImageDataUrl(message.metadata) ?? undefined} alt="User-provided attachment" /> : null}
                      {chatTextAttachment(message.metadata) ? <div className="assistant-chat-file-attachment"><strong>Attached file: {chatTextAttachment(message.metadata)?.filename}</strong><small>{chatTextAttachment(message.metadata)?.mimeType}</small></div> : null}
                      <div
                        className={`assistant-message-content${isDeepResearchMessage(message.metadata) ? ' assistant-research-report-host' : ''}`}
                        data-omnix-message-content="true"
                        data-raw-content={message.content}
                        data-message-id={message.id}
                        dangerouslySetInnerHTML={{
                          __html: isDeepResearchMessage(message.metadata)
                            ? renderResearchReportHtml(message.content, message.metadata)
                            : renderMarkdownHtml(message.content, message.metadata),
                        }}
                      />
                      {liveAgentToolProposals(message.metadata).map((proposal) => <LiveAgentToolProposalCard key={proposal.proposal_id} proposal={proposal} sessionId={displayedSessionId} onOpenTools={() => { showAssistantView('tools'); setActiveUtilityPanel('tools'); }} />)}
                      <OmnixRunCard metadata={message.metadata} />
                      {message.role === 'assistant' ? <div className="assistant-message-actions" aria-label="Assistant message actions"><button type="button" className={assistantMessageFeedback[message.id] === 'liked' ? 'active' : undefined} aria-label="Like response" aria-pressed={assistantMessageFeedback[message.id] === 'liked'} onClick={() => toggleAssistantMessageFeedback(message.id, 'liked')}>♡</button><button type="button" className={assistantMessageFeedback[message.id] === 'disliked' ? 'active' : undefined} aria-label="Dislike response" aria-pressed={assistantMessageFeedback[message.id] === 'disliked'} onClick={() => toggleAssistantMessageFeedback(message.id, 'disliked')}>↯</button><button type="button" aria-label="Copy response" onClick={() => void copyAssistantResponse(message)}>□</button><button type="button" aria-label="Play response audio" onClick={() => void playAssistantResponseAudio(message.content)}>▶</button><button type="button" aria-label="More response actions" aria-expanded={openMessageActionMenuId === message.id} onClick={() => setOpenMessageActionMenuId((current) => current === message.id ? null : message.id)}>⋮</button>{openMessageActionMenuId === message.id ? <div className="assistant-message-action-menu" role="menu"><button type="button" role="menuitem" onClick={() => void copyAssistantResponse(message)}>Copy text</button><button type="button" role="menuitem" onClick={() => { setOpenMessageActionMenuId(null); void playAssistantResponseAudio(message.content); }}>Play audio</button><button type="button" role="menuitem" onClick={() => { setOpenMessageActionMenuId(null); applySuggestedPrompt(`Continue from: ${message.content.slice(0, 120)}`); }}>Continue</button></div> : null}</div> : null}
                    </div>
                  </article>
                )) : activeSessionLoading || sessionsLoading ? <div className="platform-empty" role="status">Loading chat messages...</div> : activeSessionError ? <div className="platform-empty" role="status">Chat messages failed to load.</div> : <div className="platform-empty" role="status">No chat messages yet.</div>}
                {quickSearchProgress ? <div className="assistant-quick-search-progress" role="status" aria-live="polite"><span className="assistant-quick-search-icon" aria-hidden="true">◎</span><span>Searching {quickSearchProgress}</span></div> : null}
                <div ref={messagesEndRef} aria-hidden="true" />
              </div>
              <form className="assistant-composer" onSubmit={handleSubmit(submitComposerMessage)}>
                <div className="assistant-suggestion-row" aria-label="Suggested prompts">
                  {suggestedPrompts.map((prompt) => <button key={prompt} type="button" onClick={() => applySuggestedPrompt(prompt)}>{prompt}</button>)}
                  <button type="button" onClick={() => applySuggestedPrompt('Give me more options for this conversation')}>More</button>
                </div>
                <div className="assistant-composer-controls" aria-label="Conversation controls">
                  <label><span>Provider</span><select {...register('providerId')} aria-label="Provider"><option value="">Default provider</option>{chatProviders.map((provider) => <option key={provider.id} value={provider.id}>{provider.label}</option>)}</select></label>
                  <label><span>Model</span><select {...register('modelId')} aria-label="Model"><option value="">Default model</option>{chatModels.map((model) => <option key={model.id} value={model.id}>{model.label}</option>)}</select></label>
                  <button type="button" className="assistant-composer-chip" onClick={() => void playAssistantResponseAudio(latestAssistantMessage?.content ?? '')} disabled={!latestAssistantMessage}><span>Voice</span><strong>{ttsOutputLabel}</strong></button>
                  <button className="assistant-composer-chip" type="button" onClick={() => showAssistantView('settings')}><span>Personality</span><strong>{selectedPersonalityLabel}</strong></button>
                  <button className="assistant-composer-chip" type="button" onClick={() => showAssistantView('settings')}><span>Permissions</span><strong>{codingApprovalOptions.find((option) => option.value === assistantSettings.codingApprovalPolicy)?.label}</strong></button>
                  <button type="button" className="assistant-composer-chip" onClick={() => { showAssistantView('tools'); setActiveUtilityPanel('tools'); }}><span>Tools</span><strong>{runtimeConfig.features.toolExecution ? `${enabledToolCount} Active` : 'Off'}</strong></button>
                  <button type="button" className="assistant-composer-chip" onClick={refreshActivityPanel}><span>Context</span><strong>{activeMessageCount > 0 ? 'Project Brief' : 'Ready'}</strong></button>
                </div>
                {pastedChatImage ? <div className="assistant-chat-image-attachment" role="status"><img src={pastedChatImage.dataUrl} alt="Pasted image preview" /><div><strong>Image attached</strong><small>{pastedChatImage.mimeType.replace('image/', '').toUpperCase()} · {(pastedChatImage.size / 1024).toFixed(0)} KB</small></div><button type="button" aria-label="Remove pasted image" onClick={() => { setPastedChatImage(null); setChatImageError(null); }}>×</button></div> : null}
                {pastedChatTextFile ? <div className="assistant-chat-file-attachment" role="status"><span aria-hidden="true">📄</span><div><strong>{pastedChatTextFile.filename}</strong><small>{pastedChatTextFile.mimeType} · {(pastedChatTextFile.size / 1024).toFixed(0)} KB</small></div><button type="button" aria-label="Remove attached file" onClick={() => { setPastedChatTextFile(null); setChatImageError(null); }}>×</button></div> : null}
                {chatImageError ? <p className="assistant-chat-image-error" role="alert">{chatImageError}</p> : null}
                <label className="assistant-message-input"><span>Message <small className="assistant-chat-paste-hint">Paste an image, or use + to add a photo or text file</small></span><textarea rows={3} aria-label="Message" aria-invalid={Boolean(errors.content)} placeholder="Message Omnix Assistant, or use the microphone…" onKeyDown={handleComposerTextareaKeyDown} onPaste={handleComposerPaste} {...register('content', { validate: (value) => (value.trim() || pastedChatImage || pastedChatTextFile) ? true : 'Enter a message, paste an image, or add a file before sending.' })} /></label>
                <div className="assistant-composer-actions"><button type="button" className="assistant-mic-button" aria-label={liveVoiceActive ? 'Stop voice input' : 'Start voice input'} onClick={() => void (liveVoiceActive ? stopLiveCall() : startLiveCall())}>{liveVoiceActive ? '■' : '◉'}</button><button aria-label={sendMutation.isPending ? 'Generating response' : 'Queue response'} className="assistant-send-button" type="submit" disabled={sendMutation.isPending}>{sendMutation.isPending ? 'Generating response…' : 'Send message'}</button></div>
              </form>
            </>
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
              onStartLiveCall={startLiveCall}
              onUpdateAssistantSettings={updateAssistantSettings}
              onShowTools={() => setActiveUtilityPanel('tools')}
              selectedSessionId={selectedSessionId}
            />
          )}
          <div className="assistant-inline-status" aria-live="polite">
            {errors.content ? <span role="alert">Enter a message or paste an image before sending.</span> : null}
            {sendMutation.isPending ? <span role="status">Contacting the selected chat provider…</span> : null}
            {sendMutation.isError ? <span role="alert">{chatbotSubmitErrorMessage(sendMutation.error)}</span> : null}
            {audioStatus ? <span role="status">{audioStatus}</span> : null}
            {settingsStatus && activeView === 'settings' ? <span role="status">{settingsStatus}</span> : null}
            {sendMutation.data ? <span role="status">{generationComplete ? 'Response ready' : 'Generation job queued'}: {sendMutation.data.job.id}</span> : null}
          </div>
        </section>

        <aside className="assistant-chat-side" aria-label="Live voice, tools, and workspace activity">
          <div className="assistant-side-panel-toggle" aria-label="Assistant utility panel"><button type="button" className={activeUtilityPanel === 'voice' ? 'active' : undefined} onClick={() => setActiveUtilityPanel('voice')}>Live Voice</button><button type="button" className={activeUtilityPanel === 'tools' ? 'active' : undefined} onClick={() => setActiveUtilityPanel('tools')}>Tools</button></div>
          <div className="assistant-live-tools-grid" data-active-panel={activeUtilityPanel}>
            <section className="assistant-live-card" data-live-voice-id={currentLiveCallVoiceId()}>
              <header><div><p className="eyebrow">Live Voice</p><span className={liveCallRuntime?.interaction_mode === 'character' ? 'assistant-live-identity active' : 'assistant-live-identity'}>{liveIdentityLabel}</span></div><div className="assistant-live-header-actions"><strong>{liveConnectionLabel}</strong><button type="button" className="assistant-live-fullscreen-button" aria-label="Enter fullscreen Live Voice" onClick={() => enterLiveChatFullscreen('call-card')}>Fullscreen</button></div></header>
              {liveCallRuntime?.avatar_pack?.renderer === 'live2d'
                ? <Live2DMotionControl rigAssetId={liveCallRuntime.avatar_pack.rig_asset_id} />
                : <div className="assistant-live-state" aria-label="Live voice state"><span>{liveVoiceState}</span><span aria-hidden="true">v</span></div>}
              <div
                key={liveCallRuntime?.avatar_pack?.renderer === 'live2d'
                  ? `${liveCallRuntime.avatar_pack.character_id}:${liveCallRuntime.avatar_pack.version}:${liveCallRuntime.avatar_pack.rig_asset_id}`
                  : 'voice-orb'}
                className="assistant-live-visual-stage"
                aria-label="Live character visual"
              >
                <div className="assistant-voice-orb" data-voice-mode={liveVoiceVisualMode} aria-hidden="true">
                  <div className="assistant-voice-meter assistant-voice-meter-left">{[0, 1, 2, 3, 4, 5, 6].map((index) => <i key={`left-${index}`} style={{ '--bar-index': index } as CSSProperties} />)}</div>
                  <div className="assistant-voice-core"><span className="assistant-voice-pulse" /><span className="assistant-voice-mic" /></div>
                  <div className="assistant-voice-meter assistant-voice-meter-right">{[0, 1, 2, 3, 4, 5, 6].map((index) => <i key={`right-${index}`} style={{ '--bar-index': index } as CSSProperties} />)}</div>
                </div>
              </div>
              {liveCallRuntime?.avatar_pack?.renderer === 'live2d' ? <Live2DZoomControl /> : null}
              <div className="assistant-voice-input-indicator" aria-live="polite">
                <span>Mic input</span>
                <strong className="assistant-voice-input-status">{liveVoiceActive ? 'Listening' : 'Idle'}</strong>
                <i aria-hidden="true"><b /></i>
              </div>
              <time className="assistant-call-timer" dateTime={`PT${Math.floor(callElapsedMs / 1000)}S`}>{liveCallTimerLabel}</time>
              <div className="assistant-voice-controls"><button type="button" onClick={clearVoiceTranscript}>Clear</button><button type="button" className={liveVoiceActive ? 'danger' : undefined} onClick={() => void (liveVoiceActive ? stopLiveCall() : startLiveCall())}>{liveVoiceActive ? 'End Call' : 'Start Call'}</button><button type="button" onClick={sendVoiceTranscript} disabled={sendMutation.isPending || !(liveDraftText || composerContent).trim()}>Send text</button></div>
              <label className="assistant-voice-toggle"><input type="checkbox" checked={autoSpeakResponses} onChange={(event) => setAutoSpeakResponses(event.currentTarget.checked)} /> Auto-speak assistant replies</label>
              <div className="assistant-live-draft" aria-live="polite"><strong>Voice draft</strong><p>{liveDraftText || 'Start Live Voice and speak. Final speech is copied into the message composer.'}</p></div>
              <div className="assistant-voice-transcript"><div className="assistant-voice-transcript-header"><h3>Transcript</h3><button type="button" onClick={clearVoiceTranscript}>Clear</button></div>{visibleVoiceTranscriptMessages.length ? visibleVoiceTranscriptMessages.map((message) => <p key={`transcript-${message.id}`} className={message.role === 'assistant' ? 'assistant' : 'user'}><span><strong>{message.role === 'assistant' ? 'Omnix' : 'You'}</strong><time dateTime={message.created_at}>{formatMessageTime(message.created_at)}</time></span>{message.content}</p>) : <p className="muted">Voice transcript will appear here during live calls.</p>}</div>
              <div className="assistant-audio-devices"><header><h3>Audio Services</h3><button type="button" onClick={() => void startVoiceInput()}>Test input</button></header><div><span>Input</span><strong>{speechInputLabel}</strong><i aria-hidden="true" /></div><div><span>Output</span><strong>{ttsOutputLabel}</strong><i aria-hidden="true" /></div></div>
              <footer className="assistant-voice-status"><span>Voice Status</span><strong>{liveVoiceState}</strong></footer>
            </section>
            <section className="assistant-tool-sidebar-card" aria-labelledby="assistant-tool-execution-heading"><ToolExecutionPanel rows={toolExecutionRows} title="Tool execution" description="Review approvals and monitor tool execution results." /></section>
          </div>
          <div className="assistant-supporting-panels">
            <AssistantWorkspaceDashboardPanel input={{ workspaceName: runtimeConfig.workspaceId, projectName: runtimeConfig.projectId ?? 'Chatbot', sessionTitle: activeSession?.title ?? 'New chat', sessionMode: liveVoiceActive ? 'voice' : 'text', providerLabel, modelLabel, messageCount: activeMessageCount, contextSourceCount: activeMessageCount > 0 ? 1 : 0, memoryCount: Number((activeSession as ApiChatSession & { memory_record_count?: number })?.memory_record_count ?? 0), knowledgeChunkCount: 0, enabledToolCount: runtimeConfig.features.toolExecution ? 1 : 0, qualitySignals: [{ id: 'session', label: 'Conversation session is available', passed: Boolean(activeSession?.id) || !selectedSessionId, severity: 'info' }, { id: 'provider', label: 'At least one chat provider is available', passed: providerQuery.isLoading || chatProviders.length > 0, severity: 'warning' }, { id: 'stt', label: 'Speech-to-text input is available', passed: Boolean(getSpeechRecognitionConstructor() || runtimeConfig.sttServiceUrl), severity: 'warning' }, { id: 'tts', label: 'TTS playback can use service or Voice Studio jobs', passed: true, severity: 'info' }, { id: 'personality', label: `Personality: ${selectedPersonalityLabel}`, passed: true, severity: 'info' }, { id: 'messages', label: 'Conversation projection can render messages', passed: Boolean(activeSession?.messages) || !activeSession, severity: 'info' }, { id: 'event-store', label: 'Workspace events are configured for persistence', passed: runtimeConfig.features.persistedEvents, severity: 'warning' }] }} />
            <AssistantWorkspaceActivityPanel events={activityEvents} />
          </div>
        </aside>
      </div>
      <LiveChatFullscreenShell />
    </WorkspacePanel>
  );
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

function AssistantWorkspaceView({ activeView, assistantSettings, selectedSessionId, chatProviders, enabledToolCount, initialToolConnectionMessage, initialToolId, modelLabel, onResetAssistantSettings, onSessionResolved, onShowTools, onStartLiveCall, onUpdateAssistantSettings, providerLabel, runtimeConfig, settingsStatus, speechInputLabel, toolExecutionRows, ttsOutputLabel, voiceProfiles, voiceProfilesLoading }: { activeView: Exclude<AssistantView, 'chats'>; assistantSettings: AssistantSettings; selectedSessionId: string | null; chatProviders: ReturnType<typeof chatCapableProviders>; enabledToolCount: number; initialToolConnectionMessage: string | null; initialToolId: string | null; modelLabel: string; onResetAssistantSettings: () => void; onSessionResolved: (sessionId: string) => void; onShowTools: () => void; onStartLiveCall: () => void | Promise<void>; onUpdateAssistantSettings: (settings: AssistantSettings) => void; providerLabel: string; runtimeConfig: AssistantWorkspaceRuntimeConfig; settingsStatus: string | null; speechInputLabel: string; toolExecutionRows: number; ttsOutputLabel: string; voiceProfiles: VoiceProfileAsset[]; voiceProfilesLoading: boolean }) {
  if (activeView === 'voice') return <section className="assistant-view-panel" aria-label="Voice Sessions view"><p className="eyebrow">Omnix Assistant</p><h2>Voice Sessions</h2><p>Use browser speech-to-text or the configured STT service to draft messages, then play assistant replies through the TTS service or local Voice Studio jobs.</p><div className="platform-grid"><article><h3>Live call</h3><p>Input: {speechInputLabel}. Output: {ttsOutputLabel}.</p><button type="button" onClick={() => void onStartLiveCall()}>Start Call</button></article><article><h3>Response playback</h3><p>{assistantSettings.voiceId ? `Active cloned voice: ${voiceLabelForId(assistantSettings.voiceId, voiceProfiles) || assistantSettings.voiceId}` : runtimeConfig.ttsVoice ? `Configured voice: ${runtimeConfig.ttsVoice}` : 'Chatbot will synthesize assistant replies with the default configured voice.'}</p></article></div></section>;
  if (activeView === 'tools') return <AssistantToolSettingsPanel enabledToolCount={enabledToolCount} initialConnectionMessage={initialToolConnectionMessage} initialToolId={initialToolId} toolExecutionRows={toolExecutionRows} onShowExecutionPanel={onShowTools} />;
  if (activeView === 'characters') return <section className="assistant-view-panel" aria-label="Characters view"><header><p className="eyebrow">Omnix Assistant</p><h2>Characters</h2><p>Create, version, and govern character identities independently from their linked voices and memory.</p></header><CharacterManagementPanel sessionId={selectedSessionId} onSessionResolved={onSessionResolved} /></section>;
  if (activeView === 'memory') return <MemoryManagementPanel sessionId={selectedSessionId} />;
  return <section className="assistant-view-panel" aria-label="Settings view"><p className="eyebrow">Omnix Assistant</p><h2>Settings</h2><p>Select the assistant personality and cloned voice used by Chatbot sessions and response audio.</p><div className="assistant-settings-list"><div><label htmlFor="assistant-personality">Personality</label><select id="assistant-personality" aria-label="Personality" value={assistantSettings.personalityId} onChange={(event) => onUpdateAssistantSettings({ ...assistantSettings, personalityId: event.currentTarget.value as PersonalityId })}>{personalityOptions.map((personality) => <option key={personality.id} value={personality.id}>{personality.label}</option>)}</select></div><div><label htmlFor="coding-approval-policy">Coding agent permissions</label><select id="coding-approval-policy" aria-label="Coding agent permissions" value={assistantSettings.codingApprovalPolicy} onChange={(event) => onUpdateAssistantSettings({ ...assistantSettings, codingApprovalPolicy: event.currentTarget.value as CodingApprovalPolicy })}>{codingApprovalOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select><small>{codingApprovalOptions.find((option) => option.value === assistantSettings.codingApprovalPolicy)?.description}</small></div><div><label htmlFor="assistant-custom-personality">Custom personality</label><textarea id="assistant-custom-personality" aria-label="Custom personality" rows={4} value={assistantSettings.customPersonality} disabled={assistantSettings.personalityId !== 'custom'} placeholder="Describe how the assistant should behave, speak, and prioritize responses." onChange={(event) => onUpdateAssistantSettings({ ...assistantSettings, customPersonality: event.currentTarget.value })} /></div><div><label htmlFor="assistant-voice">Cloned voice</label><select id="assistant-voice" aria-label="Cloned voice" value={assistantSettings.voiceId} onChange={(event) => onUpdateAssistantSettings({ ...assistantSettings, voiceId: event.currentTarget.value })}><option value="">{runtimeConfig.ttsVoice ? `Default configured voice (${runtimeConfig.ttsVoice})` : 'Default voice'}</option>{voiceProfiles.map((asset) => <option key={asset.id} value={voiceProfileId(asset)}>{voiceProfileLabel(asset)}</option>)}</select></div><div><label htmlFor="assistant-live-sensitivity">Live mic sensitivity</label><input id="assistant-live-sensitivity" aria-label="Live mic sensitivity" type="range" min="1" max="100" step="1" value={assistantSettings.liveVoiceSensitivity} onChange={(event) => onUpdateAssistantSettings({ ...assistantSettings, liveVoiceSensitivity: clampLiveVoiceSensitivity(event.currentTarget.value) })} /><strong>{assistantSettings.liveVoiceSensitivity}%</strong></div><div><span>Voice profiles</span><strong>{voiceProfilesLoading ? 'Loading cloned voices…' : voiceProfiles.length ? `${voiceProfiles.length} cloned voices available` : 'No cloned voices indexed'}</strong></div><div><span>TTS output</span><strong>{ttsOutputLabel}</strong></div><div><span>Provider</span><strong>{providerLabel}</strong></div><div><span>Model</span><strong>{modelLabel}</strong></div><div><span>Speech input</span><strong>{speechInputLabel}</strong></div><div><span>Event storage</span><strong>{runtimeConfig.features.persistedEvents ? runtimeConfig.eventStorageKey : 'In-memory only'}</strong></div><div><span>Live assistant</span><strong>{runtimeConfig.features.liveAssistant ? 'Enabled' : 'Disabled'}</strong></div><div><span>Tool execution</span><strong>{runtimeConfig.features.toolExecution ? 'Enabled' : 'Disabled'}</strong></div><div><span>Available chat providers</span><strong>{chatProviders.length}</strong></div></div><div className="assistant-settings-actions"><button type="button" onClick={onResetAssistantSettings}>Reset assistant settings</button></div>{settingsStatus ? <p className="assistant-view-note" role="status">{settingsStatus}</p> : null}<p className="assistant-view-note">Personality is sent as the system prompt when a new chat session is created. Coding agent permissions apply to new coding Agent runs. Existing runs keep their original policy.</p></section>;
}

function chatCapableProviders(payload: ProviderFacadePayload | undefined) { return payload?.providers.filter((provider) => provider.capabilities.includes('chat')) ?? []; }
function chatCapableModels(payload: ProviderFacadePayload | undefined, providerId: string) { return payload?.models.filter((model) => { const providerMatches = providerId ? model.provider_id === providerId : true; return providerMatches && model.capabilities.includes('chat'); }) ?? []; }
function selectedProviderLabel(payload: ProviderFacadePayload | undefined, providerId: string) { if (!providerId) return 'Default provider'; return payload?.providers.find((provider) => provider.id === providerId)?.label ?? providerId; }
function selectedModelLabel(payload: ProviderFacadePayload | undefined, modelId: string) { if (!modelId) return 'Default model'; return payload?.models.find((model) => model.id === modelId)?.label ?? modelId; }
function chatbotSubmitErrorMessage(error: unknown): string { if (error instanceof ApiError) return error.message; if (error instanceof Error) return error.message; return 'Chat request failed'; }
function formatMessageTime(value: string): string { if (value.includes('T')) return value.slice(11, 16); return value; }
function formatCallDuration(valueMs: number): string { const totalSeconds = Math.max(0, Math.floor(valueMs / 1000)); const hours = Math.floor(totalSeconds / 3600); const minutes = Math.floor((totalSeconds % 3600) / 60); const seconds = totalSeconds % 60; return [hours, minutes, seconds].map((value) => value.toString().padStart(2, '0')).join(':'); }
function createChatbotWorkspaceEventStore(config: AssistantWorkspaceRuntimeConfig): AssistantWorkspaceEventStore { const storage = getAssistantWorkspaceEventStorage(); if (config.features.persistedEvents && storage) return createStoredAssistantWorkspaceEventStore(storage, config.eventStorageKey); return createInMemoryAssistantWorkspaceEventStore(); }
function appendWorkspaceEventIfMissing(eventStore: AssistantWorkspaceEventStore, event: AssistantWorkspaceEvent, filter: AssistantWorkspaceEventStoreFilter): void { const currentEventIds = new Set(eventStore.list(filter).map((currentEvent) => currentEvent.id)); if (!currentEventIds.has(event.id)) eventStore.append(event); }
function getAssistantWorkspaceEventStorage(): AssistantWorkspaceEventStorage | undefined { try { return typeof window === 'undefined' ? undefined : window.localStorage; } catch { return undefined; } }
function createWorkspaceEventFilter(config: AssistantWorkspaceRuntimeConfig, sessionId?: string): AssistantWorkspaceEventStoreFilter { return { workspaceId: config.workspaceId, projectId: config.projectId, sessionId }; }
function readAssistantToolReturn(): { message: string | null; toolId: string | null } { try { if (typeof window === 'undefined') return { message: null, toolId: null }; const params = new URLSearchParams(window.location.search); const toolId = params.get('assistant_tool'); return { message: params.get('assistant_tool_message'), toolId: toolId && /^[a-z][a-z0-9_-]*$/.test(toolId) ? toolId : null }; } catch { return { message: null, toolId: null }; } }
function getLatestAssistantMessage(messages: ChatMessage[]): ChatMessage | undefined { return [...messages].reverse().find((message) => message.role === 'assistant' && message.content.trim()); }
function isScrolledNearBottom(element: HTMLElement): boolean { return element.scrollHeight - element.scrollTop - element.clientHeight < 160; }
function getSynthesizedAudioSource(response: TtsSynthesisResponse): string { if (response.audioUrl) return response.audioUrl; if (response.audioBase64) return `data:${response.mimeType ?? 'audio/wav'};base64,${response.audioBase64}`; throw new Error('TTS service did not return playable audio.'); }
function isPinnedSession(session: ApiChatSession): boolean { const metadata = 'metadata' in session ? (session as { metadata?: Record<string, unknown> }).metadata : undefined; return metadata?.pinned === true || metadata?.starred === true; }
function sessionTitle(session: ApiChatSession): string { return session.title?.trim() || 'Untitled chat'; }
function formatSessionTime(session: ApiChatSession): string { const timestamp = session.updated_at || session.created_at; if (!timestamp) return 'Recent'; return timestamp.includes('T') ? formatMessageTime(timestamp) : timestamp; }
function mergeTranscript(current: string, next: string): string { return [current.trim(), next.trim()].filter(Boolean).join(' ').replace(/\s+/g, ' ').trim(); }
function shouldFlushStreamedSpeechBuffer(value: string): boolean { const text = value.trim(); if (text.length < STREAMED_TTS_MIN_PHRASE_CHARS) return false; return /[.!?]["')\]]?$/.test(text) || text.length >= STREAMED_TTS_MIN_PHRASE_CHARS * 2; }
function elapsedMs(start: number | undefined, end: number | undefined): number | null { return start === undefined || end === undefined ? null : Math.round(end - start); }
function voiceCaptureLabel(mode: VoiceCaptureMode): string { if (mode === 'recording') return 'Recording'; if (mode === 'transcribing') return 'Transcribing'; if (mode === 'error') return 'Error'; if (mode === 'listening') return 'Listening'; return 'Ready'; }
function getSpeechRecognitionConstructor(): BrowserSpeechRecognitionConstructor | undefined { if (typeof window === 'undefined') return undefined; const speechWindow = window as SpeechRecognitionWindow; return speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition; }
function canUseStreamingTts(): boolean { if (typeof window === 'undefined') return false; const liveWindow = window as StreamingTtsWindow; return Boolean((liveWindow.AudioContext || liveWindow.webkitAudioContext) && typeof window.fetch === 'function' && typeof window.ReadableStream !== 'undefined'); }
function canUseDecodedAudioPlayback(): boolean { if (typeof window === 'undefined') return false; const liveWindow = window as StreamingTtsWindow; return Boolean(liveWindow.AudioContext || liveWindow.webkitAudioContext); }
function parseStreamingTtsSseEvent(value: string): { type?: string; message?: string; audio_b64?: string; sample_rate?: number; partial?: boolean } | null { const line = value.split(/\r?\n/).find((entry) => entry.startsWith('data:')); if (!line) return null; try { return JSON.parse(line.slice(5).trim()) as { type?: string; message?: string; audio_b64?: string; sample_rate?: number; partial?: boolean }; } catch { return null; } }
function parseChatStreamEvent(value: string): ChatStreamEvent | null { const line = value.split(/\r?\n/).find((entry) => entry.startsWith('data:')); if (!line) return null; try { return JSON.parse(line.slice(5).trim()) as ChatStreamEvent; } catch { return null; } }
function makePlayableAudioSource(source: string): { url: string; revoke?: () => void } { if (!source.startsWith('data:audio/') || typeof URL === 'undefined' || typeof URL.createObjectURL !== 'function') return { url: source }; const blob = dataUrlToBlob(source); const url = URL.createObjectURL(blob); return { url, revoke: () => URL.revokeObjectURL(url) }; }
function dataUrlToBlob(source: string): Blob { const [header, encoded = ''] = source.split(',', 2); const mime = /^data:([^;,]+)/.exec(header)?.[1] || 'audio/wav'; const binary = window.atob(encoded); const bytes = new Uint8Array(binary.length); for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index); return new Blob([bytes], { type: mime }); }
async function audioSourceToArrayBuffer(source: string): Promise<ArrayBuffer> { if (source.startsWith('data:')) return dataUrlToArrayBuffer(source); const response = await fetch(source); if (!response.ok) throw new Error(`Audio fetch failed with status ${response.status}.`); return response.arrayBuffer(); }
function dataUrlToArrayBuffer(source: string): ArrayBuffer { const [, encoded = ''] = source.split(',', 2); return base64ToArrayBuffer(encoded); }
function waitForAudioElementPlaying(audio: HTMLAudioElement): Promise<void> { return new Promise((resolve, reject) => { if (typeof audio.addEventListener !== 'function') { resolve(); return; } if (!audio.paused && audio.readyState >= 3) { resolve(); return; } let timeoutId: ReturnType<typeof setTimeout> | null = null; const cleanup = () => { audio.removeEventListener('playing', onPlaying); audio.removeEventListener('error', onError); if (timeoutId !== null) clearTimeout(timeoutId); }; const onPlaying = () => { cleanup(); resolve(); }; const onError = () => { cleanup(); reject(new Error(audio.error?.message || 'Audio playback failed before it started.')); }; audio.addEventListener('playing', onPlaying, { once: true }); audio.addEventListener('error', onError, { once: true }); timeoutId = setTimeout(() => { cleanup(); reject(new Error('Audio element did not start playing within 3s.')); }, 3000); }); }
function waitForAudioElementToFinish(audio: HTMLAudioElement): Promise<void> { return new Promise((resolve) => { if (audio.ended || audio.paused || typeof audio.addEventListener !== 'function') { resolve(); return; } const done = () => resolve(); audio.addEventListener('ended', done, { once: true }); audio.addEventListener('pause', done, { once: true }); audio.addEventListener('error', done, { once: true }); }); }
function waitForStreamingPlaybackToFinish(playback: StreamingTtsPlayback, isCancelled: () => boolean): Promise<void> { return new Promise((resolve) => { const tick = () => { if (playback.closed || playback.sources.length === 0 || isCancelled()) { resolve(); return; } window.setTimeout(tick, 25); }; tick(); }); }
function base64ToArrayBuffer(value: string): ArrayBuffer { const binary = window.atob(value); const bytes = new Uint8Array(binary.length); for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index); return bytes.buffer; }
function pcm16ArrayBufferToAudioBuffer(audioContext: AudioContext, pcm: ArrayBuffer, sampleRate: number): AudioBuffer { const input = new Int16Array(pcm); const buffer = audioContext.createBuffer(1, input.length, sampleRate); const channel = buffer.getChannelData(0); for (let index = 0; index < input.length; index += 1) channel[index] = input[index] / 32768; return buffer; }
function getVoiceJobAudioSource(job: JobRecord): string | null { const refs = Array.isArray(job.output_refs) ? job.output_refs : []; for (const ref of refs) { const output = ref as VoiceJobOutputRef; if (isFallbackVoiceOutput(output)) continue; if (typeof output.data_url === 'string' && output.data_url.startsWith('data:audio/')) return output.data_url; if (typeof output.audio_url === 'string' && output.audio_url.trim()) return output.audio_url; } return null; }
function isFallbackVoiceOutput(ref: VoiceJobOutputRef): boolean { if (ref.provider_fallback === true || ref.provider_success === false) return true; const segments = Array.isArray(ref.segments) ? ref.segments : []; return segments.some((segment) => { const row = segment as { provider_fallback?: unknown; provider_success?: unknown } | null; return row?.provider_fallback === true || row?.provider_success === false; }); }
function voiceJobErrorMessage(job: JobRecord): string { if (job.status !== 'failed') return ''; const error = job.error as { message?: unknown } | null | undefined; return typeof error?.message === 'string' ? error.message : 'Voice Studio TTS job failed.'; }
function getVoiceProfileAssets(payload: AssetListResponse | undefined): VoiceProfileAsset[] { return payload?.assets.filter((asset) => asset.type === 'voice_profile') ?? []; }
function asRecord(value: unknown): Record<string, unknown> { return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}; }
function voiceProfileId(asset: VoiceProfileAsset): string { const metadata = asRecord(asset.metadata); return stringMetadata(metadata.voice_id) || stringMetadata(metadata.profile_id) || stringMetadata(metadata.id) || asset.id; }
function voiceProfileLabel(asset: VoiceProfileAsset): string { const metadata = asRecord(asset.metadata); return stringMetadata(metadata.profile_name) || stringMetadata(metadata.name) || stringMetadata(metadata.voice_name) || asset.storage_path.split(/[\\/]/).pop() || asset.id; }
function voiceLabelForId(voiceId: string, voiceProfiles: VoiceProfileAsset[]): string { if (!voiceId) return ''; const profile = voiceProfiles.find((asset) => voiceProfileId(asset) === voiceId || asset.id === voiceId); return profile ? voiceProfileLabel(profile) : voiceId; }
function stringMetadata(value: unknown): string { return typeof value === 'string' ? value.trim() : ''; }
function readFileAsDataUrl(file: File): Promise<string> { return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => typeof reader.result === 'string' ? resolve(reader.result) : reject(new Error('Image data was not text.')); reader.onerror = () => reject(reader.error ?? new Error('Image read failed.')); reader.readAsDataURL(file); }); }
function attachmentDefaultMessage(image: PastedChatImage | null, textFile: PastedChatTextFile | null): string { return image ? DEFAULT_IMAGE_MESSAGE : textFile ? DEFAULT_TEXT_FILE_MESSAGE : ''; }
function chatImageDataUrl(metadata?: Record<string, unknown>): string | null { const value = metadata?.image_data_url; if (typeof value !== 'string') return null; return [...SUPPORTED_CHAT_IMAGE_TYPES].some((mimeType) => value.startsWith(`data:${mimeType};base64,`)) ? value : null; }
function chatTextAttachment(metadata?: Record<string, unknown>): { filename: string; mimeType: string } | null { const value = metadata?.text_attachment; if (!value || typeof value !== 'object' || Array.isArray(value)) return null; const attachment = value as Record<string, unknown>; const filename = typeof attachment.filename === 'string' ? attachment.filename.trim() : ''; const mimeType = typeof attachment.mime_type === 'string' ? attachment.mime_type.trim() : ''; const text = typeof attachment.text === 'string' ? attachment.text : ''; return filename && mimeType && text ? { filename, mimeType } : null; }
async function copyTextToClipboard(text: string): Promise<boolean> { try { if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) { await navigator.clipboard.writeText(text); return true; } if (typeof document === 'undefined') return false; const textarea = document.createElement('textarea'); textarea.value = text; textarea.setAttribute('readonly', 'true'); textarea.style.position = 'fixed'; textarea.style.left = '-9999px'; document.body.appendChild(textarea); textarea.select(); const copied = document.execCommand('copy'); textarea.remove(); return copied; } catch { return false; } }
function defaultAssistantSettings(config: AssistantWorkspaceRuntimeConfig): AssistantSettings { return { voiceId: config.ttsVoice ?? '', personalityId: 'default', customPersonality: '', liveVoiceSensitivity: DEFAULT_LIVE_VOICE_SENSITIVITY, codingApprovalPolicy: DEFAULT_CODING_APPROVAL_POLICY }; }
function loadAssistantSettings(config: AssistantWorkspaceRuntimeConfig): AssistantSettings { const fallback = defaultAssistantSettings(config); try { if (typeof window === 'undefined') return fallback; const raw = window.localStorage.getItem(ASSISTANT_SETTINGS_STORAGE_KEY); if (!raw) return fallback; const parsed = JSON.parse(raw) as Partial<AssistantSettings>; return { voiceId: typeof parsed.voiceId === 'string' ? parsed.voiceId : fallback.voiceId, personalityId: isPersonalityId(parsed.personalityId) ? parsed.personalityId : fallback.personalityId, customPersonality: typeof parsed.customPersonality === 'string' ? parsed.customPersonality : fallback.customPersonality, liveVoiceSensitivity: clampLiveVoiceSensitivity(parsed.liveVoiceSensitivity), codingApprovalPolicy: isCodingApprovalPolicy(parsed.codingApprovalPolicy) ? parsed.codingApprovalPolicy : fallback.codingApprovalPolicy }; } catch { return fallback; } }
function saveAssistantSettings(settings: AssistantSettings): void { try { if (typeof window !== 'undefined') window.localStorage.setItem(ASSISTANT_SETTINGS_STORAGE_KEY, JSON.stringify(settings)); } catch { /* ignore local storage failures */ } }
function loadSelectedSessionId(): string | null { try { if (typeof window === 'undefined') return null; const stored = window.localStorage.getItem(ASSISTANT_SESSION_STORAGE_KEY)?.trim(); return stored || null; } catch { return null; } }
function clampLiveVoiceSensitivity(value: unknown): number { const parsed = typeof value === 'number' ? value : Number(value); if (!Number.isFinite(parsed)) return DEFAULT_LIVE_VOICE_SENSITIVITY; return Math.min(100, Math.max(1, Math.round(parsed))); }
function isCodingApprovalPolicy(value: unknown): value is CodingApprovalPolicy { return value === 'always_ask' || value === 'ask_sensitive' || value === 'allow_automatic'; }
function isPersonalityId(value: unknown): value is PersonalityId { return typeof value === 'string' && personalityOptions.some((option) => option.id === value); }
function personalityLabel(value: PersonalityId): string { return personalityOptions.find((option) => option.id === value)?.label ?? 'Omnix Default'; }
function createPersonalityPrompt(settings: AssistantSettings): string | undefined { if (settings.personalityId === 'custom') return settings.customPersonality.trim() || undefined; return personalityOptions.find((option) => option.id === settings.personalityId)?.prompt; }
