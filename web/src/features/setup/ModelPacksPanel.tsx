import { Button, Checkbox, Modal, Progress, SegmentedControl, Text } from '@mantine/core';
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import type { JobRecord } from '../../api/client';
import { ApiError } from '../../api/errors';
import { desktopBridge } from '../../shared/desktopBridge';
import {
  CAPABILITIES_QUERY_KEY, formatGigabytes, MODEL_PACKS_QUERY_KEY, modelPacksClient,
  type ModelPacksStatus, type PackModelStatus, type PackRuntimeStatus, type PackVerdict,
} from './api/modelPacksClient';
import './setup.css';

type Preset = 'recommended' | 'minimal' | 'custom';
const ACTIVE_JOB = new Set(['queued', 'leased', 'running', 'waiting', 'retrying', 'cancel_requested']);

function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.detail || error.message;
  return error instanceof Error ? error.message : String(error);
}

function StatusChip({ verdict }: { verdict: PackVerdict }) {
  if (verdict.installed) return <span className="setup-chip setup-chip-installed">Installed</span>;
  if (verdict.status === 'fits') return <span className="setup-chip setup-chip-fits">✓ Fits</span>;
  if (verdict.status === 'warn') return <span className="setup-chip setup-chip-warn">⚠ Check</span>;
  return <span className="setup-chip setup-chip-unavailable">✗ Unavailable</span>;
}

function HardwareSummary({ status }: { status: ModelPacksStatus }) {
  const hardware = status.hardware as {
    gpus?: { name: string; vram_total_mb: number; vram_free_mb: number }[]; nvidia_driver?: string; apple_silicon?: boolean;
    chip?: string; memory?: { total_bytes?: number | null }; disk?: { free_bytes?: number | null };
  };
  const parts: string[] = [];
  const gpu = hardware.gpus?.[0];
  if (gpu) parts.push(`${gpu.name} · ${(gpu.vram_total_mb / 1024).toFixed(0)} GB VRAM`);
  else if (hardware.apple_silicon) parts.push(hardware.chip || 'Apple Silicon');
  else parts.push('No NVIDIA GPU found');
  if (hardware.nvidia_driver) parts.push(`driver ${hardware.nvidia_driver}`);
  if (hardware.memory?.total_bytes) parts.push(`${(hardware.memory.total_bytes / 2 ** 30).toFixed(0)} GB RAM`);
  if (hardware.disk?.free_bytes) parts.push(`${formatGigabytes(hardware.disk.free_bytes)} free`);
  return <p className="setup-hardware" role="status">{parts.join(' · ')}</p>;
}

function BundleRow({ verdict, selected, onToggle, job, busy, onRemove, onVerify, onCancel }: {
  verdict: PackVerdict;
  selected: boolean;
  onToggle: (value: boolean) => void;
  job: JobRecord | undefined;
  busy: boolean;
  onRemove: () => void;
  onVerify: () => void;
  onCancel: () => void;
}) {
  const running = job && ACTIVE_JOB.has(job.status);
  const progress = job?.progress;
  const share = progress && progress.total ? Math.min(100, (Number(progress.current) / progress.total) * 100) : 0;
  const size = verdict.model_bytes + verdict.runtime_bytes;
  const selectable = !verdict.installed && verdict.status !== 'unavailable' && !running;
  return (
    <li className={`setup-bundle setup-bundle-${verdict.status}`} aria-label={verdict.label}>
      <div className="setup-bundle-head">
        <Checkbox
          checked={selected}
          disabled={!selectable}
          onChange={(event) => onToggle(event.currentTarget.checked)}
          label={<b>{verdict.label}</b>}
          aria-describedby={`setup-bundle-${verdict.bundle}-details`}
        />
        <StatusChip verdict={verdict} />
      </div>
      <div id={`setup-bundle-${verdict.bundle}-details`} className="setup-bundle-details">
        <Text size="sm">{verdict.description}</Text>
        {!verdict.installed && size > 0 ? (
          <Text size="xs" className="setup-muted">
            {formatGigabytes(verdict.model_bytes)} of models
            {verdict.runtime_bytes ? ` + ${formatGigabytes(verdict.runtime_bytes)} of runtime` : ''}
          </Text>
        ) : null}
        {verdict.reasons.map((reason) => <Text key={reason} size="xs" className="setup-reason">{reason}</Text>)}
        {verdict.action ? (
          <a className="setup-action-link" href={verdict.action.url} target="_blank" rel="noreferrer">{verdict.action.label}</a>
        ) : null}
        {verdict.note ? <Text size="xs" className="setup-muted">{verdict.note}</Text> : null}
        {running ? (
          <div className="setup-progress" role="status">
            <Progress value={share} size="sm" aria-label={`${verdict.label} progress`} />
            <Text size="xs">{progress?.message || 'Waiting to start'}{share ? ` · ${share.toFixed(0)}%` : ''}</Text>
            <Button size="compact-xs" variant="subtle" onClick={onCancel}>Cancel</Button>
          </div>
        ) : null}
        {job && job.status === 'failed' ? <Text size="xs" className="setup-reason" role="alert">{job.error?.message ?? 'The download failed.'}</Text> : null}
        {verdict.installed ? (
          <div className="setup-bundle-actions">
            <Button size="compact-xs" variant="subtle" loading={busy} onClick={onVerify}>Verify files</Button>
            <Button size="compact-xs" variant="subtle" color="red" loading={busy}
              onClick={() => { if (window.confirm(`Remove ${verdict.label}? Its models are deleted from this computer.`)) onRemove(); }}>
              Remove
            </Button>
          </div>
        ) : null}
      </div>
    </li>
  );
}

