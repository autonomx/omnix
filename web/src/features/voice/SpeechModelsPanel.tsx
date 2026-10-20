import { Button, Text } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { omnixApiClient } from '../../api/client';
import { voiceApiClient, type SpeechModelListResponse, type SpeechModelStatus } from './api/voiceClient';

export const MODELS_QUERY_KEY = ['voice', 'speech-models'] as const;

type ModelAction = 'install' | 'update' | 'remove';

function gigabytes(bytes: number): string {
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

const CAPABILITY_LABELS: Record<string, string> = {
  synthesis: 'speech', voice_clone: 'cloning', voice_design: 'voice design', many_languages: '600+ languages',
  transcription: 'transcription', word_timestamps: 'word timing', diarization: 'speakers', speaker_embedding: 'speakers',
  separation: 'vocal isolation', enhancement: 'noise cleanup', watermark: 'watermarks',
};

function HardwareReport({ data }: { data: SpeechModelListResponse }) {
  const hardware = data.hardware as { device?: string; vram_total_bytes?: number; vram_free_bytes?: number; unified_memory?: boolean };
  if (!hardware?.device) return <Text size="xs">GPU: the TTS service is not reporting one right now.</Text>;
  const total = hardware.vram_total_bytes ?? 0;
  const free = hardware.vram_free_bytes ?? 0;
  // Apple Silicon shares memory with the CPU: the total is what Metal recommends for the GPU.
  const memory = hardware.unified_memory ? 'unified memory for the GPU' : 'VRAM';
  return (
    <Text size="xs" className="voice-hardware" role="status">
      {hardware.device} · {gigabytes(total)} {memory}, {gigabytes(free)} free now · planned for {data.vram_target_gb} GB: one engine at a time, helpers beside it.
    </Text>
  );
}

function ModelRow({ model, target, accepted, onAccept, busy, onAction }: {
  model: SpeechModelStatus;
  target: number;
  accepted: boolean;
  onAccept: (value: boolean) => void;
  busy: boolean;
  onAction: (action: ModelAction) => void;
}) {
  const installed = model.status === 'installed' || model.status === 'present';
  const environment = model.environment as { name?: string; ready?: boolean; setup?: string };
  const environmentMissing = environment?.ready === false;
  const fromHub = model.source === 'huggingface';
  const termsNeeded = model.requires_acceptance && !model.accepted_terms;
  return (
    <li className="voice-model-row">
      <div>
        <b>{model.label}</b>
        <small>
          <a href={model.licence_url} target="_blank" rel="noreferrer">{model.licence}</a>
          {' · '}{model.size_gb.toFixed(1)} GB download
          {model.disk_bytes ? ` · ${gigabytes(model.disk_bytes)} on disk` : ''}
          {model.installed_revision ? ` · revision ${model.installed_revision.slice(0, 8)}` : ''}
        </small>
        <div className="voice-model-vram" title={`About ${model.vram_gb.toFixed(1)} GB of the ${target} GB target`}>
          <span style={{ width: `${Math.min(100, (model.vram_gb / target) * 100)}%` }} />
          <small>~{model.vram_gb.toFixed(1)} GB VRAM ({model.residency === 'helper' ? 'beside the engine' : model.residency === 'swap' ? 'swapped in for its tool' : 'as the engine'})</small>
        </div>
        <div className="voice-model-capabilities">
          {model.capabilities.map((capability) => <span key={capability} className="voice-tag">{CAPABILITY_LABELS[capability] ?? capability}</span>)}
        </div>
        {model.output_terms ? <small>{model.output_terms}</small> : null}
        {environmentMissing ? (
          <div className="voice-model-setup">
            <small>Its environment ({environment.name}) is not set up. Run:</small>
            <code>{environment.setup || `create the ${environment.name} environment`}</code>
          </div>
        ) : null}
      </div>
      <span className={installed ? 'ready-chip' : 'voice-tag'}>{model.status === 'package' ? 'fetched on first use' : model.status}</span>
      <div className="voice-model-actions">
        {fromHub && termsNeeded && !installed ? (
          <label className="voice-favourites-only"><input type="checkbox" checked={accepted} onChange={(event) => onAccept(event.currentTarget.checked)} />Accept {model.commercial_use ? 'terms' : 'non-commercial terms'}</label>
        ) : null}
        {fromHub && !installed && !environmentMissing ? (
          <Button size="compact-xs" variant="light" disabled={termsNeeded && !accepted} loading={busy} onClick={() => onAction('install')}>Install</Button>
        ) : null}
        {fromHub && installed ? (
          <>
            <Button size="compact-xs" variant="subtle" loading={busy} title="Fetch the newest commit of its revision" onClick={() => onAction('update')}>Update</Button>
            <Button size="compact-xs" variant="subtle" color="red" onClick={() => { if (window.confirm(`Remove ${model.label}'s weights from disk?`)) onAction('remove'); }}>Remove</Button>
          </>
        ) : null}
      </div>
    </li>
  );
}

/**
 * The Models tool: each speech model's licence, download and disk size, VRAM against the 24 GB
 * target, installed revision and what it unlocks; install, update or remove (workspace admins;
 * the server checks). Environments come from each service's lock file; a missing one shows
 * its setup command instead of an install button.
 */
export function SpeechModelsPanel() {
  const queryClient = useQueryClient();
  const modelsQuery = useQuery({ queryKey: MODELS_QUERY_KEY, queryFn: () => voiceApiClient.listSpeechModels(), retry: false });
  const [accepted, setAccepted] = useState<Record<string, boolean>>({});
  const [token, setToken] = useState('');
  const [message, setMessage] = useState('');

  const jobMutation = useMutation({
    mutationFn: ({ model, action }: { model: SpeechModelStatus; action: ModelAction }) => omnixApiClient.createJob({
      module: 'voice',
      type: action === 'remove' ? 'models.remove' : 'models.install',
      resource_class: 'cpu',
      priority: 0,
      input_payload: { model_id: model.id, ...(action === 'remove' ? {} : { accept_terms: Boolean(accepted[model.id] || model.accepted_terms) }) },
      stages: [{ id: action, label: `${action === 'install' ? 'Install' : action === 'update' ? 'Update' : 'Remove'} ${model.label}`, resource_class: 'cpu', status: 'queued' }],
    }),
    onSuccess: async (job, { model, action }) => {
      const verb = action === 'install' ? 'Installing' : action === 'update' ? 'Updating' : 'Removing';
      setMessage(job.status === 'failed' ? `${model.label}: ${job.error?.message ?? 'the job failed'}` : `${verb} ${model.label}; it shows here when the job finishes.`);
      await queryClient.invalidateQueries({ queryKey: MODELS_QUERY_KEY });
      await queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] });
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : 'The model job could not be queued.'),
  });

  const tokenMutation = useMutation({
    mutationFn: () => voiceApiClient.saveHubToken(token),
    onSuccess: (data) => {
      queryClient.setQueryData(MODELS_QUERY_KEY, data);
      setToken('');
      setMessage(data.hub_token_source === 'missing' ? 'Hugging Face token cleared.' : 'Hugging Face token saved.');
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : 'The token could not be saved.'),
  });

  if (modelsQuery.isError) return <div className="platform-empty" role="alert">The model list could not be loaded.</div>;
  const data = modelsQuery.data;
  return (
    <section className="voice-models" aria-label="Speech models">
      <div className="voice-section-head"><div><h3>Models</h3><Text size="sm">Weights for every voice engine and tool, with their licences.</Text></div></div>
      {data ? (
        <>
          <HardwareReport data={data} />
          <ul className="voice-model-list">
            {data.models.map((model) => (
              <ModelRow
                key={model.id}
                model={model}
                target={data.vram_target_gb}
                accepted={Boolean(accepted[model.id])}
                onAccept={(value) => setAccepted((current) => ({ ...current, [model.id]: value }))}
                busy={jobMutation.isPending && jobMutation.variables?.model.id === model.id}
                onAction={(action) => jobMutation.mutate({ model, action })}
              />
            ))}
          </ul>
          <div className="voice-hub-token">
            <label>Hugging Face token<input type="password" autoComplete="off" aria-label="Hugging Face token" value={token} placeholder={data.hub_token_source === 'missing' ? 'Needed for gated models' : data.hub_token_source === 'environment' ? 'Set by the environment' : 'Saved; type to replace'} disabled={data.hub_token_source === 'environment'} onChange={(event) => setToken(event.currentTarget.value)} /></label>
            <Button size="compact-xs" variant="subtle" disabled={data.hub_token_source === 'environment'} loading={tokenMutation.isPending} onClick={() => tokenMutation.mutate()}>{token ? 'Save token' : 'Clear token'}</Button>
          </div>
        </>
      ) : <div className="platform-empty" role="status">Loading speech models…</div>}
      {message ? <div className="voice-success-note" role="status">{message}</div> : null}
    </section>
  );
}
