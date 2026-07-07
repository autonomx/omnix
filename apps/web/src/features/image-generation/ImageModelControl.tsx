import { Button, Text } from '@mantine/core';
import { OmnixStatusPill } from '../../design/primitives';

export interface ImageModelStatusPayload {
  ok: boolean;
  service: string;
  enabled: boolean;
  provider: string;
  model: string;
  loaded: boolean;
  state: 'loaded' | 'unloaded' | 'loading' | 'warming' | 'unloading' | string;
  warmed_up?: boolean;
  warmup_state?: string;
  warmup_error?: string;
  warmup_duration_ms?: number | null;
  explicit_load_required?: boolean;
  local_model?: {
    ok?: boolean;
    exists?: boolean;
    complete?: boolean;
    missing?: string[];
    local_dir?: string;
  };
  error?: string;
}

interface ImageModelControlProps {
  status?: ImageModelStatusPayload;
  statusLoading: boolean;
  action: 'load' | 'unload' | null;
  error?: string;
  onLoad: () => void;
  onUnload: () => void;
  onRefresh: () => void;
}

function modelDescription(status: ImageModelStatusPayload | undefined, loaded: boolean): string {
  if (status?.state === 'warming') return 'Model weights are resident. Running a representative warmup before generation is enabled.';
  if (loaded && status?.warmup_state === 'failed') return 'Model weights are resident, but warmup failed. The first generated image may be slower.';
  if (loaded && status?.warmed_up) return 'Model weights are resident and warmed. Image generation is ready.';
  if (loaded) return 'Model weights are resident and image generation is ready.';
  return 'Model weights are not resident. Load and warm them only when image generation is needed.';
}

export function ImageModelControl({
  status,
  statusLoading,
  action,
  error,
  onLoad,
  onUnload,
  onRefresh,
}: ImageModelControlProps) {
  const loaded = Boolean(status?.loaded);
  const modelName = status?.model || 'FLUX.2 [klein] 4B';
  const localComplete = status?.local_model?.complete !== false;
  const state = action === 'load' ? 'loading' : action === 'unload' ? 'unloading' : status?.state || 'checking';
  const busy = state === 'loading' || state === 'warming' || state === 'unloading';
  const canLoad = Boolean(status && status.enabled && localComplete && !loaded && !action && !statusLoading && !busy);
  const canUnload = Boolean(status && loaded && !action && !statusLoading && !busy);
  const location = status?.local_model?.local_dir || '';
  const missing = status?.local_model?.missing ?? [];
  const warmupError = status?.warmup_error || '';

  return (
    <section className={`image-model-control ${loaded ? 'loaded' : 'unloaded'}`} aria-label="Image model control" aria-live="polite">
      <div className="image-model-control-copy">
        <div className="image-model-control-title-row">
          <span className="image-model-control-icon" aria-hidden="true">◈</span>
          <div>
            <strong>{modelName}</strong>
            <Text size="xs">{modelDescription(status, loaded)}</Text>
          </div>
          <OmnixStatusPill>{state}</OmnixStatusPill>
        </div>
        {location ? <Text className="image-model-path" size="xs" title={location}>{location}</Text> : null}
        {!localComplete ? (
          <Text c="red" size="xs" role="alert">
            Local model files are incomplete{missing.length ? `: ${missing.join(', ')}` : '.'}
          </Text>
        ) : null}
        {warmupError ? <Text c="yellow" size="xs" role="alert">Warmup warning: {warmupError}</Text> : null}
        {error ? <Text c="red" size="xs" role="alert">{error}</Text> : null}
      </div>
      <div className="image-model-control-actions">
        {loaded ? (
          <Button
            color="red"
            loading={action === 'unload'}
            disabled={!canUnload}
            onClick={onUnload}
            size="compact-sm"
            variant="light"
          >
            Unload Model
          </Button>
        ) : (
          <Button
            loading={action === 'load'}
            disabled={!canLoad}
            onClick={onLoad}
            size="compact-sm"
            variant="filled"
          >
            {action === 'load' ? 'Loading & Warming...' : 'Load & Warm Model'}
          </Button>
        )}
        <Button disabled={Boolean(action) || busy} loading={statusLoading} onClick={onRefresh} size="compact-sm" variant="subtle">
          Refresh Status
        </Button>
      </div>
    </section>
  );
}

export function imageModelGenerationBlockReason(
  status: ImageModelStatusPayload | undefined,
  statusLoading: boolean,
  statusError: boolean,
): string | undefined {
  if (statusLoading) return 'Checking FLUX.2 [klein] 4B model status.';
  if (statusError || !status) return 'The image model service is unavailable. Check the launcher and refresh status.';
  if (status.error || status.ok === false || status.state === 'unavailable') return 'The image model service is unavailable. Check the launcher and refresh status.';
  if (!status.enabled) return 'Image generation is disabled for this startup.';
  if (status.local_model?.complete === false) return 'The local FLUX.2 [klein] 4B model files are incomplete.';
  if (status.state === 'loading') return 'FLUX.2 [klein] 4B is loading.';
  if (status.state === 'warming') return 'FLUX.2 [klein] 4B is warming up. Generation will be enabled when warmup completes.';
  if (!status.loaded) return 'Load and warm FLUX.2 [klein] 4B before generating an image.';
  return undefined;
}
