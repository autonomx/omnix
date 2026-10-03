/* eslint-disable omnix/no-app-direct-feature-dynamic-import -- baseline WP-9.x */
import type { QueryClient } from '@tanstack/react-query';
import { DisposableStore, type Disposable } from './moduleRuntime';
import type { OmnixModuleId } from './modules';

/**
 * Browser-side runtime of the active workspace (WP-9.1).
 *
 * Entering a workspace activates its runtime; leaving it disposes it. Every
 * initializer returns a cleanup that goes into the workspace's store, so
 * listeners, observers, timers, fetch middleware and client patches do not
 * outlive the route. Feature code is imported here, lazily, so Chat does not
 * boot trading, voice or audiobook runtimes (and vice versa).
 */
export interface ModuleRuntimeContext {
  queryClient: QueryClient;
}

const activeStores = new Map<OmnixModuleId, DisposableStore>();

export interface ActiveViewRuntime extends Disposable {
  /** Settles when activation finished (or failed and was logged). */
  readonly ready: Promise<void>;
}

export function activateViewRuntime(moduleId: OmnixModuleId, context: ModuleRuntimeContext): ActiveViewRuntime {
  const store = new DisposableStore();
  activeStores.get(moduleId)?.dispose();
  activeStores.set(moduleId, store);
  const ready = loadViewRuntime(moduleId, context, store).catch((error: unknown) => {
    console.error(`[Omnix] ${moduleId} workspace runtime failed to initialize`, error);
  });
  return {
    ready,
    dispose: () => {
      store.dispose();
      if (activeStores.get(moduleId) === store) activeStores.delete(moduleId);
    },
  };
}

/** Workspaces whose runtime is active (tests and diagnostics). */
export function activeViewRuntimes(): OmnixModuleId[] {
  return [...activeStores.keys()];
}

async function loadViewRuntime(moduleId: OmnixModuleId, context: ModuleRuntimeContext, store: DisposableStore): Promise<void> {
  switch (moduleId) {
    case 'chatbot':
      await activateChatRuntime(context, store);
      return;
    case 'rpg':
      store.add((await import('../features/rpg/rpgTurnUiStore')).installRpgTurnUiFetchInterceptor());
      return;
    case 'voice':
      store.add((await import('../features/voice/voiceLibraryAssetFallback')).installVoiceLibraryAssetFallback());
      store.add((await import('../features/voice/voiceLibraryFetchDiagnostics')).installVoiceLibraryFetchDiagnostics());
      return;
    default:
      return;
  }
}

