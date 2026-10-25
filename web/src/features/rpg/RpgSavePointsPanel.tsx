import { Button } from '@mantine/core';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { FormEvent } from 'react';
import { useState } from 'react';
import { rpgSessionClient } from './api/rpgSessionClient';
import { rpgPlayerMessage } from './rpgPlayerMessage';

interface RpgSavePointsPanelProps {
  busy: boolean;
  liveSessionId: string;
  onBack: () => void;
  /** The campaign returned to a save point: a turn of its own. */
  onReturned: () => void;
  /** Runs one action with its progress and failure on the menu bar; resolves to what the bar then says. */
  run: (progress: string, action: () => Promise<string | undefined>, failure: string) => Promise<void>;
}

/** Save points (rewind.md): name this moment, return to one, or delete it. */
export function RpgSavePointsPanel({ busy, liveSessionId, onBack, onReturned, run }: RpgSavePointsPanelProps) {
  const queryClient = useQueryClient();
  const [savePointName, setSavePointName] = useState('');
  const queryKey = ['feature', 'rpg', 'save-points', liveSessionId];
  const savePointsQuery = useQuery({
    queryKey,
    queryFn: () => rpgSessionClient.listRpgSavePoints(liveSessionId),
    enabled: Boolean(liveSessionId),
  });
  const savePoints = savePointsQuery.data?.save_points ?? [];

  const createSavePoint = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const name = savePointName.trim();
    if (!name) return;
    void run('Saving…', async () => {
      queryClient.setQueryData(queryKey, await rpgSessionClient.createRpgSavePoint(liveSessionId, name));
      setSavePointName('');
      return `Saved as “${name}”.`;
    }, 'The save point could not be made.');
  };

  const returnToSavePoint = (name: string) => {
    if (!window.confirm(`Return to “${name}”? You can undo this like any turn.`)) return;
    void run(`Returning to “${name}”…`, async () => {
      await rpgSessionClient.rewindRpgSession(liveSessionId, name);
      onReturned();
      return `Returned to “${name}”.`;
    }, 'The campaign could not return to that save point.');
  };

  const deleteSavePoint = (name: string) => {
    if (!window.confirm(`Delete the save point “${name}”?`)) return;
    void run('Deleting…', async () => {
      queryClient.setQueryData(queryKey, await rpgSessionClient.deleteRpgSavePoint(liveSessionId, name));
      return `Save point “${name}” deleted.`;
    }, 'The save point could not be deleted.');
  };

  return (
    <div role="group" className="rpg-launcher-panel" aria-label="Save points">
      <div className="rpg-launcher-section-heading">
        <div>
          <p className="eyebrow">Save points</p>
          <h4>Moments to return to</h4>
        </div>
        <Button variant="subtle" type="button" disabled={busy} onClick={onBack}>
          Back
        </Button>
      </div>
      <form className="rpg-save-point-form" onSubmit={createSavePoint}>
        <label>
          <span>Name this moment</span>
          <input maxLength={80} placeholder="Before the gate" value={savePointName} onChange={(event) => setSavePointName(event.currentTarget.value)} />
        </label>
        <Button type="submit" disabled={busy || !savePointName.trim()}>Save here</Button>
      </form>
      {savePointsQuery.isError ? (
        <p className="rpg-session-launcher-error">{rpgPlayerMessage(savePointsQuery.error, 'The save points could not be read.')}</p>
      ) : savePointsQuery.isPending ? (
        <p>Reading save points…</p>
      ) : savePoints.length ? (
        <ul className="rpg-load-game-list" aria-label="Your save points">
          {savePoints.map((point) => (
            <li key={point.name} className="rpg-load-game-card">
              <div className="rpg-load-game-main">
                <strong>{point.name}</strong>
                <span>{new Date(point.created_at).toLocaleString()}</span>
              </div>
              <div className="rpg-load-game-actions">
                <Button size="xs" variant="light" type="button" disabled={busy} onClick={() => returnToSavePoint(point.name)}>
                  Return here
                </Button>
                <Button size="xs" variant="outline" type="button" disabled={busy} onClick={() => deleteSavePoint(point.name)}>
                  Delete
                </Button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p>No save points yet.</p>
      )}
    </div>
  );
}
