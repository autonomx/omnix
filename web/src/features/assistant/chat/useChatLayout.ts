import { useMediaQuery } from '@mantine/hooks';
import { useCallback, useEffect, useState, type SetStateAction } from 'react';
import {
  ASSISTANT_SIDEBAR_STORAGE_KEY,
  ASSISTANT_SIDE_PANEL_STORAGE_KEY,
  ASSISTANT_VIEW_STORAGE_KEY,
  assistantSidebarItems,
  type AssistantView,
  type UtilityPanel,
} from './chatbotWorkspaceModel';

/**
 * Below this width the chat list folds to its icon rail, so the Live Voice rail keeps its place on the right
 * (ChatWorkspaceLayout.css stacks the panels only below 900px).
 */
export const NARROW_CHAT_QUERY = '(max-width: 1180px)';

/** Chat's layout: the active view, full screen, and the two collapsible side panels (persisted per browser). */
export function useChatLayout(initialToolId: string | null) {
  const [activeView, setActiveView] = useState<AssistantView>(() => {
    if (initialToolId) return 'tools';
    const stored = window.localStorage.getItem(ASSISTANT_VIEW_STORAGE_KEY);
    return assistantSidebarItems.some((item) => item.id === stored) ? stored as AssistantView : 'chats';
  });
  const [isChatFullscreen, setIsChatFullscreen] = useState(false);
  const [activeUtilityPanel, setActiveUtilityPanel] = useState<UtilityPanel>('voice');
  const [isStoredSidebarMinimized, setIsStoredSidebarMinimized] = useState(() => {
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
      window.localStorage.setItem(ASSISTANT_SIDEBAR_STORAGE_KEY, String(isStoredSidebarMinimized));
    } catch {
      // Ignore local storage failures; the navigation remains usable for this session.
    }
  }, [isStoredSidebarMinimized]);

  // A narrow window starts with the chat list folded; opening it there is not remembered for wide windows.
  const narrow = useMediaQuery(NARROW_CHAT_QUERY, false, { getInitialValueInEffect: false });
  const [isExpandedWhileNarrow, setIsExpandedWhileNarrow] = useState(false);
  useEffect(() => {
    if (!narrow) setIsExpandedWhileNarrow(false);
  }, [narrow]);
  const isAssistantSidebarMinimized = narrow ? !isExpandedWhileNarrow : isStoredSidebarMinimized;
  const setIsAssistantSidebarMinimized = useCallback((update: SetStateAction<boolean>) => {
    if (narrow) setIsExpandedWhileNarrow((expanded) => !(typeof update === 'function' ? update(!expanded) : update));
    else setIsStoredSidebarMinimized(update);
  }, [narrow]);

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

  return {
    activeView, setActiveView,
    isChatFullscreen, setIsChatFullscreen,
    activeUtilityPanel, setActiveUtilityPanel,
    isAssistantSidebarMinimized, setIsAssistantSidebarMinimized,
    isSidePanelMinimized, setIsSidePanelMinimized,
  };
}
