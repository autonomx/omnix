import { useState } from 'react';
import type { StoryBlock, StoryProject, StoryVersionSummary } from './api/storyClient';
import { type DiffLine, diffBlocks } from './storyDiffModel';
import { visiblePages } from './storyProjectModel';

const actionLabels: Record<string, string> = { rewrite: 'rewrite', expand: 'expansion', dialogue: 'dialogue polish' };
const changePrefix = { same: '', removed: 'Removed: ', added: 'Added: ' } as const;

/** A diff as the writer reads it: kept lines plain, removed lines struck through, added lines marked (ST-6.2, ST-6.3). */
export function StoryDiff({ lines, label, speakerName }: {
  lines: DiffLine[];
  label: string;
  speakerName: (speakerId: string) => string;
}) {
  return (
    <ol aria-label={label} className="storyteller-diff">
      {lines.map((line, index) => (
        <li className={`storyteller-diff-${line.change}`} key={`${line.change}-${index}`}>
          {line.change === 'same' ? null : <span className="visually-hidden">{changePrefix[line.change]}</span>}
          {line.block.kind === 'dialogue' ? (
            <span className="storyteller-diff-speaker">{line.block.speaker_id ? speakerName(line.block.speaker_id) : 'Unknown speaker'}</span>
          ) : null}
          <span>{line.block.text}</span>
        </li>
      ))}
    </ol>
  );
}

export function castNames(project: StoryProject): (speakerId: string) => string {
  const names = new Map(project.characters.map((character) => [character.id, character.name]));
  return (speakerId) => names.get(speakerId) ?? speakerId;
}

/** The server's test for a page unchanged since a proposal: the same blocks, text, speaker and tag alike. */
const blockKey = (block: StoryBlock) =>
  JSON.stringify([block.kind ?? 'narration', block.text ?? '', block.speaker_id || null, block.attribution || null]);
const sameBlocks = (left: readonly StoryBlock[], right: readonly StoryBlock[]) =>
  left.length === right.length && left.every((block, index) => blockKey(block) === blockKey(right[index]));

/**
 * The changes jobs proposed to a selection or a page and the writer has not answered (ST-6.2): each shows
 * the original against the proposal, to accept into the page or reject. One whose page has changed since
 * can only be rejected, since accepting it would overwrite the writer's newer text.
 */
export function StoryProposals({ project, disabled, onAccept, onReject }: {
  project: StoryProject;
  disabled: boolean;
  onAccept: (version: StoryVersionSummary, pageNumber: number) => Promise<unknown>;
  onReject: (version: StoryVersionSummary) => Promise<unknown>;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const pending = project.versions
    .filter((version) => version.selection?.status === 'pending')
    .sort((left, right) => right.version_number - left.version_number);
  if (!pending.length) return null;
  const pages = visiblePages(project);
  const speakerName = castNames(project);
  const answer = (version: StoryVersionSummary, task: () => Promise<unknown>) => {
    setBusy(version.id);
    void task().finally(() => setBusy(null));
  };
  return (
    <div className="storyteller-proposals">
      {pending.map((version) => {
        const selection = version.selection!;
        const index = pages.findIndex((page) => page.id === selection.page_id);
        const page = index >= 0 ? pages[index] : null;
        const stale = !page || !sameBlocks(page.blocks.slice(selection.start, selection.end), selection.original);
        const name = `Proposed ${actionLabels[version.kind] ?? version.kind}${page ? ` of page ${index + 1}` : ''}`;
        return (
          <section aria-label={name} className="storyteller-proposal" key={version.id}>
            <p className="eyebrow">{name}</p>
            <StoryDiff label={`${name}: changes`} lines={diffBlocks(selection.original, selection.proposed)} speakerName={speakerName} />
            {stale ? (
              <p className="storyteller-proposal-stale">
                The page has changed since this was written, so it can no longer be accepted. Ask again from the page as it is now.
              </p>
            ) : null}
            <div className="storyteller-proposal-actions">
              <button
                className="storyteller-primary-action"
                disabled={disabled || stale || busy !== null}
                type="button"
                onClick={() => answer(version, () => onAccept(version, index + 1))}
              >
                Accept change
              </button>
              <button disabled={disabled || busy !== null} type="button" onClick={() => answer(version, () => onReject(version))}>
                {stale ? 'Dismiss' : 'Reject change'}
              </button>
            </div>
          </section>
        );
      })}
    </div>
  );
}
