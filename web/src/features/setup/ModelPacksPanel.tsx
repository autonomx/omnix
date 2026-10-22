import { Button, Checkbox, Modal, Progress, SegmentedControl, Text } from '@mantine/core';
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import type { JobRecord } from '../../api/client';
import { ApiError } from '../../api/errors';
import { desktopBridge } from '../../shared/desktopBridge';
import {
  ASSISTANT_AVATAR_QUERY_KEY, AVATARS_QUERY_KEY, avatarsClient, CAPABILITIES_QUERY_KEY, FIRST_RUN_ASSISTANT_AVATAR,
  formatGigabytes, MODEL_PACKS_QUERY_KEY, modelPacksClient,
  type AvatarModel, type ModelPacksStatus, type PackModelStatus, type PackOption, type PackRuntimeStatus, type PackVerdict,
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

/** The shared GPU runtime downloads once, however many features use it. */
function sharedRuntimeNote(runtimes: PackRuntimeStatus[]): string {
  const shared = runtimes.find((runtime) => runtime.kind === 'torch-layer' && !runtime.current);
  return shared ? ` (${formatGigabytes(shared.download_bytes)} of it is the shared GPU runtime, downloaded once)` : '';
}

function OptionChip({ option }: { option: PackOption }) {
  if (option.installed) return <span className="setup-chip setup-chip-installed">Downloaded</span>;
  if (option.status === 'warn') return <span className="setup-chip setup-chip-warn">⚠ Check</span>;
  if (option.status === 'unavailable') return <span className="setup-chip setup-chip-unavailable">✗ Unavailable</span>;
  return null;
}

/** A bundle's optional models: chosen before its download, or added and removed one by one afterwards. */
function BundleOptions({ verdict, picked, onPick, manage, busy, onAdd, onRemove }: {
  verdict: PackVerdict;
  picked: Set<string>;
  onPick: (model: string, value: boolean) => void;
  manage: boolean;
  busy: boolean;
  onAdd: (option: PackOption) => void;
  onRemove: (option: PackOption) => void;
}) {
  if (!verdict.options.length) return null;
  const choosing = !verdict.installed;
  const installedCount = verdict.options.filter((option) => option.installed).length;
  return (
    <div className="setup-bundle-options" role="group" aria-label={`${verdict.label} choices`}>
      <Text size="xs" className="setup-muted">
        {verdict.min_options ? `Choose at least ${verdict.min_options}:` : 'Also available:'}
      </Text>
      <ul>
        {verdict.options.map((option) => {
          const label = (
            <span>
              <b>{option.label}</b> · {formatGigabytes(option.model_bytes + option.runtime_bytes || 0)} ·{' '}
              <a href={option.licence.url} target="_blank" rel="noreferrer">{option.licence.id}</a>
              {option.licence.gated ? ' · gated' : ''}
            </span>
          );
          // The last chosen option of a bundle that needs one stays chosen.
          const last = picked.has(option.model) && picked.size <= verdict.min_options;
          return (
            <li key={option.model} aria-label={option.label}>
              <div className="setup-bundle-head">
                {choosing && manage ? (
                  <Checkbox size="xs" checked={picked.has(option.model)} disabled={option.status === 'unavailable' || last}
                    onChange={(event) => onPick(option.model, event.currentTarget.checked)} label={label} />
                ) : label}
                <OptionChip option={option} />
              </div>
              {option.note ? <Text size="xs" className="setup-muted">{option.note}</Text> : null}
              {!option.licence.commercial_use ? <Text size="xs" className="setup-reason">Not for commercial use.</Text> : null}
              {option.reasons.map((reason) => <Text key={reason} size="xs" className="setup-reason">{reason}</Text>)}
              {!choosing && manage ? (
                <div className="setup-bundle-actions">
                  {option.installed
                    ? (installedCount > verdict.min_options
                      ? <Button size="compact-xs" variant="subtle" color="red" loading={busy}
                          onClick={() => { if (window.confirm(`Remove ${option.label}? It is deleted from this computer.`)) onRemove(option); }}>
                          Remove
                        </Button>
                      : null)
                    : <Button size="compact-xs" variant="light" loading={busy} disabled={option.status === 'unavailable'}
                        onClick={() => onAdd(option)}>Download</Button>}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function BundleRow({ verdict, models, runtimes, selected, onToggle, job, busy, onRemove, onVerify, onCancel, manage,
  picked, onPick, onAddOption, onRemoveOption }: {
  verdict: PackVerdict;
  /** The chosen optional models, and changing them before or after the bundle's download. */
  picked: Set<string>;
  onPick: (model: string, value: boolean) => void;
  onAddOption: (option: PackOption) => void;
  onRemoveOption: (option: PackOption) => void;
  /** The bundle's models and runtime packs, as the status lists them. */
  models: PackModelStatus[];
  runtimes: PackRuntimeStatus[];
  /** The signed-in account may download and remove models (the server enforces it either way). */
  manage: boolean;
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
  const selectable = manage && !verdict.installed && verdict.status !== 'unavailable' && !running;
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
        {models.length ? (
          <ul className="setup-bundle-models" aria-label={`${verdict.label} models`}>
            {models.map((model) => (
              <li key={model.id}>
                {model.label} · {formatGigabytes(model.size_bytes)} ·{' '}
                <a href={model.licence.url} target="_blank" rel="noreferrer">{model.licence.id}</a>
                {model.installed ? ' · downloaded' : ''}
              </li>
            ))}
          </ul>
        ) : null}
        {!verdict.installed && size > 0 ? (
          <Text size="xs" className="setup-muted">
            {formatGigabytes(verdict.model_bytes)} of models
            {verdict.runtime_bytes ? ` + ${formatGigabytes(verdict.runtime_bytes)} of runtime` : ''}
            {sharedRuntimeNote(runtimes)}
          </Text>
        ) : null}
        <BundleOptions verdict={verdict} picked={picked} onPick={onPick} manage={manage} busy={busy}
          onAdd={onAddOption} onRemove={onRemoveOption} />
        {verdict.reasons.map((reason) => <Text key={reason} size="xs" className="setup-reason">{reason}</Text>)}
        {verdict.action ? (
          <a className="setup-action-link" href={verdict.action.url} target="_blank" rel="noreferrer">{verdict.action.label}</a>
        ) : null}
        {verdict.note ? <Text size="xs" className="setup-muted">{verdict.note}</Text> : null}
        {running ? (
          <div className="setup-progress" role="status">
            <Progress value={share} size="sm" aria-label={`${verdict.label} progress`} />
            <Text size="xs">{progress?.message || 'Waiting to start'}{share ? ` · ${share.toFixed(0)}%` : ''}</Text>
            {manage ? <Button size="compact-xs" variant="subtle" onClick={onCancel}>Cancel</Button> : null}
          </div>
        ) : null}
        {job && job.status === 'failed' ? <Text size="xs" className="setup-reason" role="alert">{job.error?.message ?? 'The download failed.'}</Text> : null}
        {verdict.installed && manage ? (
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

function LicenceReview({ opened, onClose, models, runtimes, avatar = null, onConfirm, submitting }: {
  opened: boolean;
  onClose: () => void;
  models: PackModelStatus[];
  runtimes: PackRuntimeStatus[];
  /** A Live2D avatar downloaded with the models (the first-run assistant avatar). */
  avatar?: AvatarModel | null;
  onConfirm: () => void;
  submitting: boolean;
}) {
  const [accepted, setAccepted] = useState<Record<string, boolean>>({});
  useEffect(() => { if (opened) setAccepted({}); }, [opened]);
  const avatarKey = avatar ? `avatar:${avatar.id}` : '';
  const allAccepted = models.every((model) => accepted[model.id]) && (!avatar || Boolean(accepted[avatarKey]));
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
        {avatar ? (
          <li>
            <Checkbox
              checked={Boolean(accepted[avatarKey])}
              onChange={(event) => {
                const checked = event.currentTarget.checked;
                setAccepted((current) => ({ ...current, [avatarKey]: checked }));
              }}
              label={<span><b>{avatar.name}</b> (Live2D avatar) · <a href={avatar.runtime_license_url} target="_blank" rel="noreferrer">Live2D Proprietary Software License</a> · <a href={avatar.model_license_url} target="_blank" rel="noreferrer">model terms</a></span>}
            />
            <Text size="xs" className="setup-muted">{avatar.license_summary}</Text>
          </li>
        ) : null}
      </ul>
      {runtimes.length ? (
        <Text size="xs" className="setup-muted">
          Runtimes it installs (for information): {runtimes.map((runtime) => `${runtime.label} (${runtime.licences.join(', ')})`).join('; ')}.
        </Text>
      ) : null}
      <div className="setup-footer">
        <Button variant="subtle" onClick={onClose}>Back</Button>
        <Button disabled={!allAccepted} loading={submitting} onClick={onConfirm}>{models.length || avatar ? 'Accept and download' : 'Download'}</Button>
      </div>
    </Modal>
  );
}

/**
 * The first-run setup's offer of a Live2D avatar for the System Assistant, ticked by default, while the assistant has
 * none (it is changed later in Chat, Characters).
 */
function useAssistantAvatarChoice(mode: 'setup' | 'settings') {
  const avatarsQuery = useQuery({
    queryKey: ASSISTANT_AVATAR_QUERY_KEY,
    queryFn: () => avatarsClient.assistantAvatars(),
    enabled: mode === 'setup',
    retry: false,
  });
  const [chosen, setChosen] = useState(true);
  const models = avatarsQuery.data?.models ?? [];
  const offer = mode === 'setup' && !models.some((model) => model.selected)
    ? models.find((model) => model.id === FIRST_RUN_ASSISTANT_AVATAR) ?? null
    : null;
  return { offer, chosen: Boolean(offer) && chosen, setChosen };
}

function AssistantAvatarChoice({ avatar, chosen, onChange, manage }: {
  avatar: AvatarModel;
  chosen: boolean;
  onChange: (chosen: boolean) => void;
  manage: boolean;
}) {
  return (
    <section className="setup-bundle setup-assistant-avatar" aria-label="Assistant avatar">
      <img className="setup-assistant-avatar-preview" src={avatar.preview_path} alt="" />
      <div className="setup-bundle-details">
        <Checkbox
          checked={chosen}
          disabled={!manage}
          onChange={(event) => onChange(event.currentTarget.checked)}
          label={<span><b>Assistant avatar: {avatar.name}</b></span>}
        />
        <Text size="sm">A Live2D avatar for the assistant in Live Voice, with idle motion and lip sync. Change it or turn it off in Chat, Characters.</Text>
      </div>
    </section>
  );
}

/**
 * The folder downloads go to, and (in the desktop app) the folder picker that changes it: anything already downloaded
 * moves with it. Shared by the download footer and "On this computer".
 */
function usePacksFolder(status: ModelPacksStatus | undefined) {
  const bridge = desktopBridge();
  const [moved, setMoved] = useState<string | null>(null);
  const folder = moved ?? status?.packs_folder ?? '';
  const choose = bridge?.choosePacksFolder && status?.can_manage_runtimes
    ? () => { void bridge.choosePacksFolder?.().then((target) => { if (target) setMoved(target); }); }
    : null;
  return { folder, choose };
}

function InstalledPacks({ status, folder, onChooseFolder, onRemoveRuntime, onVerifyRuntime, busy }: {
  status: ModelPacksStatus;
  folder: string;
  onChooseFolder: (() => void) | null;
  onRemoveRuntime: (runtime: PackRuntimeStatus) => void;
  onVerifyRuntime: (runtime: PackRuntimeStatus) => void;
  busy: boolean;
}) {
  const installedRuntimes = status.runtimes.filter((runtime) => runtime.installed);
  const installedModels = status.models.filter((model) => model.installed);
  const disk = installedModels.reduce((total, model) => total + model.disk_bytes, 0);
  return (
    <section className="setup-installed" aria-label="Downloaded runtimes and models">
      <h3>On this computer</h3>
      <Text size="sm">{installedModels.length} models ({formatGigabytes(disk)}) and {installedRuntimes.length} runtimes in <code>{folder}</code></Text>
      {onChooseFolder ? (
        <Button size="compact-xs" variant="subtle" onClick={onChooseFolder}>
          Move to another folder…
        </Button>
      ) : null}
      {installedRuntimes.length ? (
        <ul className="setup-runtime-list">
          {installedRuntimes.map((runtime) => (
            <li key={runtime.id}>
              <span><b>{runtime.label}</b>{runtime.current ? '' : ' · an update is available: download it again'}</span>
              {status.can_manage_runtimes ? <span className="setup-bundle-actions">
                <Button size="compact-xs" variant="subtle" loading={busy} onClick={() => onVerifyRuntime(runtime)}>Verify</Button>
                <Button size="compact-xs" variant="subtle" color="red" loading={busy}
                  onClick={() => { if (window.confirm(`Remove ${runtime.label}?`)) onRemoveRuntime(runtime); }}>Remove</Button>
              </span> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

/**
 * Which downloaded models Omnix uses by default: the voice engine for spoken replies and Voice Studio, and the model
 * the image view starts with. Only models on this computer are offered.
 */
function DefaultModelsPanel({ status }: { status: ModelPacksStatus }) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState('');
  const save = useMutation({
    mutationFn: (change: { voice?: string; image?: string }) => modelPacksClient.setDefaults(change),
    onSuccess: () => {
      setMessage('Saved.');
      void queryClient.invalidateQueries({ queryKey: MODEL_PACKS_QUERY_KEY });
    },
    onError: (error) => setMessage(errorText(error)),
  });
  const slots = [
    { key: 'voice' as const, label: 'Default voice engine', slot: status.defaults.voice },
    { key: 'image' as const, label: 'Default image model', slot: status.defaults.image },
  ].filter((item) => item.slot.choices.length > 0);
  if (!slots.length) return null;
  return (
    <section className="setup-defaults" aria-label="Default models">
      <h3>Defaults</h3>
      {slots.map(({ key, label, slot }) => (
        <label key={key} className="setup-default">
          <span>{label}</span>
          <select
            aria-label={label}
            value={slot.current}
            disabled={!status.can_manage || save.isPending}
            onChange={(event) => save.mutate({ [key]: event.currentTarget.value })}
          >
            {slot.current ? null : <option value="">Choose…</option>}
            {slot.choices.map((choice) => <option key={choice.model} value={choice.model}>{choice.label}</option>)}
          </select>
        </label>
      ))}
      {message ? <Text size="xs" role="status">{message}</Text> : null}
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
  const packsFolder = usePacksFolder(status);
  const assistantAvatar = useAssistantAvatarChoice(mode);
  const queryClient = useQueryClient();
  const [preset, setPreset] = useState<Preset>('recommended');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [initialised, setInitialised] = useState(false);
  // Each bundle's chosen optional models, starting from its defaults.
  const [picked, setPicked] = useState<Record<string, Set<string>>>({});
  useEffect(() => {
    if (!status || initialised) return;
    setPicked(Object.fromEntries(bundles.map((item) => [item.bundle,
      new Set(item.options.filter((option) => option.default).map((option) => option.model))])));
    setSelected(new Set(mode === 'setup' && status.can_manage ? bundles.filter((item) => item.recommended).map((item) => item.bundle) : []));
    setPreset(mode === 'setup' ? 'recommended' : 'custom');
    setInitialised(true);
  }, [status, initialised, bundles, mode]);
  const choosePreset = (value: Preset) => {
    setPreset(value);
    if (value === 'recommended') setSelected(new Set(bundles.filter((item) => item.recommended).map((item) => item.bundle)));
    if (value === 'minimal') setSelected(new Set());
  };
  const selection = [...selected].sort();
  const chosenOptions = Object.fromEntries(selection.map((bundle) => [bundle, [...(picked[bundle] ?? [])].sort()]));
  const sizeQuery = useQuery({
    queryKey: ['setup', 'selection', selection, chosenOptions],
    queryFn: () => modelPacksClient.selection(selection, chosenOptions),
    enabled: Boolean(status?.enabled) && selection.length > 0,
  });

  const [message, setMessage] = useState('');
  const [reviewing, setReviewing] = useState(false);
  // An optional model added to a downloaded bundle: its own licence review, then its own job.
  const [adding, setAdding] = useState<{ bundle: string; option: PackOption } | null>(null);
  const installMutation = useMutation({
    mutationFn: async (bundleIds: string[]) => {
      const started: Record<string, string> = {};
      for (const bundle of bundleIds) {
        const job = await modelPacksClient.install({ bundle_id: bundle, accept_terms: true, options: chosenOptions[bundle] ?? [] });
        started[bundle] = job.id;
      }
      // The assistant's avatar is small: it downloads now, after the model jobs are queued.
      let avatarError = '';
      if (assistantAvatar.chosen && assistantAvatar.offer) {
        try {
          await avatarsClient.useForAssistant(assistantAvatar.offer.id);
        } catch (error) {
          avatarError = errorText(error);
        }
      }
      return { started, avatarError };
    },
    onSuccess: ({ started, avatarError }) => {
      track(started);
      setSelected(new Set());
      setReviewing(false);
      void queryClient.invalidateQueries({ queryKey: ASSISTANT_AVATAR_QUERY_KEY });
      void queryClient.invalidateQueries({ queryKey: AVATARS_QUERY_KEY });
      setMessage([
        Object.keys(started).length ? 'Downloading in the background: you can keep using Omnix, and this keeps going when you close it.' : '',
        avatarError ? `The assistant's avatar could not be downloaded: ${avatarError}` : '',
      ].filter(Boolean).join(' ') || 'The assistant has its avatar.');
    },
    onError: (error) => { setReviewing(false); setMessage(errorText(error)); },
  });
  const actionMutation = useMutation({
    mutationFn: async ({ kind, target }: { kind: 'add' | 'remove' | 'verify'; key?: string;
      target: { bundle_id?: string; runtime_id?: string; model_id?: string } }) => (
      kind === 'add' ? modelPacksClient.install({ ...target, accept_terms: true })
        : kind === 'remove' ? modelPacksClient.remove(target) : modelPacksClient.verify(target)
    ),
    onSuccess: (job, { kind, key, target }) => {
      track({ [key ?? target.bundle_id ?? target.runtime_id ?? job.id]: job.id });
      setAdding(null);
      setMessage(kind === 'add' ? 'Downloading in the background.' : kind === 'remove' ? 'Removing…' : 'Checking every file against its pinned digest…');
    },
    onError: (error) => { setAdding(null); setMessage(errorText(error)); },
  });

  if (statusQuery.isError) return <div className="platform-empty" role="alert">{errorText(statusQuery.error)}</div>;
  if (!status) return <div className="platform-empty" role="status">Checking what this computer can run…</div>;
  if (!status.enabled) {
    return mode === 'setup'
      ? <div className="platform-empty" role="status">Model downloads are part of the Omnix desktop app. Here, install models from Voice Studio, Models.</div>
      : null;
  }

  const chosen = bundles.filter((item) => selected.has(item.bundle));
  const optionModels = (verdict: PackVerdict) => new Set(verdict.options.map((option) => option.model));
  const requiredModels = (verdict: PackVerdict) => verdict.models.filter((id) => !optionModels(verdict).has(id));
  const chosenModelIds = new Set(chosen.flatMap((item) => [...requiredModels(item), ...(picked[item.bundle] ?? [])]));
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
      {!status.can_manage ? (
        <div className="setup-message" role="status">The workspace owner or an admin downloads and removes models on this computer.</div>
      ) : null}
      {status.can_manage ? <SegmentedControl
        value={preset}
        onChange={(value) => choosePreset(value as Preset)}
        data={[
          { label: 'Recommended for this computer', value: 'recommended' },
          { label: 'Minimal', value: 'minimal' },
          { label: 'Custom', value: 'custom' },
        ]}
        aria-label="Which models to download"
      /> : null}
      <ul className="setup-bundles">
        {bundles.map((verdict) => (
          <BundleRow
            key={verdict.bundle}
            verdict={verdict}
            models={requiredModels(verdict).map((id) => status.models.find((model) => model.id === id)).filter((model) => model !== undefined)}
            runtimes={verdict.runtimes.map((id) => status.runtimes.find((runtime) => runtime.id === id)).filter((runtime) => runtime !== undefined)}
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
            manage={status.can_manage}
            picked={picked[verdict.bundle] ?? new Set()}
            onPick={(model, value) => setPicked((current) => {
              const next = new Set(current[verdict.bundle] ?? []);
              if (value) next.add(model); else next.delete(model);
              return { ...current, [verdict.bundle]: next };
            })}
            onAddOption={(option) => setAdding({ bundle: verdict.bundle, option })}
            onRemoveOption={(option) => actionMutation.mutate({ kind: 'remove', key: `${verdict.bundle}:${option.model}`,
              target: { model_id: option.model } })}
          />
        ))}
      </ul>
      {assistantAvatar.offer ? (
        <AssistantAvatarChoice avatar={assistantAvatar.offer} chosen={assistantAvatar.chosen} onChange={assistantAvatar.setChosen}
          manage={status.can_manage} />
      ) : null}
      <DefaultModelsPanel status={status} />
      <Text size="sm" className="setup-chat-note">Chat works without any of these: add an API key in Settings, AI providers, or use a local LM Studio or llama.cpp server.</Text>
      <div className="setup-footer">
        <Text size="sm" role="status">
          {selection.length ? `Download: ${formatGigabytes(total)}` : assistantAvatar.chosen ? 'Download: the assistant avatar' : 'Nothing selected'}
          {sizeQuery.data?.runtime_bytes ? ` (${formatGigabytes(sizeQuery.data.runtime_bytes)} of it runtimes, shared by every model)` : ''}
        </Text>
        {status.can_manage ? <Button disabled={(!selection.length && !assistantAvatar.chosen) || installMutation.isPending} onClick={() => setReviewing(true)}>Review licences and download</Button> : null}
      </div>
      {packsFolder.folder ? (
        <div className="setup-download-folder">
          <Text size="sm">Downloads go to <code>{packsFolder.folder}</code></Text>
          {packsFolder.choose ? <Button size="compact-xs" variant="subtle" onClick={packsFolder.choose}>Change…</Button> : null}
        </div>
      ) : null}
      {message ? <div className="setup-message" role="status">{message}</div> : null}
      {lastVerification ? <div className="setup-message" role="status">{String(lastVerification.logs?.at(-1)?.content ?? 'Verified.')}</div> : null}
      <InstalledPacks
        status={status}
        folder={packsFolder.folder}
        onChooseFolder={packsFolder.choose}
        busy={actionMutation.isPending}
        onRemoveRuntime={(runtime) => actionMutation.mutate({ kind: 'remove', target: { runtime_id: runtime.id } })}
        onVerifyRuntime={(runtime) => actionMutation.mutate({ kind: 'verify', target: { runtime_id: runtime.id } })}
      />
      <LicenceReview
        opened={reviewing}
        onClose={() => setReviewing(false)}
        models={reviewModels}
        runtimes={reviewRuntimes}
        avatar={assistantAvatar.chosen ? assistantAvatar.offer : null}
        submitting={installMutation.isPending}
        onConfirm={() => installMutation.mutate(selection)}
      />
      <LicenceReview
        opened={adding !== null}
        onClose={() => setAdding(null)}
        models={adding ? status.models.filter((model) => model.id === adding.option.model && !model.installed) : []}
        runtimes={[]}
        submitting={actionMutation.isPending}
        onConfirm={() => {
          if (adding) actionMutation.mutate({ kind: 'add', key: `${adding.bundle}:${adding.option.model}`, target: { model_id: adding.option.model } });
        }}
      />
    </section>
  );
}