async function activateChatRuntime({ queryClient }: ModuleRuntimeContext, store: DisposableStore): Promise<void> {
  // Navigating away can dispose the store while these imports load; a step
  // that completes afterwards is undone at once by store.add.
  const add = (cleanup: Parameters<DisposableStore['add']>[0]) => store.add(cleanup);

  add((await import('../features/chatbot/chat-response-metrics-controller')).initializeChatResponseMetricsController());
  add((await import('../features/chatbot/sessionTools')).installSessionTools());
  add((await import('../features/chatbot/researchProgressController')).installResearchProgressController());
  add((await import('../features/voice/voiceLibraryAssetFallback')).installVoiceLibraryAssetFallback());
  add((await import('../features/voice/voiceLibraryFetchDiagnostics')).installVoiceLibraryFetchDiagnostics());
  add((await import('../features/chatbot/newChatCoordinator')).initializeNewChatCoordinator());
  add((await import('../features/chatbot/liveCharacterAvatarBridge')).installLiveCharacterAvatarBridge());
  add((await import('../features/chatbot/liveCharacterVisemeBridge')).installLiveCharacterVisemeBridge());
  add((await import('../features/chatbot/live2dCharacterRenderer')).installLive2DCharacterRenderer());

  add((await import('../features/chatbot/chat-sidebar-manager')).initializeChatSidebarManager());
  add((await import('../features/chatbot/live-chat-workspace')).initializeLiveChatWorkspace(queryClient));

  add((await import('../features/assistant-workspace/live-conversation-store-bridge')).initializeLiveConversationStoreBridge());
  add((await import('../features/assistant-workspace/live-session-coordinator')).initializeLiveSessionCoordinator());
  add((await import('../features/assistant-workspace/live-stt-authority-controller')).initializeLiveSttAuthorityController());
  const voiceTurns = await import('../features/assistant-workspace/live-voice-turn-coordinator');
  add(voiceTurns.initializeLiveVoiceTranscriptReconciliation());
  add(voiceTurns.initializeLiveVoiceTurnCoordinator());
  add((await import('../features/assistant-workspace/live-voice-release-observer')).initializeLiveVoiceReleaseObserver());
  add((await import('../features/assistant-workspace/live-voice-echo-suppression')).initializePlaybackEchoSuppression());
  add((await import('../features/assistant-workspace/live-speculation-diagnostics-bridge')).initializeLiveSpeculationDiagnosticsBridge());
  add((await import('../features/assistant-workspace/live-speculation-eligibility-diagnostics')).initializeLiveSpeculationEligibilityDiagnostics());
  add((await import('../features/assistant-workspace/live-speculation-direct-gateway-transport')).initializeLiveSpeculationDirectGatewayTransport());
  add((await import('../features/assistant-workspace/live-speculation-handshake-transport')).initializeLiveSpeculationHandshakeTransport());
  add((await import('../features/assistant-workspace/live-speculation-early-trigger')).initializeLiveSpeculationEarlyTrigger());
  add((await import('../features/assistant-workspace/live-speculation-runtime')).initializeLiveSpeculationRuntime());
  add((await import('../features/assistant-workspace/live-call-prewarm-controller')).initializeLiveCallPrewarmController());
  if (!store.isDisposed) (await import('../features/assistant-workspace/live-runtime-provenance')).emitLiveRuntimeProvenance();
  add((await import('../features/assistant-workspace/live-voice-controller')).initializeLiveVoiceController());
  add((await import('../features/assistant-workspace/live-output-coordinator')).initializeLiveOutputCoordinator());
  add((await import('../features/assistant-workspace/live-presence-policy-controller')).initializeLivePresencePolicyController());
  add((await import('../features/assistant-workspace/live-voice-duplex-gate')).initializeLiveVoiceDuplexGate());
  add((await import('../features/assistant-workspace/live-voice-audio-duck-bridge')).initializeLiveVoiceAudioDuckBridge());
  add((await import('../features/assistant-workspace/live-voice-cue-asset-bridge')).initializeLiveVoiceCueAssetBridge());
  add((await import('../features/assistant-workspace/live-voice-cue-pack-loader')).initializeLiveVoiceCuePackLoader());
  add((await import('../features/assistant-workspace/live-tts-capability-controller')).initializeLiveTtsCapabilityController());
  add((await import('../features/assistant-workspace/live-tts-adaptive-buffer-controller')).initializeLiveTtsAdaptiveBufferController());
  add((await import('../features/assistant-workspace/live-voice-unified-audio-controller')).initializeLiveVoiceUnifiedAudioController());
  add((await import('../features/assistant-workspace/live-voice-pending-output-interrupt')).initializeLiveVoicePendingOutputInterrupt());
  add((await import('../features/assistant-workspace/live-avatar-presence')).initializeLiveAvatarPresenceController());
  add((await import('../features/assistant-workspace/live-conversation-initiative-controller')).initializeLiveConversationInitiativeController());
  add((await import('../features/assistant-workspace/live-conversation-repair-controller')).initializeLiveConversationRepairController());
  add((await import('../features/assistant-workspace/live-conversation-evaluation-controller')).initializeLiveConversationEvaluationController());
  add((await import('../features/assistant-workspace/live-conversation-durable-evaluation-controller')).initializeLiveConversationDurableEvaluationController());

  add((await import('../features/assistant-workspace/assistant-context-controller')).initializeAssistantContextController());
  add((await import('../features/assistant-workspace/desktop-companion-controls')).initializeDesktopCompanionControls());

  add((await import('../features/assistant-workspace/live-voice-form-sync')).initializeLiveVoiceFormSync());
  add((await import('../features/assistant-workspace/desktop-companion-expression-enricher')).initializeDesktopCompanionExpressionEnricher());
  add((await import('../features/assistant-workspace/desktop-companion-delivery')).initializeDesktopCompanionDeliveryController());
  const [watch, textSurface, evaluation, operationalGuard] = await Promise.all([
    import('../features/assistant-workspace/desktop-companion-watch-controller'),
    import('../features/assistant-workspace/desktop-companion-text-surface'),
    import('../features/assistant-workspace/desktop-companion-shadow-evaluation-controller'),
    import('../features/assistant-workspace/desktop-companion-operational-guard'),
  ]);
  add(textSurface.initializeDesktopCompanionTextSurface());
  add(evaluation.initializeDesktopCompanionShadowEvaluationController());
  add(operationalGuard.initializeDesktopCompanionOperationalGuard());
  add(watch.initializeDesktopCompanionWatchController());
  add((await import('../features/assistant-workspace/research-release-controller')).initializeResearchReleaseController());
}
