import type { QueryClient } from '@tanstack/react-query';
import type { OmnixModuleId } from './modules';

/**
 * Browser-side runtime initialization is deliberately scoped to the active
 * workspace.  Importing a feature is not free: many of the legacy workspaces
 * install fetch/event observers and start background reconciliation. Keeping
 * those imports behind this boundary prevents Chat from booting trading,
 * voice, audiobook, and desktop-companion runtimes at the same time.
 */
const runtimePromises = new Map<OmnixModuleId, Promise<void>>();

export function initializeViewRuntime(moduleId: OmnixModuleId, queryClient: QueryClient): Promise<void> {
  const existing = runtimePromises.get(moduleId);
  if (existing) return existing;

  const runtime = loadViewRuntime(moduleId, queryClient).catch((error: unknown) => {
    runtimePromises.delete(moduleId);
    console.error(`[Omnix] ${moduleId} workspace runtime failed to initialize`, error);
  });
  runtimePromises.set(moduleId, runtime);
  return runtime;
}

async function loadViewRuntime(moduleId: OmnixModuleId, queryClient: QueryClient): Promise<void> {
  switch (moduleId) {
    case 'chatbot':
      await initializeChatRuntime(queryClient);
      return;
    case 'rpg':
      (await import('../features/rpg/rpgTurnUiStore')).installRpgTurnUiFetchInterceptor();
      return;
    case 'podcast':
      await import('../features/podcast/podcastSessionGuard');
      return;
    case 'voice':
      await import('../features/voice/voiceJobListGuard');
      (await import('../features/voice/voiceLibraryAssetFallback')).installVoiceLibraryAssetFallback();
      (await import('../features/voice/voiceLibraryFetchDiagnostics')).installVoiceLibraryFetchDiagnostics();
      return;
    case 'storyteller':
      await import('../features/storyteller/story-audio-enhancer');
      await import('../features/storyteller/story-extra-mount');
      return;
    default:
      return;
  }
}

