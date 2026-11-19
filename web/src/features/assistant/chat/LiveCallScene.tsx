import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import {
  addCallGuest,
  callSceneGuests,
  loadCallScene,
  removeCallGuest,
  setLiveCallSceneTalk,
  useCallScene,
  useLiveCallPresentation,
  useLiveConversationSelector,
} from '../workspace';
import { readEffectiveLiveConversationProfile } from './liveConversationProfileClient';
import { characterClient } from './characterClient';
import './LiveCallScene.css';

/**
 * Who is on the call (live companion roadmap 5.5/5.6): the chat's character hosts, and up to two of the person's
 * other characters can join. A name lights up while that member speaks; the server decides who answers each turn.
 * With the account's talk setting on, "Let them talk" lets the members talk to each other on this call (6.1).
 */
export function LiveCallScene({ sessionId }: { sessionId: string | null }) {
  const sceneState = useCallScene();
  const presentation = useLiveCallPresentation();
  const profile = useLiveConversationSelector((state) => state.profile) ?? readEffectiveLiveConversationProfile();
  const [choice, setChoice] = useState('');

  useEffect(() => {
    if (sessionId) void loadCallScene(sessionId);
  }, [sessionId]);

  const scene = sceneState.sessionId === sessionId ? sceneState.scene : null;
  const guests = callSceneGuests(sceneState);
  const canAdd = Boolean(scene?.available) && guests.length < (scene?.max_guests ?? 0);
  const charactersQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'characters'],
    queryFn: () => characterClient.list(),
    enabled: canAdd,
  });
  const candidates = useMemo(() => {
    const seated = new Set(scene?.members.map((member) => member.character_id) ?? []);
    return charactersQuery.data?.characters
      .filter((item) => item.enabled && item.status === 'active' && !seated.has(item.id)) ?? [];
  }, [charactersQuery.data?.characters, scene?.members]);

  if (!sessionId || !scene?.available) return null;
  const host = scene.members.find((member) => member.role === 'host');
  const speakingId = presentation.speaking ? presentation.sceneSpeakerId ?? host?.character_id ?? null : null;
  const selected = candidates.some((item) => item.id === choice) ? choice : candidates[0]?.id ?? '';

  return (
    <section className="live-call-scene" aria-label="On this call">
      <ul className="live-call-scene-members">
        {scene.members.map((member) => (
          <li
            key={member.character_id}
            className="live-call-scene-member"
            data-role={member.role}
            data-speaking={member.character_id === speakingId ? 'true' : undefined}
            aria-current={member.character_id === speakingId ? 'true' : undefined}
          >
            <span>{member.display_name}</span>
            {member.role === 'guest' ? (
              <button
                type="button"
                onClick={() => void removeCallGuest(sessionId, member.character_id)}
                disabled={Boolean(sceneState.changing)}
                aria-label={`Remove ${member.display_name} from the call`}
              >
                Remove
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      {profile?.scene_talk_enabled && guests.length ? (
        <label className="live-call-scene-talk">
          <input
            type="checkbox"
            checked={presentation.sceneTalkOn}
            disabled={!presentation.captureActive}
            onChange={(event) => setLiveCallSceneTalk(event.currentTarget.checked)}
          />
          <span>Let them talk</span>
        </label>
      ) : null}
      {canAdd && candidates.length ? (
        <form
          className="live-call-scene-add"
          onSubmit={(event) => {
            event.preventDefault();
            if (selected) void addCallGuest(sessionId, selected);
          }}
        >
          <select aria-label="Character to add to the call" value={selected} onChange={(event) => setChoice(event.target.value)}>
            {candidates.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}
          </select>
          <button type="submit" disabled={!selected || Boolean(sceneState.changing)}>
            {sceneState.changing === selected ? 'Adding…' : 'Add to call'}
          </button>
        </form>
      ) : null}
      {sceneState.error ? <p className="live-call-scene-error" role="alert">{sceneState.error}</p> : null}
    </section>
  );
}
