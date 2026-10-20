import { Button, Text } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { omnixApiClient } from '../../api/client';
import { DUB_STEPS, dubbingClient, type DubProject, type DubStep } from './api/dubbingClient';
import { DubReview } from './DubReview';

const ACTIVE = new Set(['queued', 'running', 'waiting']);

function stepState(project: DubProject, step: DubStep): { status: string; error: string } {
  const value = (project.steps?.[step] ?? {}) as { status?: string; error?: string };
  return { status: value.status ?? 'not run', error: value.error ?? '' };
}

function Casting({ project, onSave }: { project: DubProject; onSave: (casting: Record<string, string>) => void }) {
  const voices = useQuery({ queryKey: ['platform', 'assets'], queryFn: () => omnixApiClient.listAssets() });
  const profiles = (voices.data?.assets ?? []).filter((asset) => asset.type === 'voice_profile');
  const speakers = [...new Set((project.segments ?? []).map((segment) => segment.speaker))];
  if (!speakers.length) return null;
  return (
    <section className="dub-casting" aria-label="Casting">
      <h3>Voices</h3>
      {speakers.map((speaker) => (
        <label key={speaker}>{speaker}
          <select aria-label={`Voice for ${speaker}`} value={project.casting?.[speaker] ?? ''} onChange={(event) => onSave({ ...(project.casting ?? {}), [speaker]: event.currentTarget.value })}>
            <option value="">{project.steps?.cast ? 'Needs a voice' : 'Clone from the video'}</option>
            {profiles.map((asset) => {
              const name = String(asset.metadata?.profile_name ?? asset.file_name ?? asset.id);
              return <option key={asset.id} value={asset.id}>{name}</option>;
            })}
          </select>
        </label>
      ))}
    </section>
  );
}

export function DubProjectView({ projectId, onDeleted }: { projectId: string; onDeleted: () => void }) {
  const queryClient = useQueryClient();
  const key = ['feature', 'dubbing', 'project', projectId];
  const project = useQuery({
    queryKey: key,
    queryFn: () => dubbingClient.getProject(projectId),
    refetchInterval: (query) => {
      const steps = Object.values(query.state.data?.steps ?? {}) as Array<{ status?: string }>;
      return steps.some((step) => ACTIVE.has(step.status ?? '')) ? 2000 : false;
    },
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: key });
  const run = useMutation({
    mutationFn: ({ step, chain, lineIds }: { step: DubStep; chain?: boolean; lineIds?: string[] }) => dubbingClient.runStep(projectId, step, { chain, lineIds }),
    onSuccess: () => { window.setTimeout(() => void refresh(), 500); },
  });
  const update = useMutation({
    mutationFn: (casting: Record<string, string>) => dubbingClient.updateProject(projectId, { casting }),
    onSuccess: (data) => queryClient.setQueryData(key, data),
  });
  const remove = useMutation({ mutationFn: () => dubbingClient.deleteProject(projectId), onSuccess: onDeleted });

  if (!project.data) return <Text size="sm">{project.isError ? 'The dub could not be loaded.' : 'Loading…'}</Text>;
  const data = project.data;
  const allApproved = data.line_count > 0 && data.approved_count === data.line_count;
  const assets = data.assets ?? {};
  return (
    <div className="dub-project">
      <div className="dub-project-head">
        <div><h3>{data.title}</h3><Text size="sm">{data.source_language} → {data.target_language} · {data.line_count} lines, {data.approved_count} approved</Text></div>
        <Button size="xs" variant="subtle" color="red" onClick={() => { if (window.confirm('Delete this dub? Its audio and video stay in the library.')) remove.mutate(); }}>Delete</Button>
      </div>
      <ol className="dub-steps" aria-label="Steps">
        {DUB_STEPS.map((step) => {
          const state = stepState(data, step.id);
          return (
            <li key={step.id} className={`dub-step ${state.status.replace(' ', '-')}`}>
              <b>{step.label}</b>
              <small>{state.status}</small>
              {state.error ? <small className="dub-step-error" title={state.error}>{state.error}</small> : null}
              {step.id !== 'mux' ? (
                <span className="dub-step-actions">
                  <Button size="compact-xs" variant="subtle" disabled={ACTIVE.has(state.status)} onClick={() => run.mutate({ step: step.id })} title="Run this step again">Run</Button>
                  <Button size="compact-xs" variant="subtle" disabled={ACTIVE.has(state.status)} onClick={() => run.mutate({ step: step.id, chain: true })} title="Run this step and the ones after it, up to review">From here</Button>
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
      {run.isError ? <Text size="xs" role="alert">The step could not be queued.</Text> : null}
      <Casting project={data} onSave={(casting) => update.mutate(casting)} />
      <DubReview project={data} onChanged={(next) => queryClient.setQueryData(key, next)} onRegenerate={(lineIds) => run.mutate({ step: 'synthesize', lineIds })} onRetranslate={(lineIds) => run.mutate({ step: 'translate', lineIds })} />
      <section className="dub-export" aria-label="Export">
        <Button disabled={!allApproved || ACTIVE.has(stepState(data, 'mux').status)} loading={ACTIVE.has(stepState(data, 'mux').status)} title={allApproved ? 'Mix the dub and write the video' : 'Approve every line first'} onClick={() => run.mutate({ step: 'mux' })}>Mix and export</Button>
        {assets.video ? <a href={`/api/assets/${encodeURIComponent(assets.video)}/download`}>Dubbed video</a> : null}
        {assets.srt ? <a href={`/api/assets/${encodeURIComponent(assets.srt)}/download`}>Subtitles (SRT)</a> : null}
        {assets.vtt ? <a href={`/api/assets/${encodeURIComponent(assets.vtt)}/download`}>Subtitles (VTT)</a> : null}
      </section>
    </div>
  );
}