function LicenceReview({ opened, onClose, models, runtimes, onConfirm, submitting }: {
  opened: boolean;
  onClose: () => void;
  models: PackModelStatus[];
  runtimes: PackRuntimeStatus[];
  onConfirm: () => void;
  submitting: boolean;
}) {
  const [accepted, setAccepted] = useState<Record<string, boolean>>({});
  useEffect(() => { if (opened) setAccepted({}); }, [opened]);
  const allAccepted = models.every((model) => accepted[model.id]);
  return (
    <Modal opened={opened} onClose={onClose} title="Review the licences" size="lg" centered>
      <Text size="sm">Each model comes with its own licence. Omnix downloads it from Hugging Face at the exact version listed, and records that you accepted it.</Text>
      <ul className="setup-licences">
        {models.map((model) => (
          <li key={model.id}>
            <Checkbox
              checked={Boolean(accepted[model.id])}
              onChange={(event) => {
                const checked = event.currentTarget.checked;
                setAccepted((current) => ({ ...current, [model.id]: checked }));
              }}
              label={<span><b>{model.label}</b> · <a href={model.licence.url} target="_blank" rel="noreferrer">{model.licence.id}</a> · {formatGigabytes(model.size_bytes)}</span>}
            />
            {model.licence.output_terms ? <Text size="xs" className="setup-muted">{model.licence.output_terms}</Text> : null}
            {!model.licence.commercial_use ? <Text size="xs" className="setup-reason">Not for commercial use.</Text> : null}
            {model.licence.gated ? <Text size="xs" className="setup-reason">Gated: accept it on its Hugging Face page and add your Hugging Face token in Voice Studio, Models.</Text> : null}
          </li>
        ))}
      </ul>
      {runtimes.length ? (
        <Text size="xs" className="setup-muted">
          Runtimes it installs (for information): {runtimes.map((runtime) => `${runtime.label} (${runtime.licences.join(', ')})`).join('; ')}.
        </Text>
      ) : null}
      <div className="setup-footer">
        <Button variant="subtle" onClick={onClose}>Back</Button>
        <Button disabled={!allAccepted} loading={submitting} onClick={onConfirm}>{models.length ? 'Accept and download' : 'Download'}</Button>
      </div>
    </Modal>
  );
}