async function initializeChatRuntime(queryClient: QueryClient): Promise<void> {
  // These controllers are the chat/live-chat runtime. They used to be
  // installed from main.tsx for every route, which caused unrelated API work
  // to start while the user was opening the chat history sidebar.
  await import('../features/chatbot/sessionTools');
  (await import('../features/chatbot/researchProgressController')).installResearchProgressController();
  (await import('../features/voice/voiceLibraryAssetFallback')).installVoiceLibraryAssetFallback();
  (await import('../features/voice/voiceLibraryFetchDiagnostics')).installVoiceLibraryFetchDiagnostics();

  (await import('../features/chatbot/chat-sidebar-manager')).initializeChatSidebarManager();
  (await import('../features/chatbot/live-chat-workspace')).initializeLiveChatWorkspace(queryClient);
  (await import('../features/chatbot/voice-session-evaluation-workspace')).initializeVoiceSessionEvaluationWorkspace();

  const runtimeStore = await import('../features/assistant-workspace/live-conversation-store-bridge');
  runtimeStore.initializeLiveConversationStoreBridge();
  (await import('../features/assistant-workspace/live-session-coordinator')).initializeLiveSessionCoordinator();
  await import('../features/assistant-workspace/live-voice-transcript-autoscroll');
  (await import('../features/assistant-workspace/live-stt-authority-controller')).initializeLiveSttAuthorityController();
  const voiceTurns = await import('../features/assistant-workspace/live-voice-turn-coordinator');
  voiceTurns.initializeLiveVoiceTranscriptReconciliation();
  voiceTurns.initializeLiveVoiceTurnCoordinator();
  (await import('../features/assistant-workspace/live-speculation-diagnostics-bridge')).initializeLiveSpeculationDiagnosticsBridge();
  (await import('../features/assistant-workspace/live-speculation-eligibility-diagnostics')).initializeLiveSpeculationEligibilityDiagnostics();
  (await import('../features/assistant-workspace/live-speculation-direct-gateway-transport')).initializeLiveSpeculationDirectGatewayTransport();
  (await import('../features/assistant-workspace/live-speculation-handshake-transport')).initializeLiveSpeculationHandshakeTransport();
  (await import('../features/assistant-workspace/live-speculation-early-trigger')).initializeLiveSpeculationEarlyTrigger();
  (await import('../features/assistant-workspace/live-speculation-runtime')).initializeLiveSpeculationRuntime();
  (await import('../features/assistant-workspace/live-call-prewarm-controller')).initializeLiveCallPrewarmController();
  (await import('../features/assistant-workspace/live-runtime-provenance')).emitLiveRuntimeProvenance();
  (await import('../features/assistant-workspace/live-voice-controller')).initializeLiveVoiceController();
  (await import('../features/assistant-workspace/live-output-coordinator')).initializeLiveOutputCoordinator();
  (await import('../features/assistant-workspace/live-presence-policy-controller')).initializeLivePresencePolicyController();
  (await import('../features/assistant-workspace/live-voice-duplex-gate')).initializeLiveVoiceDuplexGate();
  (await import('../features/assistant-workspace/live-voice-audio-duck-bridge')).initializeLiveVoiceAudioDuckBridge();
  (await import('../features/assistant-workspace/live-voice-cue-asset-bridge')).initializeLiveVoiceCueAssetBridge();
  (await import('../features/assistant-workspace/live-voice-cue-pack-loader')).initializeLiveVoiceCuePackLoader();
  (await import('../features/assistant-workspace/live-tts-capability-controller')).initializeLiveTtsCapabilityController();
  (await import('../features/assistant-workspace/live-tts-adaptive-buffer-controller')).initializeLiveTtsAdaptiveBufferController();
  (await import('../features/assistant-workspace/live-voice-unified-audio-controller')).initializeLiveVoiceUnifiedAudioController();
  (await import('../features/assistant-workspace/live-voice-pending-output-interrupt')).initializeLiveVoicePendingOutputInterrupt();
  (await import('../features/assistant-workspace/live-avatar-presence')).initializeLiveAvatarPresenceController();
  (await import('../features/assistant-workspace/live-conversation-initiative-controller')).initializeLiveConversationInitiativeController();
  (await import('../features/assistant-workspace/live-conversation-repair-controller')).initializeLiveConversationRepairController();
  (await import('../features/assistant-workspace/live-conversation-evaluation-controller')).initializeLiveConversationEvaluationController();
  (await import('../features/assistant-workspace/live-conversation-durable-evaluation-controller')).initializeLiveConversationDurableEvaluationController();

  // These controls are intentionally deferred until the chat route is active.
  await import('../features/assistant-workspace/assistant-context-controller');
  const [audio, streamAudio, desktop] = await Promise.all([
    import('../features/assistant-workspace/chat-message-audio-controller-v2'),
    import('../features/assistant-workspace/chat-message-stream-audio-controller'),
    import('../features/assistant-workspace/desktop-companion-controls'),
  ]);
  audio.initializeChatMessageAudioControllerV2();
  streamAudio.initializeChatMessageStreamAudioController();
  desktop.initializeDesktopCompanionControls();

  (await import('../features/assistant-workspace/live-voice-form-sync'));
  (await import('../features/assistant-workspace/desktop-companion-expression-enricher')).initializeDesktopCompanionExpressionEnricher();
  (await import('../features/assistant-workspace/desktop-companion-delivery')).initializeDesktopCompanionDeliveryController();
  const [watch, textSurface, evaluation, operationalGuard] = await Promise.all([
    import('../features/assistant-workspace/desktop-companion-watch-controller'),
    import('../features/assistant-workspace/desktop-companion-text-surface'),
    import('../features/assistant-workspace/desktop-companion-shadow-evaluation-controller'),
    import('../features/assistant-workspace/desktop-companion-operational-guard'),
  ]);
  textSurface.initializeDesktopCompanionTextSurface();
  evaluation.initializeDesktopCompanionShadowEvaluationController();
  operationalGuard.initializeDesktopCompanionOperationalGuard();
  watch.initializeDesktopCompanionWatchController();
  await import('../features/assistant-workspace/research-release-controller');
}
