import React from 'react';
import ReactDOM from 'react-dom/client';
import { MantineProvider } from '@mantine/core';
import '@mantine/core/styles.css';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { OmnixApp } from './app/OmnixApp';
import { omnixTheme } from './design/theme';
import './features/chatbot/sessionTools';
import './features/chatbot/chat-sidebar-manager.css';
import './features/chatbot/chat-sidebar-manager-layout-fix.css';
import { initializeChatSidebarManager } from './features/chatbot/chat-sidebar-manager';
import './features/chatbot/researchProgressController';
import './features/chatbot/researchProgressController.css';
import { bootstrapCentralAssistantSettings } from './features/chatbot/assistantSettingsBootstrap';
import { initializeLiveChatWorkspace } from './features/chatbot/live-chat-workspace';
import { initializeVoiceSessionEvaluationWorkspace } from './features/chatbot/voice-session-evaluation-workspace';
import { installRpgTurnUiFetchInterceptor } from './features/rpg/rpgTurnUiStore';
import './features/podcast/podcastSessionGuard';
import './features/voice/voiceJobListGuard';
import { installVoiceLibraryAssetFallback } from './features/voice/voiceLibraryAssetFallback';
import { installVoiceLibraryFetchDiagnostics } from './features/voice/voiceLibraryFetchDiagnostics';
import './styles.css';
import './legacy-layout.css';
import './features/chatbot/ChatbotWorkspaceTools.css';
import './features/chatbot/ChatbotWorkspaceSidePanelFix.css';
import './features/chatbot/ChatbotWorkspaceUtilityToggle.css';
import './features/assistant-workspace/assistant-context-controller.css';
import './features/assistant-workspace/desktop-companion-controls.css';
import './features/assistant-workspace/desktop-companion-text-surface.css';
import './features/assistant-workspace/research-release-controller.css';
import { initializeChatMessageAudioControllerV2 } from './features/assistant-workspace/chat-message-audio-controller-v2';
import { initializeChatMessageStreamAudioController } from './features/assistant-workspace/chat-message-stream-audio-controller';
import { initializeDesktopCompanionDeliveryController } from './features/assistant-workspace/desktop-companion-delivery';
import { initializeLiveAvatarPresenceController } from './features/assistant-workspace/live-avatar-presence';
import { initializeLiveCallPrewarmController } from './features/assistant-workspace/live-call-prewarm-controller';
import { initializeLiveConversationDurableEvaluationController } from './features/assistant-workspace/live-conversation-durable-evaluation-controller';
import { initializeLiveConversationEvaluationController } from './features/assistant-workspace/live-conversation-evaluation-controller';
import { initializeLiveConversationInitiativeController } from './features/assistant-workspace/live-conversation-initiative-controller';
import { initializeLiveConversationRepairController } from './features/assistant-workspace/live-conversation-repair-controller';
import { initializeLiveConversationStoreBridge } from './features/assistant-workspace/live-conversation-store-bridge';
import { initializeLiveOutputCoordinator } from './features/assistant-workspace/live-output-coordinator';
import { initializeLivePresencePolicyController } from './features/assistant-workspace/live-presence-policy-controller';
import { initializeLiveSessionCoordinator } from './features/assistant-workspace/live-session-coordinator';
import { initializeLiveSpeculationDiagnosticsBridge } from './features/assistant-workspace/live-speculation-diagnostics-bridge';
import { initializeLiveSpeculationDirectGatewayTransport } from './features/assistant-workspace/live-speculation-direct-gateway-transport';
import { initializeLiveSpeculationEarlyTrigger } from './features/assistant-workspace/live-speculation-early-trigger';
import { initializeLiveSpeculationEligibilityDiagnostics } from './features/assistant-workspace/live-speculation-eligibility-diagnostics';
import { initializeLiveSpeculationHandshakeTransport } from './features/assistant-workspace/live-speculation-handshake-transport';
import { initializeLiveSpeculationRuntime } from './features/assistant-workspace/live-speculation-runtime';
import { initializeLiveSttAuthorityController } from './features/assistant-workspace/live-stt-authority-controller';
import { initializeLiveTtsAdaptiveBufferController } from './features/assistant-workspace/live-tts-adaptive-buffer-controller';
import { initializeLiveTtsCapabilityController } from './features/assistant-workspace/live-tts-capability-controller';
import { initializeLiveVoiceAudioDuckBridge } from './features/assistant-workspace/live-voice-audio-duck-bridge';
import { initializeLiveVoiceCueAssetBridge } from './features/assistant-workspace/live-voice-cue-asset-bridge';
import { initializeLiveVoiceCuePackLoader } from './features/assistant-workspace/live-voice-cue-pack-loader';
import { initializeLiveVoiceDuplexGate } from './features/assistant-workspace/live-voice-duplex-gate';
import './features/assistant-workspace/live-voice-form-sync';
import { initializeLiveVoiceController } from './features/assistant-workspace/live-voice-controller';
import { initializeLiveVoicePendingOutputInterrupt } from './features/assistant-workspace/live-voice-pending-output-interrupt';
import {
  initializeLiveVoiceTranscriptReconciliation,
  initializeLiveVoiceTurnCoordinator,
} from './features/assistant-workspace/live-voice-turn-coordinator';
import { emitLiveRuntimeProvenance } from './features/assistant-workspace/live-runtime-provenance';
import './features/assistant-workspace/live-voice-transcript-autoscroll';
import { initializeLiveVoiceUnifiedAudioController } from './features/assistant-workspace/live-voice-unified-audio-controller';
import './features/storyteller/StorytellerWorkspace.css';
import './features/storyteller/StorytellerSidebar.css';
import './features/storyteller/StoryMode.css';
import './features/storyteller/StoryThemeThumbnails.css';
import './features/storyteller/StoryAudioEnhancer.css';
import './features/storyteller/story-audio-enhancer';
import './features/storyteller/story-extra-mount';
import './features/podcast/PodcastWorkspaceLayoutFix.css';
import './features/podcast/PodcastWorkspaceEditable.css';
import './appearance-overrides.css';
import './theme-presets.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      retry: 1,
    },
  },
});

