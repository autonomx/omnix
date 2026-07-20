import { useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { RpgAuthoringSection } from '../../api/rpgWorldAuthoringClient';
import {
  rpgWorldLibraryClient,
  type RpgWorldGenerationRun,
} from '../../api/rpgWorldLibraryClient';
import './RpgWorldGenerationPanel.css';

interface RpgWorldGenerationPanelProps {
  generation?: RpgWorldGenerationRun | Record<string, never>;
  sections: RpgAuthoringSection[];
  worldId: string;
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function statusLabel(value: string): string {
  return value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function RpgWorldGenerationPanel({ generation, sections, worldId }: RpgWorldGenerationPanelProps) {
  const queryClient = useQueryClient();
  const [depth, setDepth] = useState('standard');
  const [startingLocation, setStartingLocation] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [strategy, setStrategy] = useState('reuse_unchanged');
  const [replaceLocked, setReplaceLocked] = useState(false);
  const [directions, setDirections] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState('');
  const generationSections = useMemo(
    () => sections.filter((section) => section.supports_generation),
    [sections],
  );
  const currentRun = generation && 'run_id' in generation ? generation as RpgWorldGenerationRun : undefined;
  const progress = record(currentRun?.progress);

  const generate = useMutation({
    mutationFn: (scope: Record<string, unknown>) => rpgWorldLibraryClient.startGeneration(worldId, {
      depth,
      starting_location: startingLocation,
      background_expansion: true,
      scope,
      strategy,
      replace_locked: replaceLocked,
      directives: Object.fromEntries(
        Object.entries(directions)
          .filter(([, value]) => value.trim())
          .map(([topicId, direction]) => [topicId, { direction: direction.trim() }]),
      ),
      entity_manifest: {},
    }),
    onSuccess: async (result) => {
      setFeedback(`Generation started: ${result.run.run_id}`);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-authoring-manifest', worldId] }),
        queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-authoring-section', worldId] }),
        queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-authoring-workspace'] }),
      ]);
    },
    onError: (cause) => setFeedback(cause instanceof Error ? cause.message : 'Generation could not be started.'),
  });

  const start = (mode: string) => {
    const scope = mode === 'selected'
      ? { mode, topic_ids: selected }
      : { mode };
    generate.mutate(scope);
  };

  return (
    <section className="rpg-authoring-page rpg-generation-panel" aria-label="World generation">
      <div className="rpg-authoring-page-heading">
        <div><p className="eyebrow">Workspace</p><h2>World Generation</h2><p>Generate the full world or safely target selected, stale, or failed topics.</p></div>
        {currentRun ? <span>{statusLabel(currentRun.status)} · {Number(progress.percent || 0)}%</span> : <span>Not generated</span>}
      </div>

      <div className="rpg-generation-settings">
        <label><span>Depth</span><select value={depth} onChange={(event) => setDepth(event.currentTarget.value)}><option value="quick">Quick</option><option value="standard">Standard</option><option value="epic">Epic</option></select></label>
        <label><span>Starting location</span><input placeholder="Optional stable location ID" value={startingLocation} onChange={(event) => setStartingLocation(event.currentTarget.value)} /></label>
        <label><span>Strategy</span><select value={strategy} onChange={(event) => setStrategy(event.currentTarget.value)}><option value="reuse_unchanged">Reuse unchanged</option><option value="force">Force selected replacement</option></select></label>
        <label className="rpg-authoring-checkbox"><input type="checkbox" checked={replaceLocked} onChange={(event) => setReplaceLocked(event.currentTarget.checked)} /><span>Allow forced replacement of locked manual topics</span></label>
      </div>

      <div className="rpg-generation-actions">
        <button type="button" disabled={generate.isPending} onClick={() => start('full')}>Generate World</button>
        <button type="button" disabled={generate.isPending || !selected.length} onClick={() => start('selected')}>Generate Selected</button>
        <button className="rpg-secondary-button" type="button" disabled={generate.isPending} onClick={() => start('stale')}>Regenerate Stale</button>
        <button className="rpg-secondary-button" type="button" disabled={generate.isPending} onClick={() => start('failed')}>Retry Failed</button>
      </div>
      {feedback ? <p className="rpg-authoring-feedback" aria-live="polite">{feedback}</p> : null}

      <div className="rpg-generation-topic-grid">
        {generationSections.map((section) => (
          <article key={section.id}>
            <label className="rpg-generation-topic-choice">
              <input
                type="checkbox"
                checked={selected.includes(section.id)}
                onChange={(event) => setSelected((current) => event.currentTarget.checked
                  ? [...current, section.id]
                  : current.filter((value) => value !== section.id))}
              />
              <span><strong>{section.label}</strong><small>{statusLabel(section.operational_status)} · {statusLabel(section.editorial_status)}</small></span>
            </label>
            <textarea
              aria-label={`Generation direction for ${section.label}`}
              placeholder="Optional direction for this topic…"
              rows={2}
              value={directions[section.id] ?? ''}
              onChange={(event) => setDirections((current) => ({ ...current, [section.id]: event.currentTarget.value }))}
            />
          </article>
        ))}
      </div>

      {currentRun ? (
        <details className="rpg-authoring-structured-data">
          <summary>Current run details</summary>
          <pre>{JSON.stringify({ scope: record(currentRun.context).scope, progress: currentRun.progress, plan: currentRun.plan }, null, 2)}</pre>
        </details>
      ) : null}
    </section>
  );
}