function InstalledPacks({ status, onRemoveRuntime, onVerifyRuntime, busy }: {
  status: ModelPacksStatus;
  onRemoveRuntime: (runtime: PackRuntimeStatus) => void;
  onVerifyRuntime: (runtime: PackRuntimeStatus) => void;
  busy: boolean;
}) {
  const bridge = desktopBridge();
  const [folder, setFolder] = useState(status.packs_folder);
  const installedRuntimes = status.runtimes.filter((runtime) => runtime.installed);
  const installedModels = status.models.filter((model) => model.installed);
  const disk = installedModels.reduce((total, model) => total + model.disk_bytes, 0);
  return (
    <section className="setup-installed" aria-label="Downloaded runtimes and models">
      <h3>On this computer</h3>
      <Text size="sm">{installedModels.length} models ({formatGigabytes(disk)}) and {installedRuntimes.length} runtimes in <code>{folder}</code></Text>
      {bridge?.choosePacksFolder ? (
        <Button size="compact-xs" variant="subtle" onClick={() => { void bridge.choosePacksFolder?.().then((moved) => { if (moved) setFolder(moved); }); }}>
          Move to another folder…
        </Button>
      ) : null}
      {installedRuntimes.length ? (
        <ul className="setup-runtime-list">
          {installedRuntimes.map((runtime) => (
            <li key={runtime.id}>
              <span><b>{runtime.label}</b>{runtime.current ? '' : ' · an update is available: download it again'}</span>
              <span className="setup-bundle-actions">
                <Button size="compact-xs" variant="subtle" loading={busy} onClick={() => onVerifyRuntime(runtime)}>Verify</Button>
                <Button size="compact-xs" variant="subtle" color="red" loading={busy}
                  onClick={() => { if (window.confirm(`Remove ${runtime.label}?`)) onRemoveRuntime(runtime); }}>Remove</Button>
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

/** The install, removal and check jobs this screen started, by bundle (or runtime), polled until they finish. */
function usePackJobs() {
  const queryClient = useQueryClient();
  const [jobs, setJobs] = useState<Record<string, string>>({});
  const jobQueries = useQueries({
    queries: Object.values(jobs).map((jobId) => ({
      queryKey: ['setup', 'job', jobId],
      queryFn: () => modelPacksClient.job(jobId),
      refetchInterval: (query: { state: { data?: JobRecord } }) => (query.state.data && !ACTIVE_JOB.has(query.state.data.status) ? false : 1500),
    })),
  });
  const jobByBundle = useMemo(() => Object.fromEntries(Object.keys(jobs).map((bundle, index) => [bundle, jobQueries[index]?.data])),
    [jobs, jobQueries]);
  const finishedCount = jobQueries.filter((query) => query.data && !ACTIVE_JOB.has(query.data.status)).length;
  useEffect(() => {
    if (!finishedCount) return;
    // A finished download: the packs changed, so ask the shell to start (or stop) the model services now.
    void queryClient.invalidateQueries({ queryKey: MODEL_PACKS_QUERY_KEY });
    void queryClient.invalidateQueries({ queryKey: CAPABILITIES_QUERY_KEY });
    void desktopBridge()?.refreshServices?.();
  }, [finishedCount, queryClient]);
  const track = (started: Record<string, string>) => setJobs((current) => ({ ...current, ...started }));
  return { jobs, jobByBundle, track, active: Object.keys(jobs).length - finishedCount > 0 };
}

/**
 * What this computer can run, and downloading it (desktop roadmap §4.5): the setup screen on the first start, and
 * Settings, Models afterwards. Bundles a computer cannot run stay visible with the reason. Downloads run as jobs, keep
 * going when the screen closes, and the shell starts each model service once its packs are in place.
 */
export function ModelPacksPanel({ mode }: { mode: 'setup' | 'settings' }) {
  const { jobs, jobByBundle, track, active } = usePackJobs();
  const statusQuery = useQuery({
    queryKey: MODEL_PACKS_QUERY_KEY,
    queryFn: () => modelPacksClient.status(),
    retry: false,
    refetchInterval: active ? 5000 : false,
  });
  const status = statusQuery.data;
  const bundles = useMemo(() => status?.bundles ?? [], [status]);
  const [preset, setPreset] = useState<Preset>('recommended');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [initialised, setInitialised] = useState(false);
  useEffect(() => {
    if (!status || initialised) return;
    setSelected(new Set(mode === 'setup' ? bundles.filter((item) => item.recommended).map((item) => item.bundle) : []));
    setPreset(mode === 'setup' ? 'recommended' : 'custom');
    setInitialised(true);
  }, [status, initialised, bundles, mode]);
  const choosePreset = (value: Preset) => {
    setPreset(value);
    if (value === 'recommended') setSelected(new Set(bundles.filter((item) => item.recommended).map((item) => item.bundle)));
    if (value === 'minimal') setSelected(new Set());
  };
  const selection = [...selected].sort();
  const sizeQuery = useQuery({
    queryKey: ['setup', 'selection', selection],
    queryFn: () => modelPacksClient.selection(selection),
    enabled: Boolean(status?.enabled) && selection.length > 0,
  });

  const [message, setMessage] = useState('');
  const [reviewing, setReviewing] = useState(false);
  const installMutation = useMutation({
    mutationFn: async (bundleIds: string[]) => {
      const started: Record<string, string> = {};
      for (const bundle of bundleIds) {
        const job = await modelPacksClient.install({ bundle_id: bundle, accept_terms: true });
        started[bundle] = job.id;
      }
      return started;
    },
    onSuccess: (started) => {
      track(started);
      setSelected(new Set());
      setReviewing(false);
      setMessage('Downloading in the background: you can keep using Omnix, and this keeps going when you close it.');
    },
    onError: (error) => { setReviewing(false); setMessage(errorText(error)); },
  });
  const actionMutation = useMutation({
    mutationFn: async ({ kind, target }: { kind: 'remove' | 'verify'; target: { bundle_id?: string; runtime_id?: string } }) => (
      kind === 'remove' ? modelPacksClient.remove(target) : modelPacksClient.verify(target)
    ),
    onSuccess: (job, { kind, target }) => {
      track({ [target.bundle_id ?? target.runtime_id ?? job.id]: job.id });
      setMessage(kind === 'remove' ? 'Removing…' : 'Checking every file against its pinned digest…');
    },
    onError: (error) => setMessage(errorText(error)),
  });

  if (statusQuery.isError) return <div className="platform-empty" role="alert">{errorText(statusQuery.error)}</div>;
  if (!status) return <div className="platform-empty" role="status">Checking what this computer can run…</div>;
  if (!status.enabled) {
    return mode === 'setup'
      ? <div className="platform-empty" role="status">Model downloads are part of the Omnix desktop app. Here, install models from Voice Studio, Models.</div>
      : null;
  }

  const chosen = bundles.filter((item) => selected.has(item.bundle));
  const chosenModelIds = new Set(chosen.flatMap((item) => item.models));
  const chosenRuntimeIds = new Set(chosen.flatMap((item) => item.runtimes));
  const reviewModels = status.models.filter((model) => chosenModelIds.has(model.id) && !model.installed);
  const reviewRuntimes = status.runtimes.filter((runtime) => chosenRuntimeIds.has(runtime.id) && !runtime.current);
  const total = sizeQuery.data?.total_bytes ?? 0;
  const lastVerification = Object.values(jobByBundle).find((job) => job?.type === 'models.verify' && job.status === 'completed');

  return (
    <section className="setup-panel" aria-label="AI models for this computer">
      {mode === 'settings' ? (
        <header>
          <h2 className="setup-settings-title">AI models on this computer</h2>
          <Text size="sm">Download, check or remove the runtimes and models voice, transcription and images use.</Text>
        </header>
      ) : null}
      <HardwareSummary status={status} />
      <SegmentedControl
        value={preset}
        onChange={(value) => choosePreset(value as Preset)}
        data={[
          { label: 'Recommended for this computer', value: 'recommended' },
          { label: 'Minimal', value: 'minimal' },
          { label: 'Custom', value: 'custom' },
        ]}
        aria-label="Which models to download"
      />
      <ul className="setup-bundles">
        {bundles.map((verdict) => (
          <BundleRow
            key={verdict.bundle}
            verdict={verdict}
            selected={selected.has(verdict.bundle)}
            onToggle={(value) => {
              setPreset('custom');
              setSelected((current) => {
                const next = new Set(current);
                if (value) next.add(verdict.bundle); else next.delete(verdict.bundle);
                return next;
              });
            }}
            job={jobByBundle[verdict.bundle]}
            busy={actionMutation.isPending}
            onRemove={() => actionMutation.mutate({ kind: 'remove', target: { bundle_id: verdict.bundle } })}
            onVerify={() => actionMutation.mutate({ kind: 'verify', target: { bundle_id: verdict.bundle } })}
            onCancel={() => { const jobId = jobs[verdict.bundle]; if (jobId) void modelPacksClient.cancel(jobId); }}
          />
        ))}
      </ul>
      <Text size="sm" className="setup-chat-note">Chat works without any of these: add an API key in Settings, AI providers, or use a local LM Studio or llama.cpp server.</Text>
      <div className="setup-footer">
        <Text size="sm" role="status">
          {selection.length ? `Download: ${formatGigabytes(total)}` : 'Nothing selected'}
          {sizeQuery.data?.runtime_bytes ? ` (${formatGigabytes(sizeQuery.data.runtime_bytes)} of it runtimes, shared by every model)` : ''}
        </Text>
        <Button disabled={!selection.length || installMutation.isPending} onClick={() => setReviewing(true)}>Review licences and download</Button>
      </div>
      {message ? <div className="setup-message" role="status">{message}</div> : null}
      {lastVerification ? <div className="setup-message" role="status">{String(lastVerification.logs?.at(-1)?.content ?? 'Verified.')}</div> : null}
      <InstalledPacks
        status={status}
        busy={actionMutation.isPending}
        onRemoveRuntime={(runtime) => actionMutation.mutate({ kind: 'remove', target: { runtime_id: runtime.id } })}
        onVerifyRuntime={(runtime) => actionMutation.mutate({ kind: 'verify', target: { runtime_id: runtime.id } })}
      />
      <LicenceReview
        opened={reviewing}
        onClose={() => setReviewing(false)}
        models={reviewModels}
        runtimes={reviewRuntimes}
        submitting={installMutation.isPending}
        onConfirm={() => installMutation.mutate(selection)}
      />
    </section>
  );
}
