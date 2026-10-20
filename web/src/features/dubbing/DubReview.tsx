import { Button, Text } from '@mantine/core';
import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { dubbingClient, type DubProject, type DubSegment } from './api/dubbingClient';
import { FIT_LABELS, formatTime } from './dubbingOptions';

function Lane({ label, project, render }: { label: string; project: DubProject; render: (segment: DubSegment) => string | null }) {
  const duration = project.duration_seconds || Math.max(1, ...(project.segments ?? []).map((segment) => segment.end_seconds));
  return (
    <div className="dub-lane" role="group" aria-label={`${label} lane`}>
      <span className="dub-lane-label">{label}</span>
      <div className="dub-lane-track">
        {(project.segments ?? []).map((segment) => {
          const state = render(segment);
          if (state === null) return null;
          return (
            <a key={segment.id} href={`#dub-line-${segment.position}`} className={`dub-block ${state}`} title={`${formatTime(segment.start_seconds)} ${segment.speaker}`}
              style={{ left: `${(segment.start_seconds / duration) * 100}%`, width: `${Math.max(0.4, ((segment.end_seconds - segment.start_seconds) / duration) * 100)}%` }} />
          );
        })}
      </div>
    </div>
  );
}

function ReviewLine({ project, segment, onChanged, onRegenerate, onRetranslate }: {
  project: DubProject;
  segment: DubSegment;
  onChanged: (project: DubProject) => void;
  onRegenerate: () => void;
  onRetranslate: () => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const edit = useMutation({
    mutationFn: (update: { translation?: string; voice_override?: string }) => dubbingClient.updateLine(project.id, segment.id, update),
    onSuccess: (next) => { setDraft(null); onChanged(next); },
  });
  const approve = useMutation({
    mutationFn: (value: boolean) => dubbingClient.approve(project.id, [segment.id], value),
    onSuccess: onChanged,
  });
  const fitClass = segment.take_current ? segment.fit_status : 'pending';
  return (
    <li id={`dub-line-${segment.position}`} className={segment.approved ? 'dub-line approved' : 'dub-line'}>
      <div className="dub-line-meta">
        <span>{formatTime(segment.start_seconds)}</span>
        <b>{segment.speaker}</b>
        <span className={`dub-fit ${fitClass}`}>{segment.take_current ? FIT_LABELS[segment.fit_status] ?? segment.fit_status : segment.take_asset_id ? 'Take is out of date' : 'No take yet'}</span>
        <small>{segment.budget_seconds.toFixed(1)} s{segment.take_current ? ` · take ${segment.take_seconds.toFixed(1)} s` : ''}</small>
      </div>
      <p className="dub-source">{segment.source_text}</p>
      <textarea aria-label={`Line ${segment.position + 1} translation`} rows={2} value={draft ?? segment.translation}
        onChange={(event) => setDraft(event.currentTarget.value)}
        onBlur={() => { if (draft !== null && draft.trim() !== segment.translation) edit.mutate({ translation: draft }); else setDraft(null); }} />
      <div className="dub-line-actions">
        {segment.take_current ? <audio controls preload="none" src={`/api/assets/${encodeURIComponent(segment.take_asset_id)}/audio`} aria-label={`Line ${segment.position + 1} take`} /> : null}
        <input aria-label={`Line ${segment.position + 1} voice override`} placeholder="Voice (default: the speaker's)" defaultValue={segment.voice_override}
          onBlur={(event) => { const value = event.currentTarget.value.trim(); if (value !== segment.voice_override) edit.mutate({ voice_override: value }); }} />
        <Button size="compact-xs" variant="subtle" onClick={onRetranslate}>Translate again</Button>
        <Button size="compact-xs" variant="subtle" disabled={!segment.translation} onClick={onRegenerate}>Speak again</Button>
        <label className="dub-approve">
          <input type="checkbox" aria-label={`Approve line ${segment.position + 1}`} checked={segment.approved} disabled={!segment.take_current || approve.isPending}
            onChange={(event) => approve.mutate(event.currentTarget.checked)} />
          Approved
        </label>
      </div>
      {edit.isError || approve.isError ? <Text size="xs" role="alert">The line could not be saved.</Text> : null}
    </li>
  );
}

/** Review: lanes for source, translation, take and background, then each line to correct and approve. */
export function DubReview({ project, onChanged, onRegenerate, onRetranslate }: {
  project: DubProject;
  onChanged: (project: DubProject) => void;
  onRegenerate: (lineIds: string[]) => void;
  onRetranslate: (lineIds: string[]) => void;
}) {
  const segments = project.segments ?? [];
  const ready = segments.filter((segment) => segment.take_current && !segment.approved).map((segment) => segment.id);
  const approveAll = useMutation({ mutationFn: () => dubbingClient.approve(project.id, ready), onSuccess: onChanged });
  if (!segments.length) return <Text size="sm">Lines appear here once the video is transcribed.</Text>;
  const hasBackground = Boolean(project.assets?.background);
  return (
    <section className="dub-review" aria-label="Review">
      <div className="dub-review-head">
        <h3>Review</h3>
        <Button size="xs" variant="light" disabled={!ready.length} loading={approveAll.isPending} onClick={() => approveAll.mutate()}>Approve {ready.length} ready line{ready.length === 1 ? '' : 's'}</Button>
      </div>
      <div className="dub-timeline">
        <Lane label="Source" project={project} render={() => 'source'} />
        <Lane label="Translation" project={project} render={(segment) => (segment.translation ? 'translated' : 'missing')} />
        <Lane label="Take" project={project} render={(segment) => (segment.take_current ? `fit-${segment.fit_status}${segment.approved ? ' approved' : ''}` : null)} />
        {hasBackground ? (
          <div className="dub-lane" role="group" aria-label="Background lane"><span className="dub-lane-label">Background</span><div className="dub-lane-track"><span className="dub-block background" style={{ left: 0, width: '100%' }} /></div></div>
        ) : null}
      </div>
      <ol className="dub-lines">
        {segments.map((segment) => (
          <ReviewLine key={segment.id} project={project} segment={segment} onChanged={onChanged}
            onRegenerate={() => onRegenerate([segment.id])} onRetranslate={() => onRetranslate([segment.id])} />
        ))}
      </ol>
    </section>
  );
}
