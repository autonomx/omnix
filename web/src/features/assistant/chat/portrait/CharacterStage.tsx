import { useSyncExternalStore } from 'react';

import { characterClient, type CharacterAvatarPack } from '../characterClient';
import { characterAvatarAssetUrl } from '../characterAvatarClient';
import { livePortrait, portraitNotice } from './livePortrait';
import { MemberPortrait } from './MemberPortrait';
import { packRevision } from './memberIdleLoops';
import './CharacterStage.css';

/** A library character a podcast can cast (D4): its profile's voice and personality, and its avatar pack. */
export type CastableCharacter = {
  id: string;
  name: string;
  personality: string;
  description: string;
  voiceAssetId: string | null;
  pack: CharacterAvatarPack | null;
};

/** The workspace's characters with their packs (a character without one has none). */
export async function listCastableCharacters(): Promise<CastableCharacter[]> {
  const { characters } = await characterClient.list();
  return Promise.all(characters.filter((character) => character.enabled !== false).map(async (character) => ({
    id: character.id,
    name: character.display_name,
    personality: character.personality_prompt,
    description: character.description ?? '',
    voiceAssetId: character.default_voice_asset_id ?? null,
    pack: await characterClient.avatarPack(character.id).catch(() => null),
  })));
}

export type StageCharacter = { id: string; name: string; pack: CharacterAvatarPack | null };

/** Whether a pack can stream a live portrait. */
export function isPortraitPack(pack: CharacterAvatarPack | null | undefined): boolean {
  return pack?.renderer === 'portrait' && Boolean(pack.base_asset_id);
}

/**
 * The cast's live avatars outside a call (a podcast, D4): one tile a character; the one speaking is drawn from the
 * live portrait, the others play their idle loop once their own turn has sent it, or show their picture.
 */
export function CharacterStage({ members, speakingId }: { members: readonly StageCharacter[]; speakingId: string | null }) {
  const portraitState = useSyncExternalStore(livePortrait.subscribe, livePortrait.getSnapshot, livePortrait.getSnapshot);
  const notice = portraitNotice(portraitState);
  const streaming = portraitState.status !== 'off';
  return (
    <div className="character-stage" role="group" aria-label="Live avatars">
      {members.map((member) => {
        const portrait = isPortraitPack(member.pack);
        const imageUrl = member.pack?.base_asset_id ? characterAvatarAssetUrl(member.pack.base_asset_id) : '';
        const speaking = speakingId === member.id;
        return (
          <figure
            key={member.id}
            className="character-stage-tile"
            data-speaking={speaking ? 'true' : undefined}
            data-renderer={portrait ? 'portrait' : 'picture'}
          >
            {portrait ? (
              <MemberPortrait
                characterId={member.id}
                revision={packRevision(member.pack)}
                imageUrl={imageUrl}
                label={`${member.name} live portrait`}
                live={streaming && portraitState.speakerId === member.id}
                streaming={streaming}
              />
            ) : imageUrl ? (
              <img src={imageUrl} alt={member.name} />
            ) : (
              <span className="character-stage-initials" aria-hidden="true">{member.name.slice(0, 2).toUpperCase()}</span>
            )}
            <figcaption>{member.name}{speaking ? <small>speaking</small> : null}</figcaption>
            {!portrait ? <p className="character-stage-note">Live video needs a portrait avatar</p> : null}
          </figure>
        );
      })}
      {notice ? <p className="character-stage-notice" role="status">{notice}</p> : null}
    </div>
  );
}
