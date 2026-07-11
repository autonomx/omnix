import { useEffect, useState } from 'react';

import {
  type BackchannelMode,
  type ConversationPaceSetting,
  type InterruptionPreference,
  type LiveConversationSettings,
  readLiveConversationSettings,
  updateLiveConversationSettings,
} from '../assistant-workspace/live-voice-conversation-settings';

const SETTINGS_CHANGED_EVENT = 'omnix:live-conversation-settings-changed';

export function LiveConversationControls() {
  const [settings, setSettings] = useState<LiveConversationSettings>(() => readLiveConversationSettings());

  useEffect(() => {
    const sync = (event: Event) => {
      const detail = (event as CustomEvent<LiveConversationSettings>).detail;
      setSettings(detail ?? readLiveConversationSettings());
    };
    window.addEventListener(SETTINGS_CHANGED_EVENT, sync);
    return () => window.removeEventListener(SETTINGS_CHANGED_EVENT, sync);
  }, []);

  function update(patch: Partial<LiveConversationSettings>): void {
    setSettings(updateLiveConversationSettings(patch));
  }

  return (
    <section className="live-chat-card" aria-labelledby="live-chat-turn-taking-heading">
      <header>
        <div>
          <p className="eyebrow">Conversation presence</p>
          <h3 id="live-chat-turn-taking-heading">Turn-taking</h3>
          <p>Control pause timing, interruption sensitivity, and optional spoken acknowledgements.</p>
        </div>
      </header>
      <div className="live-chat-control-grid">
        <label>
          <span>Conversation pace</span>
          <select
            aria-label="Conversation pace"
            value={settings.conversationPace}
            onChange={(event) => update({ conversationPace: event.currentTarget.value as ConversationPaceSetting })}
          >
            <option value="quick">Quick</option>
            <option value="balanced">Balanced</option>
            <option value="reflective">Reflective</option>
          </select>
        </label>
        <label>
          <span>Interruption behavior</span>
          <select
            aria-label="Interruption behavior"
            value={settings.interruptionPreference}
            onChange={(event) => update({ interruptionPreference: event.currentTarget.value as InterruptionPreference })}
          >
            <option value="easy">Easy to interrupt</option>
            <option value="balanced">Balanced</option>
            <option value="finish_more">Let assistant finish more often</option>
          </select>
        </label>
        <label>
          <span>Spoken acknowledgements</span>
          <select
            aria-label="Spoken acknowledgements"
            value={settings.backchannelMode}
            onChange={(event) => update({ backchannelMode: event.currentTarget.value as BackchannelMode })}
          >
            <option value="off">Off</option>
            <option value="minimal">Minimal</option>
            <option value="natural">Natural</option>
          </select>
        </label>
      </div>
    </section>
  );
}
