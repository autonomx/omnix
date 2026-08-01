import { Button, PasswordInput, Progress, Text } from '@mantine/core';
import { useEffect, useState } from 'react';
import { OmnixStatusPill } from '../../design/primitives';

export interface ImageLocalModelStatus {
  ok?: boolean;
  exists?: boolean;
  complete?: boolean;
  missing?: string[];
  local_dir?: string;
  repo_id?: string;
  gated?: boolean;
  license?: string;
}

export interface ImageDownloadProgress {
  status: string;
  bytes_downloaded: number;
  bytes_total: number;
  percent?: number | null;
  indeterminate?: boolean;
}

export interface ImageModelRecord {
  key?: string;
  provider: string;
  label?: string;
  model: string;
  loaded: boolean;
  state: 'loaded' | 'unloaded' | 'downloading' | 'loading' | 'unloading' | string;
  downloaded?: boolean;
  supports_download?: boolean;
  supports_image_to_image?: boolean;
  repo_id?: string;
  gated?: boolean;
  license?: string;
  minimum_diffusers?: string;
  minimum_torch?: string;
  local_model?: ImageLocalModelStatus;
  download_progress?: ImageDownloadProgress;
}

export interface ImageModelStatusPayload extends ImageModelRecord {
  ok: boolean;
  service: string;
  enabled: boolean;
  explicit_load_required?: boolean;
  models?: ImageModelRecord[];
  error?: string;
}

export type ImageModelAction = {
  type: 'download' | 'load' | 'unload';
  provider: string;
} | null;

interface ImageModelControlProps {
  status?: ImageModelStatusPayload;
  selectedProvider: string;
  statusLoading: boolean;
  action: ImageModelAction;
  error?: string;
  onSelect: (provider: string) => void;
  onDownload: (provider: string, hfToken?: string) => void;
  onLoad: (provider: string) => void;
  onUnload: (provider: string) => void;
  onRefresh: () => void | Promise<unknown>;
}

const FALLBACK_MODELS: ImageModelRecord[] = [
  { provider: 'flux_klein', model: 'FLUX.2 [klein] 4B', loaded: false, state: 'unloaded', supports_download: true },
  { provider: 'krea2_turbo', model: 'Krea 2 Turbo', loaded: false, state: 'unloaded', supports_download: true, gated: true },
  { provider: 'z_image_turbo', model: 'Z-Image Turbo', loaded: false, state: 'unloaded', supports_download: true },
];

export function selectedImageModel(
  status: ImageModelStatusPayload | undefined,
  selectedProvider: string,
): ImageModelRecord | undefined {
  if (status?.provider === selectedProvider) return status;
  return status?.models?.find((model) => model.provider === selectedProvider || model.key === selectedProvider);
}

function imageModelOptions(status: ImageModelStatusPayload | undefined): ImageModelRecord[] {
  if (status?.models?.length) return status.models;
  return FALLBACK_MODELS;
}

async function responseError(response: Response): Promise<string> {
  try {
    const payload = await response.json() as { detail?: unknown; error?: unknown };
    const detail = payload.detail ?? payload.error;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (detail) return JSON.stringify(detail);
  } catch {
    // Fall through to status text when the response is not JSON.
  }
  return response.statusText || `Image service start failed (${response.status}).`;
}

