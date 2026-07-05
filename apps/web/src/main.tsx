import React from 'react';
import ReactDOM from 'react-dom/client';
import { MantineProvider } from '@mantine/core';
import '@mantine/core/styles.css';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { OmnixApp } from './app/OmnixApp';
import { omnixTheme } from './design/theme';
import './features/chatbot/sessionTools';
import './features/podcast/podcastSessionGuard';
import './styles.css';
import './legacy-layout.css';
import './features/chatbot/ChatbotWorkspaceTools.css';
import './features/chatbot/ChatbotWorkspaceSidePanelFix.css';
import './features/chatbot/ChatbotWorkspaceUtilityToggle.css';
import './features/assistant-workspace/assistant-context-controller.css';
import { initializeChatMessageStreamAudioController } from './features/assistant-workspace/chat-message-stream-audio-controller';
import './features/assistant-workspace/live-voice-form-sync';
import './features/assistant-workspace/live-voice-controller';
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

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      retry: 1,
    },
  },
});

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <QueryClientProvider client={queryClient}>
        <OmnixApp />
      </QueryClientProvider>
    </MantineProvider>
  </React.StrictMode>,
);

window.setTimeout(() => {
  initializeChatMessageStreamAudioController();
  initializeLiveVoiceUnifiedAudioController();
  void import('./features/assistant-workspace/assistant-context-controller').catch((error: unknown) => {
    console.error('Assistant context controls failed to initialize', error);
  });
}, 0);
