import { useState, type Dispatch, type SetStateAction } from 'react';
import { isPortraitPack, type CastableCharacter } from '../assistant';
import { mockPodcastSpeakerProfiles } from '../conversation-production';
import { SpeakerFieldEditor, expandHint, speakerTextFields, type SpeakerTextField } from './SpeakerFieldEditor';

export type PodcastVoice = { id: string; label: string; speaker: string };

/** A speaker as the producer edits it: every text field is free text, whatever profile it started from. */
export type SpeakerDraft = {
  id: string; name: string; role: string; avatar: string; identity: string; beliefs: string; personality: string;
  speakingStyle: string; goal: string; instructions: string; voice: string; characterId: string;
};

export function toSpeakerDraft(profile: (typeof mockPodcastSpeakerProfiles)[number]): SpeakerDraft {
  return {
    id: profile.id,
    name: profile.name,
    role: profile.role,
    avatar: profile.avatar,
    identity: profile.identity,
    beliefs: profile.beliefs.join(', '),
    personality: profile.personality.join(', '),
    speakingStyle: profile.speakingStyle.join(', '),
    goal: profile.defaultGoal,
    instructions: '',
    voice: '',
    // A library character cast as this speaker (D4): its avatar appears when live avatars are on.
    characterId: '',
  };
}

export const defaultSpeakers = () => mockPodcastSpeakerProfiles.map(toSpeakerDraft);

/** Step 2 of the podcast studio: who speaks, in which voice, as which character; a text cell opens large on double-click. */
export function PodcastParticipants({ speakers, setSpeakers, voices, characters, stageCastCount, liveAvatars, onLiveAvatars, locked }: {
  speakers: SpeakerDraft[];
  setSpeakers: Dispatch<SetStateAction<SpeakerDraft[]>>;
  voices: PodcastVoice[];
  characters: CastableCharacter[];
  stageCastCount: number;
  liveAvatars: boolean;
  onLiveAvatars: (on: boolean) => void;
  /** A run is in progress: live avatars can't be switched mid-run. */
  locked: boolean;
}) {
  const [expanded, setExpanded] = useState<{ id: string; field: SpeakerTextField } | null>(null);
  const expandedSpeaker = expanded ? speakers.find((speaker) => speaker.id === expanded.id) : undefined;

  function updateSpeaker(id: string, field: keyof SpeakerDraft, value: string) {
    setSpeakers((current) => current.map((speaker) => speaker.id === id ? { ...speaker, [field]: value } : speaker));
  }
  function castCharacter(id: string, characterId: string) {
    const character = characters.find((entry) => entry.id === characterId);
    setSpeakers((current) => current.map((speaker) => {
      if (speaker.id !== id) return speaker;
      if (!character) return { ...speaker, characterId: '' };
      const voice = character.voiceAssetId && voices.some((entry) => entry.id === character.voiceAssetId) ? character.voiceAssetId : speaker.voice;
      return { ...speaker, characterId: character.id, name: character.name, avatar: character.name.slice(0, 2).toUpperCase(), identity: character.description.slice(0, 200) || speaker.identity, personality: character.personality.slice(0, 400) || speaker.personality, voice };
    }));
  }
  function addParticipant() {
    const index = speakers.length + 1;
    setSpeakers((current) => [...current, { id: `guest_${index}`, name: `Guest ${index}`, role: 'Guest Analyst', avatar: `G${index}`, identity: 'Guest Analyst', beliefs: '', personality: '', speakingStyle: '', goal: '', instructions: '', voice: voices[0]?.id ?? '', characterId: '' }]);
  }

  return (
    <article className="podcast-card">
      <div className="card-heading-row"><h3>2. Participants and voice casting</h3><small>{voices.length ? `Loaded ${voices.length} Voice Library voice${voices.length === 1 ? '' : 's'}` : 'No Voice Library voices found'}</small></div>
      <label className="podcast-live-avatars-toggle"><input type="checkbox" checked={liveAvatars} disabled={locked} onChange={(event) => onLiveAvatars(event.target.checked)} /><span><strong>Live avatars</strong><small>{stageCastCount ? `The cast speaks the live preview with ${stageCastCount === 1 ? 'its avatar' : 'their avatars'}` : 'Cast a character as a speaker to show its avatar'}</small></span></label>
      <div className="speaker-table editable-speaker-table">
        <div className="speaker-row speaker-header"><span>Speaker</span><span>Identity</span><span>Voice</span><span>Beliefs</span><span>Personality</span><span>Speaking style</span><span>Goal this episode</span><span>Instructions</span></div>
        {speakers.map((speaker, index) => (
          <div className="speaker-row editable-speaker-row" key={speaker.id}>
            <span className="speaker-cell-main"><b className={`speaker-avatar ${speaker.id}`}>{speaker.avatar}</b><span><input aria-label={`Speaker ${index + 1} name`} value={speaker.name} onChange={(event) => updateSpeaker(speaker.id, 'name', event.target.value)} /><input aria-label={`Speaker ${index + 1} role`} value={speaker.role} onChange={(event) => updateSpeaker(speaker.id, 'role', event.target.value)} /><select aria-label={`Speaker ${index + 1} character`} value={speaker.characterId} onChange={(event) => castCharacter(speaker.id, event.target.value)}><option value="">No character</option>{characters.map((character) => <option key={character.id} value={character.id}>{character.name}{isPortraitPack(character.pack) ? ' (live portrait)' : ''}</option>)}</select></span></span>
            <span><input aria-label={`Speaker ${index + 1} identity`} title={expandHint} value={speaker.identity} onDoubleClick={() => setExpanded({ id: speaker.id, field: 'identity' })} onChange={(event) => updateSpeaker(speaker.id, 'identity', event.target.value)} /></span>
            <span><select aria-label={`${speaker.name} voice`} value={speaker.voice} onChange={(event) => updateSpeaker(speaker.id, 'voice', event.target.value)}>{voices.map((voice) => <option key={voice.id} value={voice.id}>{voice.label}</option>)}{!voices.length ? <option value="">No cloned voices</option> : null}</select></span>
            {speakerTextFields.filter((entry) => entry.field !== 'identity').map(({ field, label }) => (
              <span key={field}><textarea rows={2} aria-label={`Speaker ${index + 1} ${label.toLowerCase()}`} title={expandHint} value={speaker[field]} onDoubleClick={() => setExpanded({ id: speaker.id, field })} onChange={(event) => updateSpeaker(speaker.id, field, event.target.value)} /></span>
            ))}
          </div>
        ))}
      </div>
      <SpeakerFieldEditor
        speakerName={expandedSpeaker?.name ?? ''}
        field={expandedSpeaker && expanded ? expanded.field : null}
        value={expandedSpeaker && expanded ? expandedSpeaker[expanded.field] : ''}
        onChange={(value) => { if (expanded) updateSpeaker(expanded.id, expanded.field, value); }}
        onClose={() => setExpanded(null)}
      />
      <button className="ghost-button" type="button" onClick={addParticipant}>+ Add participant</button>
    </article>
  );
}