function formatBytes(value: number): string {
  const bytes = Math.max(0, Number(value) || 0);
  if (bytes < 1024) return `${Math.round(bytes)} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let amount = bytes / 1024;
  let unit = units[0];
  for (let index = 1; index < units.length && amount >= 1024; index += 1) {
    amount /= 1024;
    unit = units[index];
  }
  return `${amount >= 10 ? amount.toFixed(1) : amount.toFixed(2)} ${unit}`;
}

function progressFromPayload(
  payload: ImageModelStatusPayload,
  provider: string,
): ImageDownloadProgress | undefined {
  return selectedImageModel(payload, provider)?.download_progress ?? payload.download_progress;
}

export function ImageModelControl({
  status,
  selectedProvider,
  statusLoading,
  action,
  error,
  onSelect,
  onDownload,
  onLoad,
  onUnload,
  onRefresh,
}: ImageModelControlProps) {
  const [serviceStarting, setServiceStarting] = useState(false);
  const [serviceStartError, setServiceStartError] = useState('');
  const [hfToken, setHfToken] = useState('');
  const [polledDownloadProgress, setPolledDownloadProgress] = useState<ImageDownloadProgress>();
  const selected = selectedImageModel(status, selectedProvider);
  const loaded = Boolean(selected?.loaded);
  const downloaded = selected?.local_model?.complete === true || selected?.downloaded === true;
  const selectedAction = action?.provider === selectedProvider ? action.type : null;
  const serviceUnavailable = Boolean(status && (status.error || status.state === 'unavailable'));
  const serviceReady = Boolean(status && status.enabled && !serviceUnavailable);
  const downloadProgress = polledDownloadProgress ?? selected?.download_progress ?? status?.download_progress;
  const downloading = selectedAction === 'download' || selected?.state === 'downloading';
  const state = serviceStarting
    ? 'starting service'
    : selectedAction === 'download'
      ? 'downloading'
      : selectedAction === 'load'
        ? 'loading'
        : selectedAction === 'unload'
          ? 'unloading'
          : selected?.state || 'checking';
  const busy = Boolean(action) || statusLoading || serviceStarting;
  const canDownload = Boolean(
    status?.enabled && selected?.supports_download !== false && !downloaded && !busy,
  );
  const canLoad = Boolean(status?.enabled && downloaded && !loaded && !busy);
  const canUnload = Boolean(serviceReady && loaded && !busy);
  const location = selected?.local_model?.local_dir || '';
  const missing = selected?.local_model?.missing ?? [];

  useEffect(() => {
    if (!serviceUnavailable) {
      setServiceStarting(false);
      setServiceStartError('');
    }
  }, [serviceUnavailable]);

  useEffect(() => {
    setServiceStartError('');
    setHfToken('');
  }, [selectedProvider]);

  useEffect(() => {
    if (downloaded) setHfToken('');
  }, [downloaded]);

  useEffect(() => {
    if (selectedAction !== 'download') {
      setPolledDownloadProgress(undefined);
      return;
    }

    let disposed = false;
    const poll = async () => {
      try {
        const response = await fetch(
          `/api/image-generation/model/status?provider=${encodeURIComponent(selectedProvider)}`,
        );
        if (!response.ok) return;
        const payload = await response.json() as ImageModelStatusPayload;
        const progress = progressFromPayload(payload, selectedProvider);
        if (!disposed && progress) setPolledDownloadProgress(progress);
      } catch {
        // Keep the last known progress while a transient status poll fails.
      }
    };

    void poll();
    const timer = window.setInterval(() => void poll(), 750);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [selectedAction, selectedProvider]);

  const startImageService = async (): Promise<boolean> => {
    setServiceStarting(true);
    setServiceStartError('');
    try {
      const response = await fetch('/api/image-generation/service/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: selectedProvider }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      return true;
    } catch (startError) {
      setServiceStartError(
        startError instanceof Error ? startError.message : 'Image service could not be started.',
      );
      return false;
    } finally {
      setServiceStarting(false);
    }
  };

  const downloadModel = async () => {
    if (serviceUnavailable && !(await startImageService())) return;
    onDownload(
      selectedProvider,
      selected?.gated ? hfToken.trim() || undefined : undefined,
    );
  };

  const loadModel = async () => {
    if (serviceUnavailable && !(await startImageService())) return;
    onLoad(selectedProvider);
  };

  const progressValue = downloadProgress?.indeterminate || downloadProgress?.percent == null
    ? 100
    : Math.max(0, Math.min(100, downloadProgress.percent));
  const progressLabel = downloadProgress?.bytes_total
    ? `${formatBytes(downloadProgress.bytes_downloaded)} of ${formatBytes(downloadProgress.bytes_total)} · ${progressValue.toFixed(1)}%`
    : downloadProgress?.bytes_downloaded
      ? `${formatBytes(downloadProgress.bytes_downloaded)} downloaded`
      : 'Preparing Hugging Face download…';

  return (
    <section className={`image-model-control ${loaded ? 'loaded' : 'unloaded'}`} aria-label="Image model control" aria-live="polite">
      <div className="image-model-control-copy">
        <div className="image-model-control-title-row">
          <span className="image-model-control-icon" aria-hidden="true">◈</span>
          <div>
            <label className="image-field image-model-selector">
              <span>Image model</span>
              <select
                aria-label="Image model"
                disabled={Boolean(action) || serviceStarting}
                value={selectedProvider}
                onChange={(event) => onSelect(event.currentTarget.value)}
              >
                {imageModelOptions(status).map((model) => (
                  <option key={model.provider || model.key} value={model.provider || model.key}>
                    {model.model || model.label || model.provider}
                  </option>
                ))}
              </select>
            </label>
            <Text size="xs">
              {serviceUnavailable && downloaded
                ? 'Model files are downloaded. Load will start the lightweight service automatically.'
                : serviceUnavailable
                  ? 'Model files are not downloaded. Download will start the lightweight service automatically.'
                  : loaded
                    ? 'Model weights are resident and image generation is ready.'
                    : downloaded
                      ? 'Model files are downloaded but weights are not resident. Load explicitly when needed.'
                      : 'Model files are not downloaded. Downloading does not load weights into memory.'}
            </Text>
          </div>
          <OmnixStatusPill>{state}</OmnixStatusPill>
        </div>
        {downloading ? (
          <div aria-label="Model download progress">
            <Progress
              animated
              aria-label="Model download progress bar"
              striped
              value={progressValue}
            />
            <Text mt={4} size="xs">{progressLabel}</Text>
          </div>
        ) : null}
        {location ? <Text className="image-model-path" size="xs" title={location}>{location}</Text> : null}
        {!downloaded && missing.length ? (
          <Text c="dimmed" size="xs">Missing local files: {missing.join(', ')}</Text>
        ) : null}
        {selected?.gated && !downloaded ? (
          <div>
            <PasswordInput
              autoComplete="off"
              disabled={busy}
              label="Hugging Face token"
              maxLength={512}
              onChange={(event) => setHfToken(event.currentTarget.value)}
              placeholder="hf_…"
              value={hfToken}
            />
            <Text c="dimmed" mt={4} size="xs">
              Used only for this download and not stored. Leave blank to use the launcher's HF_TOKEN.
            </Text>
            <Text c="yellow" mt={4} size="xs">
              Accept this model's Hugging Face license before downloading.
            </Text>
          </div>
        ) : null}
        {serviceStartError ? <Text c="red" size="xs" role="alert">{serviceStartError}</Text> : null}
        {error ? <Text c="red" size="xs" role="alert">{error}</Text> : null}
      </div>
      <div className="image-model-control-actions">
        {loaded ? (
          <Button
            color="red"
            loading={selectedAction === 'unload'}
            disabled={!canUnload}
            onClick={() => onUnload(selectedProvider)}
            size="compact-sm"
            variant="light"
          >
            Unload Model
          </Button>
        ) : downloaded ? (
          <Button
            loading={selectedAction === 'load' || serviceStarting}
            disabled={!canLoad}
            onClick={() => void loadModel()}
            size="compact-sm"
            variant="filled"
          >
            Load Model
          </Button>
        ) : (
          <Button
            loading={selectedAction === 'download' || serviceStarting}
            disabled={!canDownload}
            onClick={() => void downloadModel()}
            size="compact-sm"
            variant="filled"
          >
            Download Model
          </Button>
        )}
        <Button disabled={Boolean(action) || serviceStarting} loading={statusLoading} onClick={onRefresh} size="compact-sm" variant="subtle">
          Refresh Status
        </Button>
      </div>
    </section>
  );
}

export function imageModelGenerationBlockReason(
  status: ImageModelStatusPayload | undefined,
  selectedProvider: string,
  statusLoading: boolean,
  statusError: boolean,
): string | undefined {
  const selected = selectedImageModel(status, selectedProvider);
  const modelName = selected?.model || selectedProvider;
  if (statusLoading) return `Checking ${modelName} model status.`;
  if (statusError || !status) return 'The image model service is unavailable. Downloading or loading can start it automatically.';
  if (!status.enabled) return 'Image generation is disabled for this startup.';
  if (selected?.local_model?.complete !== true && selected?.downloaded !== true) return `Download ${modelName} before loading it.`;
  if (status.error || status.state === 'unavailable') return `Load ${modelName} to start the image service and make it resident.`;
  if (!selected?.loaded) return `Load ${modelName} before generating an image.`;
  return undefined;
}
