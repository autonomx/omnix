import './app/viewApiFirewallBootstrap';
import React from 'react';
import ReactDOM from 'react-dom/client';
import { MantineProvider } from '@mantine/core';
import './design/layers.css';
import '@mantine/core/styles.layer.css';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { OmnixApp } from './app/OmnixApp';
import { installClientErrorReporting } from './app/clientErrorReporter';
import { omnixTheme } from './design/theme';
import './features/assistant/chat/chat-sidebar-manager.css';
import './features/assistant/chat/chat-sidebar-manager-layout-fix.css';
import './features/assistant/chat/researchProgressController.css';
import './styles.css';
import './legacy-layout.css';
import './features/assistant/chat/ChatbotWorkspaceTools.css';
import './features/assistant/chat/ChatbotWorkspaceSidePanelFix.css';
import './features/assistant/chat/ChatbotWorkspaceUtilityToggle.css';
import './features/assistant/workspace/assistant-context-controller.css';
import './features/assistant/workspace/desktop-companion-controls.css';
import './features/assistant/workspace/desktop-companion-text-surface.css';
import './features/assistant/workspace/research-release-controller.css';
import './features/storyteller/StorytellerWorkspace.css';
import './features/audiobook/AudiobookWorkspace.css';
import './features/storyteller/StorytellerSidebar.css';
import './features/storyteller/StoryMode.css';
import './features/storyteller/StoryThemeThumbnails.css';
import './features/storyteller/StoryAudioEnhancer.css';
import './features/podcast/PodcastWorkspaceLayoutFix.css';
import './features/podcast/PodcastWorkspaceEditable.css';
import './appearance-overrides.css';
import './theme-presets.css';
import './liquid-glass-theme.css';
import './features/assistant/chat/ChatbotWorkspaceFullscreen.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      retry: 1,
    },
  },
});

// Uncaught errors and unhandled rejections are reported to the gateway (WP-9.9).
installClientErrorReporting();

async function mountApplication(): Promise<void> {
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
