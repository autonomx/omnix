import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { type StoryProject, type StoryVersionSummary, storyApiClient } from './api/storyClient';
import { diffBlocks, diffCounts, manuscriptBlocks } from './storyDiffModel';
import { versionLabel, visiblePages } from './storyProjectModel';
import { StoryDiff, castNames } from './StoryProposals';

const NOW = 'now';

const versionQuery = (projectId: string, versionId: string) => ({
  queryKey: ['story', 'projects', 'version', projectId, versionId],
  queryFn: () => storyApiClient.getVersion(projectId, versionId),
  staleTime: Infinity,
});

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`;

/**
 * A version read against the manuscript as it is now, or against another version (ST-6.3): what restoring
 * it would remove and add, block by block, with Restore beside it.
 */
export function StoryCompare({ project, version, disabled, onRestore, onClose }: {
  project: StoryProject;
  version: StoryVersionSummary;
  disabled: boolean;
  onRestore: (version: StoryVersionSummary) => void;
  onClose: () => void;
}) {
  const [against, setAgainst] = useState<string>(NOW);
  const chosen = useQuery(versionQuery(project.id, version.id));
  const other = useQuery({ ...versionQuery(project.id, against), enabled: against !== NOW });
  const others = project.versions.filter((candidate) => candidate.id !== version.id)
    .sort((left, right) => right.version_number - left.version_number);
  const before = against === NOW ? manuscriptBlocks(visiblePages(project)) : other.data ? manuscriptBlocks(other.data.pages) : null;
  const lines = chosen.data && before ? diffBlocks(before, manuscriptBlocks(chosen.data.pages)) : null;
  const counts = lines ? diffCounts(lines) : null;
  const againstLabel = against === NOW ? 'the manuscript now' : `version ${others.find((candidate) => candidate.id === against)?.version_number ?? ''}`;
  const name = `Compare version ${version.version_number}`;

  return (
    <section aria-label={name} className="storyteller-compare">
      <header className="storyteller-compare-header">
        <div>
          <p className="eyebrow">{name}</p>
          <h2>{versionLabel(version)}</h2>
        </div>
        <label>
          <span>Against</span>
          <select aria-label="Compare against" value={against} onChange={(event) => setAgainst(event.target.value)}>
            <option value={NOW}>The manuscript now</option>
            {others.map((candidate) => (
              <option key={candidate.id} value={candidate.id}>{`v${candidate.version_number} ${versionLabel(candidate)}`}</option>
            ))}
          </select>
        </label>
      </header>
      {chosen.isError || other.isError ? (
        <p className="storyteller-persist-feedback error" role="alert">The version could not be loaded.</p>
      ) : !lines || !counts ? (
        <p className="storyteller-side-empty">Loading the version…</p>
      ) : (
        <>
          <p className="storyteller-compare-summary" role="status">
            {counts.removed || counts.added
              ? `Against ${againstLabel}, version ${version.version_number} removes ${plural(counts.removed, 'paragraph')} and adds ${plural(counts.added, 'paragraph')}.`
              : `Version ${version.version_number} is the same as ${againstLabel}.`}
          </p>
          <StoryDiff label={`${name}: changes`} lines={lines} speakerName={castNames(project)} />
        </>
      )}
      <div className="storyteller-proposal-actions">
        <button className="storyteller-primary-action" disabled={disabled} type="button" onClick={() => onRestore(version)}>
          {`Restore version ${version.version_number}`}
        </button>
        <button type="button" onClick={onClose}>Close</button>
      </div>
    </section>
  );
}
