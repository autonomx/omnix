import type { AlertDeliveryEditor } from './alertDelivery';
import { ALERT_SOUNDS, playAlertSound, type AlertSoundName } from './alertSounds';
import type { TradingAlertNotificationChannel } from './tradingTypes';

const CHANNELS: Array<{ value: TradingAlertNotificationChannel; label: string }> = [
  { value: 'app', label: 'App' },
  { value: 'toast', label: 'Toasts' },
  { value: 'sound', label: 'Sound' },
  { value: 'webhook', label: 'Webhook' },
];

/**
 * The alert's channels (TVP-1.5): in-app, toast, sound with its sound, and webhook with its URL and optional signing
 * secret. The stored URL and secret are never shown; typing new ones replaces them.
 */
export function AlertDeliveryFields({
  editor, onChange,
}: {
  editor: AlertDeliveryEditor & { notifications: TradingAlertNotificationChannel[] };
  onChange: (patch: Partial<AlertDeliveryEditor> & { notifications?: TradingAlertNotificationChannel[] }) => void;
}) {
  const toggle = (channel: TradingAlertNotificationChannel) => onChange({
    notifications: editor.notifications.includes(channel)
      ? editor.notifications.filter((item) => item !== channel)
      : [...editor.notifications, channel],
  });
  const stored = editor.webhookDisplay ?? null;
  return (
    <>
      {CHANNELS.map((option) => <label key={option.value}><input type="checkbox" checked={editor.notifications.includes(option.value)} onChange={() => toggle(option.value)} />{option.label}</label>)}
      {editor.notifications.includes('sound') ? (
        <select aria-label="Alert sound" value={editor.sound ?? 'chime'} onChange={(event) => { const sound = event.target.value as AlertSoundName; playAlertSound(sound); onChange({ sound }); }}>
          {ALERT_SOUNDS.map((sound) => <option key={sound} value={sound}>{sound[0].toUpperCase() + sound.slice(1)}</option>)}
        </select>
      ) : null}
      {editor.notifications.includes('webhook') ? (
        <span className="trading-alert-webhook">
          <input
            aria-label="Webhook URL"
            type="url"
            inputMode="url"
            autoComplete="off"
            required={!stored}
            maxLength={2000}
            placeholder={stored ? `${stored} (saved; type to replace)` : 'https://…'}
            value={editor.webhookUrl ?? ''}
            onChange={(event) => onChange({ webhookUrl: event.target.value })}
          />
          <input
            aria-label="Webhook signing secret"
            type="password"
            autoComplete="new-password"
            maxLength={500}
            placeholder={editor.webhookHasSecret ? 'Secret saved; type to replace' : 'Signing secret (optional)'}
            value={editor.webhookSecret ?? ''}
            onChange={(event) => onChange({ webhookSecret: event.target.value })}
          />
        </span>
      ) : null}
    </>
  );
}
