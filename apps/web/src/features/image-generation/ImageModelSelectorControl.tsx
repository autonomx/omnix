import { Button, Text } from '@mantine/core';
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
  onDownload: (provider: string) => void;
  onLoad: (provider: string) => void;
  onUnload: (provider: string) => void;
  onRefresh: () => void;
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
  const selected = selectedImageModel(status, selectedProvider);
  const loaded = Boolean(selected?.loaded);
  const downloaded = selected?.local_model?.complete === true || selected?.downloaded === true;
  const selectedAction = action?.provider === selectedProvider ? action.type : null;
  const state = selectedAction === 'download'
    ? 'downloading'
    : selectedAction === 'load'
      ? 'loading'
      : selectedAction === 'unload'
        ? 'unloading'
        : selected?.state || 'checking';
  const busy = Boolean(action) || statusLoading;
  const serviceReady = Boolean(status && status.enabled && !status.error && status.state !== 'unavailable');
  const canDownload = Boolean(serviceReady && selected?.supports_download !== false && !downloaded && !busy);
  const canLoad = Boolean(serviceReady && downloaded && !loaded && !busy);
  const canUnload = Boolean(serviceReady && loaded && !busy);
  const location = selected?.local_model?.local_dir || '';
  const missing = selected?.local_model?.missing ?? [];

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
                disabled={Boolean(action)}
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
              {loaded
                ? 'Model weights are resident and image generation is ready.'
                : downloaded
                  ? 'Model files are downloaded but weights are not resident. Load explicitly when needed.'
                  : 'Model files are not downloaded. Downloading does not load weights into memory.'}
            </Text>
          </div>
          <OmnixStatusPill>{state}</OmnixStatusPill>
        </div>
        {location ? <Text className="image-model-path" size="xs" title={location}>{location}</Text> : null}
        {!downloaded && missing.length ? (
          <Text c="dimmed" size="xs">Missing local files: {missing.join(', ')}</Text>
        ) : null}
        {selected?.gated ? (
          <Text c="yellow" size="xs">
            This gated model requires accepting its Hugging Face license and setting HF_TOKEN before download.
          </Text>
        ) : null}
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
            loading={selectedAction === 'load'}
            disabled={!canLoad}
            onClick={() => onLoad(selectedProvider)}
            size="compact-sm"
            variant="filled"
          >
            Load Model
          </Button>
        ) : (
          <Button
            loading={selectedAction === 'download'}
            disabled={!canDownload}
            onClick={() => onDownload(selectedProvider)}
            size="compact-sm"
            variant="filled"
          >
            Download Model
          </Button>
        )}
        <Button disabled={Boolean(action)} loading={statusLoading} onClick={onRefresh} size="compact-sm" variant="subtle">
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
  const modelName = selected?.model || selected?.label || selectedProvider;
  if (statusLoading) return `Checking ${modelName} model status.`;
  if (statusError || !status) return 'The image model service is unavailable. Check the launcher and refresh status.';
  if (status.error || status.state === 'unavailable') return 'The image model service is unavailable. Check the launcher and refresh status.';
  if (!status.enabled) return 'Image generation is disabled for this startup.';
  if (selected?.local_model?.complete !== true && selected?.downloaded !== true) return `Download ${modelName} before loading it.`;
  if (!selected?.loaded) return `Load ${modelName} before generating an image.`;
  return undefined;
}
