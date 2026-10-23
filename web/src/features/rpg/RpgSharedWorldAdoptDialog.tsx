import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { RpgWorldSummary } from './api/rpgWorldLibraryClient';
import { rpgWorldSharingClient } from './api/rpgWorldSharingClient';
import { sharedWorldInfo } from './rpgSharedWorld';

interface RpgSharedWorldAdoptDialogProps {
  world: RpgWorldSummary;
  onAdopted: (worldId: string) => void;
  onCancel: () => void;
  onEdit: (worldId: string) => void;
}

/** Review a world made elsewhere, then adopt it: nothing from it launches until someone here does. */
export function RpgSharedWorldAdoptDialog({ world, onAdopted, onCancel, onEdit }: RpgSharedWorldAdoptDialogProps) {
  const queryClient = useQueryClient();
  const info = sharedWorldInfo(world);
  const [reviewed, setReviewed] = useState(false);
  const adopt = useMutation({
    mutationFn: () => rpgWorldSharingClient.adopt(world.id, info.bundleSha256),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ['feature', 'rpg'] });
      onAdopted(result.world_id);
    },
  });
  return (
    <div className="rpg-authoring-modal" role="dialog" aria-modal="true" aria-label="Review a shared world">
      <form className="rpg-shared-world-dialog" onSubmit={(event) => { event.preventDefault(); adopt.mutate(); }}>
        <h3>Review {world.title}</h3>
        <p>
          This world was made in someone else&apos;s Omnix{info.author ? <> and shared by <strong>@{info.author}</strong></> : null}.
          Adopt it to play it here.
        </p>
        <ul className="rpg-shared-world-points">
          <li>Its places, people and story become what the storyteller reads during your campaigns, so look through it first.</li>
          <li>Omnix checked that the file is the one {info.author ? 'listed in the community catalog' : 'you imported'} (SHA-256 <code>{info.bundleSha256.slice(0, 12)}…</code>).</li>
          <li>Adopting keeps the world as it is, recorded as accepted by you. You can edit it afterwards like any of your worlds.</li>
        </ul>
        <label className="rpg-shared-world-check">
          <input checked={reviewed} type="checkbox" onChange={(event) => setReviewed(event.currentTarget.checked)} />
          <span>I&apos;ve looked through this world and want to play it</span>
        </label>
        {adopt.isError ? <p className="rpg-authoring-feedback" role="alert">{adopt.error instanceof Error ? adopt.error.message : 'The world could not be adopted.'}</p> : null}
        <div>
          <button className="rpg-secondary-button" type="button" onClick={onCancel}>Not now</button>
          <button className="rpg-secondary-button" type="button" onClick={() => onEdit(world.id)}>Open in editor</button>
          <button type="submit" disabled={!reviewed || adopt.isPending}>{adopt.isPending ? 'Adopting…' : 'Adopt this world'}</button>
        </div>
      </form>
    </div>
  );
}
