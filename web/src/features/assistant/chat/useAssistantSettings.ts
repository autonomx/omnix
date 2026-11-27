import { useEffect, useState } from 'react';
import type { AssistantWorkspaceRuntimeConfig } from '../workspace';
import {
  defaultAssistantSettings,
  loadAssistantSettings,
  saveAssistantSettings,
  type AssistantSettings,
  type AssistantView,
} from './chatbotWorkspaceModel';

/**
 * The assistant's personality, voice and approval settings, saved per browser. A browser with none takes them from the
 * server's profile on its first visit (so the voice setup gave the assistant reaches it) and again on Settings.
 */
export function useAssistantSettings(runtimeConfig: AssistantWorkspaceRuntimeConfig, activeView: AssistantView) {
  const [assistantSettings, setAssistantSettings] = useState<AssistantSettings>(() => loadAssistantSettings(runtimeConfig));
  const [settingsStatus, setSettingsStatus] = useState<string | null>(null);

  const onSettings = activeView === 'settings';
  useEffect(() => {
    void import('./assistantSettingsBootstrap')
      .then(({ bootstrapCentralAssistantSettings }) => bootstrapCentralAssistantSettings())
      .then(() => setAssistantSettings(loadAssistantSettings(runtimeConfig)))
      .catch(() => undefined);
  }, [onSettings, runtimeConfig]);

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

  return { assistantSettings, settingsStatus, updateAssistantSettings, resetAssistantSettings };
}