installRpgTurnUiFetchInterceptor();
installVoiceLibraryAssetFallback();
installVoiceLibraryFetchDiagnostics();
initializeLiveConversationStoreBridge();
initializeLiveSessionCoordinator();
initializeLiveVoiceTranscriptReconciliation();
initializeLiveSttAuthorityController();
initializeLiveVoiceTurnCoordinator();
initializeLiveSpeculationDiagnosticsBridge();
initializeLiveSpeculationEligibilityDiagnostics();
// Install the local direct-gateway transport before the speculation wrappers so
// their captured fetch implementations can bypass the Vite :5173 proxy for the
// private hot path. Non-local and failed direct requests fall back to same-origin.
initializeLiveSpeculationDirectGatewayTransport();
initializeLiveSpeculationHandshakeTransport();
initializeLiveSpeculationEarlyTrigger();
initializeLiveSpeculationRuntime();
initializeLiveCallPrewarmController();
emitLiveRuntimeProvenance();
initializeLiveVoiceController();
initializeLiveOutputCoordinator();
initializeLivePresencePolicyController();
initializeLiveVoiceDuplexGate();
initializeLiveVoiceAudioDuckBridge();
initializeLiveVoiceCueAssetBridge();
initializeLiveVoiceCuePackLoader();
initializeLiveTtsCapabilityController();
initializeLiveTtsAdaptiveBufferController();
initializeLiveVoiceUnifiedAudioController();
initializeLiveVoicePendingOutputInterrupt();
initializeLiveAvatarPresenceController();
initializeLiveConversationInitiativeController();
initializeDesktopCompanionDeliveryController();
initializeLiveConversationRepairController();
initializeLiveConversationEvaluationController();
initializeLiveConversationDurableEvaluationController();
initializeChatSidebarManager();
initializeLiveChatWorkspace(queryClient);
initializeVoiceSessionEvaluationWorkspace();

async function mountApplication(): Promise<void> {
  await bootstrapCentralAssistantSettings();
  ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
    <React.StrictMode>
      <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
        <QueryClientProvider client={queryClient}>
          <OmnixApp />
        </QueryClientProvider>
      </MantineProvider>
    </React.StrictMode>,
  );
}

void mountApplication();

window.setTimeout(() => {
  // Install the congestion-aware capture handler before the legacy stream-button handler.
  initializeChatMessageAudioControllerV2();
  initializeChatMessageStreamAudioController();
  void import('./features/assistant-workspace/assistant-context-controller')
    .then(async () => {
      // Deferred controller initialization remains intentionally best-effort.
    });
}, 0);
