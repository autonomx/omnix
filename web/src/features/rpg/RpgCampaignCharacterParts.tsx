import type { RpgLaunchResponse } from './api/rpgSessionClient';
import { creationStages, type CreationStageState } from './rpgCreateCampaignState';

interface BackendCreationStage {
  detail?: string;
  label?: string;
  progress?: number;
  status?: string;
}

interface BackendCreationProgress {
  current_stage_index?: number;
  error?: string;
  progress?: number;
  stage_label?: string;
  stages?: BackendCreationStage[];
  status?: string;
}

interface BackendCreationJob {
  error?: string;
  progress?: number;
  status?: string;
}

export type LaunchResponseWithProgress = RpgLaunchResponse & {
  creation_job?: BackendCreationJob;
  creation_progress?: BackendCreationProgress;
};

export const FALLBACK_PROGRESS_STEPS = [8, 18, 31, 44, 56, 68, 78, 88, 96, 100];

export const PENDING_PROGRESS_STEPS = FALLBACK_PROGRESS_STEPS.slice(1, -2);

export function getCreationProgress(response: RpgLaunchResponse | null): BackendCreationProgress | undefined {
  return (response as LaunchResponseWithProgress | null)?.creation_progress;
}

export function getCreationStatus(response: LaunchResponseWithProgress): string | undefined {
  return response.creation_progress?.status ?? response.creation_job?.status ?? response.status;
}

export function getCreationError(response: LaunchResponseWithProgress): string | undefined {
  return response.error ?? response.creation_progress?.error ?? response.creation_job?.error;
}

export function getCreationProgressValue(response: LaunchResponseWithProgress, fallback: number): number {
  return clampProgress(response.creation_progress?.progress ?? response.creation_job?.progress ?? fallback);
}

export function clampProgress(value: unknown): number {
  const numeric = typeof value === 'number' && Number.isFinite(value) ? value : 0;
  return Math.max(0, Math.min(100, Math.round(numeric)));
}

export function normalizeStageIndex(value: unknown, progressPercent: number): number {
  if (typeof value === 'number' && Number.isInteger(value)) {
    return Math.max(0, Math.min(creationStages.length - 1, value));
  }
  const nextStageIndex = FALLBACK_PROGRESS_STEPS.findIndex((stageProgress) => stageProgress > progressPercent);
  return nextStageIndex < 0 ? creationStages.length - 1 : Math.min(creationStages.length - 1, nextStageIndex);
}

interface OptionSelectProps {
  detail?: string;
  label: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
  value: string;
}

export function OptionSelect({ detail, label, onChange, options, value }: OptionSelectProps) {
  return (
    <label>
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {detail ? <small>{detail}</small> : null}
    </label>
  );
}

export function BasicSelect({ label, onChange, options, value }: Omit<OptionSelectProps, 'detail' | 'options'> & { options: string[] }) {
  return (
    <label>
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option} value={option}>
            {option.replace('-', ' ')}
          </option>
        ))}
      </select>
    </label>
  );
}

export function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

interface ProgressModalProps {
  activeCapabilities: string[];
  activeStageIndex: number;
  characterName: string;
  closeProgress: () => void;
  creationError: string | null;
  creationProgress?: BackendCreationProgress;
  enterWorld: () => void;
  isCreated: boolean;
  progressPercent: number;
  seed: string;
  selectedBackground: string;
  selectedBuild: string;
  selectedLocation: string;
  selectedOpeningHook: string;
  selectedPrimary: string;
  sessionId?: string;
  stageState: (index: number) => CreationStageState;
}

export function ProgressModal({
  activeCapabilities,
  activeStageIndex,
  characterName,
  closeProgress,
  creationError,
  creationProgress,
  enterWorld,
  isCreated,
  progressPercent,
  seed,
  selectedBackground,
  selectedBuild,
  selectedLocation,
  selectedOpeningHook,
  selectedPrimary,
  sessionId,
  stageState,
}: ProgressModalProps) {
  const title = creationError ? 'Campaign Creation Failed' : isCreated ? 'Campaign Ready' : 'Creating Campaign';
  const activeStage = creationProgress?.stages?.[activeStageIndex] ?? creationStages[activeStageIndex];
  const displayedStages = creationStages.map((stage, index) => ({
    detail: creationProgress?.stages?.[index]?.detail ?? stage.detail,
    label: creationProgress?.stages?.[index]?.label ?? stage.label,
    state: stageState(index),
  }));

  return (
    <div className="rpg-create-progress-overlay" role="dialog" aria-modal="true" aria-labelledby="rpg-create-progress-title">
      <div className="rpg-create-progress-modal">
        <header>
          <div>
            <p className="eyebrow">Campaign creation</p>
            <h3 id="rpg-create-progress-title">{title}</h3>
            <p>Building a deterministic world from your setup.</p>
          </div>
          <strong>{progressPercent}%</strong>
        </header>
        <div className="rpg-create-progress-track" aria-label="Campaign creation progress" aria-valuenow={progressPercent} aria-valuemin={0} aria-valuemax={100} role="progressbar">
          <span style={{ width: `${progressPercent}%` }} />
        </div>
        {creationError ? (
          <p className="rpg-create-warning">Failed at {activeStage.label}: {creationError}</p>
        ) : (
          <p className="rpg-create-current-stage">{activeStage.label}: {activeStage.detail}</p>
        )}
        <div className="rpg-create-stage-list">
          {displayedStages.map((stage, index) => (
            <div className={`rpg-create-stage-row rpg-create-stage-${stage.state}`} key={`${stage.label}-${index}`}>
              <span aria-hidden="true">{stage.state === 'done' ? '✓' : stage.state === 'active' ? '•' : '○'}</span>
              <div>
                <strong>{stage.label}</strong>
                <small>{stage.detail}</small>
              </div>
            </div>
          ))}
        </div>
        <div className="rpg-create-modal-summary">
          <span>{characterName}</span>
          <span>{selectedBackground}</span>
          <span>{selectedLocation}</span>
          <span>{selectedBuild}</span>
          <span>{selectedOpeningHook}</span>
          <span>{selectedPrimary}</span>
          <span>{activeCapabilities.join(' + ')}</span>
          <span>Seed {seed || 'random'}</span>
          {sessionId ? <span>Session {sessionId}</span> : null}
        </div>
        <p className="rpg-create-modal-note">Optional opening narration, TTS, STT, or image generation can continue after the campaign is ready.</p>
        <footer>
          <button className="rpg-secondary-button" type="button" onClick={closeProgress}>
            {creationError ? 'Back to setup' : 'Cancel'}
          </button>
          <button className="rpg-primary-button" type="button" disabled={!isCreated || Boolean(creationError)} onClick={enterWorld}>
            Enter World
          </button>
        </footer>
      </div>
    </div>
  );
}
