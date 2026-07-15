import React from 'react';
import ReactDOM from 'react-dom/client';
import { MantineProvider } from '@mantine/core';
import '@mantine/core/styles.css';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { OmnixApp } from './app/OmnixApp';
import { omnixTheme } from './design/theme';
import './features/chatbot/sessionTools';
import './features/chatbot/researchProgressController';
import './features/chatbot/researchProgressController.css';
import { bootstrapCentralAssistantSettings } from './features/chatbot/assistantSettingsBootstrap';
import { initializeLiveChatWorkspace } from './features/chatbot/live-chat-workspace';
import { initializeVoiceSessionEvaluationWorkspace } from './features/chatbot/voice-session-evaluation-workspace';
import './features/podcast/podcastSessionGuard';
import './features/voice/voiceJobListGuard';
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
import { initializeLiveConversationDurableEvaluationController } from './features/assistant-workspace/live-conversation-durable-evaluation-controller';
import { initializeLiveConversationEvaluationController } from './features/assistant-workspace/live-conversation-evaluation-controller';
import { initializeLiveConversationInitiativeController } from './features/assistant-workspace/live-conversation-initiative-controller';
import { initializeLiveConversationRepairController } from './features/assistant-workspace/live-conversation-repair-controller';
import { initializeLiveConversationStoreBridge } from './features/assistant-workspace/live-conversation-store-bridge';
import { initializeLivePresencePolicyController } from './features/assistant-workspace/live-presence-policy-controller';
import { initializeLiveSpeechDeliveryBridge } from './features/assistant-workspace/live-speech-delivery-bridge';
import { initializeLiveVoiceAudioDuckBridge } from './features/assistant-workspace/live-voice-audio-duck-bridge';
import { initializeLiveVoiceDuplexGate } from './features/assistant-workspace/live-voice-duplex-gate';
import './features/assistant-workspace/live-voice-form-sync';
import './features/assistant-workspace/live-voice-controller';
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

initializeLiveConversationStoreBridge();
initializeLivePresencePolicyController();
initializeLiveVoiceDuplexGate();
initializeLiveSpeechDeliveryBridge();
initializeLiveVoiceAudioDuckBridge();
initializeLiveVoiceUnifiedAudioController();
initializeLiveAvatarPresenceController();
initializeLiveConversationInitiativeController();
initializeDesktopCompanionDeliveryController();
initializeLiveConversationRepairController();
initializeLiveConversationEvaluationController();
initializeLiveConversationDurableEvaluationController();
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
      const companion = await import('./features/assistant-workspace/desktop-companion-watch-controller');
      const controls = await import('./features/assistant-workspace/desktop-companion-controls');
      const evaluation = await import('./features/assistant-workspace/desktop-companion-shadow-evaluation-controller');
      const textSurface = await import('./features/assistant-workspace/desktop-companion-text-surface');
      companion.initializeDesktopCompanionWatchController();
      controls.initializeDesktopCompanionControls();
      evaluation.initializeDesktopCompanionShadowEvaluationController();
      textSurface.initializeDesktopCompanionTextSurface();
      return import('./features/assistant-workspace/research-release-controller');
    })
    .catch((error: unknown) => {
      console.error('Assistant context controls failed to initialize', error);
    });
}, 0);
