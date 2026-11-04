import { useEffect, useState } from 'react';
import { startBlankChat } from './sessionTools';

const STATUS_VISIBLE_MS = 6_000;

type Status = { message: string; danger: boolean };

/** Starts a blank chat; it keeps its place at the top of Chat's sidebar. */
export function NewChatButton() {
  const [creating, setCreating] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);

  useEffect(() => {
    if (!status) return;
    const timer = window.setTimeout(() => setStatus(null), STATUS_VISIBLE_MS);
    return () => window.clearTimeout(timer);
  }, [status]);

  async function createChat(): Promise<void> {
    setCreating(true);
    setStatus({ message: 'Creating new chat...', danger: false });
    try {
      await startBlankChat();
      setStatus(null);
    } catch (error) {
      setStatus({ message: error instanceof Error ? error.message : 'New chat could not be created.', danger: true });
    } finally {
      setCreating(false);
    }
  }

  return (
    <>
      <button type="button" aria-label={creating ? 'Creating new chat' : 'New chat'} aria-busy={creating || undefined} title="New chat" disabled={creating} onClick={() => void createChat()}>
        <span aria-hidden="true">＋</span>
        <span>{creating ? 'Creating...' : 'New chat'}</span>
      </button>
      <div className={`assistant-chatgpt-status${status ? ' visible' : ''}${status?.danger ? ' danger' : ''}`} role="status" aria-live="polite">{status?.message ?? ''}</div>
    </>
  );
}
