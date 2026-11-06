/** What a character has come to understand from conversations: to read, reword or forget, like its memories. */
import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { ownerMemoryClient, type OwnerUnderstanding, type UnderstandingKind } from './memoryClient';

const ASPECT_LABEL: Record<string, string> = {
  communication_style: 'How you like to talk',
  humor: 'Humor',
  interests: 'Interests',
  values: 'What matters to you',
  temperament: 'Temperament',
  what_helps: 'What helps',
  what_to_avoid: 'What to avoid',
};
const METRICS: ['closeness' | 'trust' | 'ease', string][] = [['closeness', 'Closeness'], ['trust', 'Trust'], ['ease', 'Ease']];

function day(value?: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString(undefined, { dateStyle: 'medium' });
}

type Refreshed = { onSuccess: () => Promise<void>; onError: (failure: unknown) => void };

function UnderstoodRow({ ownerId, kind, itemKey, label, text, detail, note, editable, refreshed }: {
  ownerId: string;
  kind: UnderstandingKind;
  itemKey: string;
  label?: string;
  text: string;
  detail?: string;
  /** A second line under the text, such as what a lesson means the character does. */
  note?: string;
  editable?: boolean;
  refreshed: Refreshed;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const [forgetting, setForgetting] = useState(false);
  const rewordMutation = useMutation({
    mutationFn: (wording: string) => ownerMemoryClient.rewordUnderstanding(ownerId, kind, itemKey, wording),
    ...refreshed,
    onSuccess: async () => {
      setDraft(null);
      await refreshed.onSuccess();
    },
  });
  const forgetMutation = useMutation({
    mutationFn: () => ownerMemoryClient.forgetUnderstanding(ownerId, kind, itemKey),
    ...refreshed,
  });

  if (draft !== null) {
    return <li>
      <div>
        {label ? <small>{label}</small> : null}
        <textarea aria-label={`Reword ${label ?? 'this'}`} value={draft} rows={2} maxLength={400} onChange={(event) => setDraft(event.target.value)} />
      </div>
      <div className="character-memory-actions">
        <button type="button" disabled={!draft.trim() || rewordMutation.isPending} onClick={() => rewordMutation.mutate(draft.trim())}>Save</button>
        <button type="button" onClick={() => setDraft(null)}>Cancel</button>
      </div>
    </li>;
  }
  return <li>
    <div>
      {label ? <small>{label}{detail ? ` · ${detail}` : ''}</small> : detail ? <small>{detail}</small> : null}
      <p>{text}</p>
      {note ? <small>{note}</small> : null}
    </div>
    <div className="character-memory-actions">
      {forgetting ? <>
        <span>Forget this?</span>
        <button type="button" disabled={forgetMutation.isPending} onClick={() => forgetMutation.mutate()}>Forget</button>
        <button type="button" onClick={() => setForgetting(false)}>Keep</button>
      </> : <>
        {editable ? <button type="button" onClick={() => setDraft(text)}>Edit</button> : null}
        <button type="button" onClick={() => setForgetting(true)}>Forget</button>
      </>}
    </div>
  </li>;
}

type OwnSide = OwnerUnderstanding['own_side'];

/** The owner's own side: how it has come to see things, what it promised, what the two joke about. */
function TheirSide({ ownerId, ownerName, side, refreshed }: {
  ownerId: string;
  ownerName: string;
  side: OwnSide;
  refreshed: Refreshed;
}) {
  const shared = { ownerId, refreshed };
  const promises = side?.promises ?? [];
  const jokes = side?.jokes ?? [];
  return <div className="character-memory-group">
    <h5>{ownerName}&apos;s side</h5>
    <ul className="character-memory-list" aria-label={`${ownerName}'s side`}>
      {side?.stance ? <UnderstoodRow
        {...shared}
        kind="stance"
        itemKey="current"
        label={`How ${ownerName} has come to see it`}
        detail={day(side.stance_updated_at)}
        text={side.stance}
      /> : null}
      {promises.map((promise) => <UnderstoodRow
        {...shared}
        key={promise.key}
        kind="promise"
        itemKey={promise.key}
        label={promise.kept ? 'Promised · done' : 'Promised'}
        detail={day(promise.since)}
        text={promise.what}
      />)}
      {jokes.map((joke) => <UnderstoodRow
        {...shared}
        key={joke.key}
        kind="joke"
        itemKey={joke.key}
        label="Running joke"
        detail={(joke.seen ?? 1) > 1 ? `seen ${joke.seen} times` : undefined}
        text={joke.joke}
      />)}
    </ul>
  </div>;
}

export function CharacterUnderstandingPanel({ ownerId, ownerName, understanding, refreshed }: {
  ownerId: string;
  ownerName: string;
  understanding: OwnerUnderstanding;
  refreshed: Refreshed;
}) {
  const { person, connections, relationship, moods, episodes } = understanding;
  const lessons = understanding.lessons ?? [];
  const triggers = understanding.triggers ?? [];
  const side = understanding.own_side;
  const promises = side?.promises ?? [];
  const jokes = side?.jokes ?? [];
  const shared = { ownerId, refreshed };
  const theirSide = Boolean(side?.stance) || promises.length > 0 || jokes.length > 0;
  const nothing = !person.length && !lessons.length && !triggers.length && !connections.length && !relationship
    && !moods.length && !episodes.length && !theirSide;
  const numbers = relationship
    ? METRICS.flatMap(([key, label]) => {
      const value = relationship[key];
      return value === null || value === undefined ? [] : [`${label} ${Math.round(value * 100)}%`];
    }).join(' · ')
    : '';

  return <div className="character-memory-understanding">
    <header className="character-section-heading">
      <div><h4>How {ownerName} sees you</h4></div>
    </header>
    {nothing ? <p className="character-memory-empty">
      Nothing yet. A few minutes after a conversation goes quiet, {ownerName} reads it back and notes how you come across and how things stand between you.
    </p> : <p className="character-memory-intro">
      {ownerName} worked these out from your conversations and uses them in every chat. Correct or forget anything here. Deleting a chat also removes what was read from it.
    </p>}

    {relationship || person.length ? <ul className="character-memory-list" aria-label="How they see you">
      {relationship ? <UnderstoodRow
        {...shared}
        kind="relationship"
        itemKey="current"
        label="Between you"
        detail={numbers || (relationship.corrected ? 'in your words' : undefined)}
        text={relationship.statement}
        editable
      /> : null}
      {person.flatMap((note) => {
        const [before, ...older] = note.earlier ?? [];
        const label = ASPECT_LABEL[note.aspect] ?? note.aspect;
        return [
          <UnderstoodRow
            {...shared}
            key={note.key}
            kind="person"
            itemKey={note.key}
            label={label}
            detail={note.corrected ? 'in your words' : undefined}
            text={note.statement}
            editable
          />,
          ...(before ? [<UnderstoodRow
            {...shared}
            key={`${note.key}:earlier`}
            kind="earlier"
            itemKey={note.key}
            label={`${label} · before ${day(before.until) || 'it changed'}`}
            detail={older.length ? `and ${older.length} older` : undefined}
            text={before.statement}
          />] : []),
        ];
      })}
    </ul> : null}

    {theirSide ? <TheirSide {...shared} ownerName={ownerName} side={side} /> : null}

    {triggers.length ? <div className="character-memory-group">
      <h5>What affects your mood</h5>
      <ul className="character-memory-list">
        {triggers.map((trigger) => <UnderstoodRow
          {...shared}
          key={trigger.key}
          kind="trigger"
          itemKey={trigger.key}
          label={trigger.emotion.charAt(0).toUpperCase() + trigger.emotion.slice(1)}
          detail={[
            trigger.about?.length ? `about ${trigger.about.join(', ')}` : '',
            (trigger.seen ?? 1) > 1 ? `seen ${trigger.seen} times` : '',
          ].filter(Boolean).join(' · ') || undefined}
          text={trigger.pattern}
        />)}
      </ul>
    </div> : null}

    {lessons.length ? <div className="character-memory-group">
      <h5>From how you reacted</h5>
      <ul className="character-memory-list">
        {lessons.map((lesson) => <UnderstoodRow
          {...shared}
          key={lesson.key}
          kind="lesson"
          itemKey={lesson.key}
          note={lesson.advice ? `So ${ownerName} will: ${lesson.advice}` : undefined}
          label={ASPECT_LABEL[lesson.aspect] ?? lesson.aspect}
          detail={(lesson.seen ?? 1) > 1 ? `seen ${lesson.seen} times` : day(lesson.since)}
          text={lesson.lesson}
        />)}
      </ul>
    </div> : null}

    {episodes.length ? <div className="character-memory-group">
      <h5>Conversations</h5>
      <ul className="character-memory-list">
        {episodes.map((episode) => <UnderstoodRow
          {...shared}
          key={episode.key}
          kind="episode"
          itemKey={episode.key}
          label={episode.title}
          detail={day(episode.at)}
          text={episode.summary}
        />)}
      </ul>
    </div> : null}

    {connections.length ? <div className="character-memory-group">
      <h5>Connections</h5>
      <ul className="character-memory-list">
        {connections.map((link) => <UnderstoodRow
          {...shared}
          key={link.key}
          kind="connection"
          itemKey={link.key}
          text={`${link.subject} ${link.relation} ${link.object}`}
        />)}
      </ul>
    </div> : null}

    {moods.length ? <div className="character-memory-group">
      <h5>Moods</h5>
      <ul className="character-memory-list">
        {moods.map((mood) => <UnderstoodRow
          {...shared}
          key={mood.key}
          kind="mood"
          itemKey={mood.key}
          detail={day(mood.at)}
          text={mood.emotion}
        />)}
      </ul>
    </div> : null}
  </div>;
}
