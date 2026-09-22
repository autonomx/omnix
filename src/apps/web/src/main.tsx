import './app/viewApiFirewallBootstrap';
import React from 'react';
import ReactDOM from 'react-dom/client';
import { MantineProvider } from '@mantine/core';
import '@mantine/core/styles.css';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { OmnixApp } from './app/OmnixApp';
import { installViewApiFirewall } from './app/viewApiScope';
import { initializeViewRuntime } from './app/viewRuntime';
import { moduleIdFromPathname } from './app/viewApiScope';
import { omnixTheme } from './design/theme';
import './features/chatbot/chat-sidebar-manager.css';
import './features/chatbot/chat-sidebar-manager-layout-fix.css';
import './features/chatbot/researchProgressController.css';
import './styles.css';
import './legacy-layout.css';
import './features/chatbot/ChatbotWorkspaceTools.css';
import './features/chatbot/ChatbotWorkspaceSidePanelFix.css';
import './features/chatbot/ChatbotWorkspaceUtilityToggle.css';
import './features/assistant-workspace/assistant-context-controller.css';
import './features/assistant-workspace/desktop-companion-controls.css';
import './features/assistant-workspace/desktop-companion-text-surface.css';
import './features/assistant-workspace/research-release-controller.css';
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
import './features/chatbot/ChatbotWorkspaceFullscreen.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      retry: 1,
    },
  },
});

// Keep trading requests out of the globally installed assistant interceptors.
// The first installation still protects side-effect imports; this outer pass
// bypasses those wrappers for the active trading route entirely.
installViewApiFirewall({ outermost: true });

async function mountApplication(): Promise<void> {
  void initializeViewRuntime(moduleIdFromPathname(window.location.pathname), queryClient);
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
