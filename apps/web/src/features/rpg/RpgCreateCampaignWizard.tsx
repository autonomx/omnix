import { useEffect, useRef, useState } from 'react';
import { omnixApiClient, type RpgLaunchResponse, type RpgNewGameRequest } from '../../api/client';
import { loadSettingsProfile } from '../settings/settingsApi';
import { RpgCreateCampaignWizard as LegacyRpgCreateCampaignWizard } from './RpgCreateCampaignWizardLegacy';
import { applyRpgWizardDefaults, rpgWizardDefaultsFromSettings } from './rpgWizardDefaults';

interface RpgCreateCampaignWizardProps {
  onCreateCampaign?: (request: RpgNewGameRequest) => Promise<RpgLaunchResponse>;
  onEnterWorld?: () => void;
}

type WorldForgeDepth = 'quick' | 'standard' | 'epic';

type CampaignCreationProgress = {
  error?: string;
  job_id?: string;
  launch_ready?: boolean;
  percent?: number;
  progress?: number;
  stage?: string;
  status?: string;
};

type CampaignCreationResponse = RpgLaunchResponse & {
  creation_job?: CampaignCreationProgress & { id?: string };
  creation_progress?: CampaignCreationProgress;
};

const CAMPAIGN_CREATION_POLL_MS = 1_000;
const CAMPAIGN_CREATION_TIMEOUT_MS = 15 * 60_000;
const ACTIVE_CREATION_STATUSES = new Set(['queued', 'leased', 'running', 'waiting', 'retrying']);

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function campaignGeneration(response: RpgLaunchResponse): CampaignCreationProgress {
  const session = record(response.session);
  const runtime = record(session.runtime_state);
  return record(runtime.campaign_generation) as CampaignCreationProgress;
}

function creationJobId(response: CampaignCreationResponse): string {
  return String(response.creation_job?.id ?? response.creation_job?.job_id ?? response.creation_progress?.job_id ?? '').trim();
}

function creationStatus(response: CampaignCreationResponse): string {
  return String(response.creation_progress?.status ?? response.creation_job?.status ?? response.status ?? '').trim().toLowerCase();
}

function jobErrorMessage(job: Record<string, unknown>): string {
  const error = record(job.error);
  return String(error.message ?? error.code ?? 'Campaign World Forge generation failed.');
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function awaitCampaignCreation(
  initial: RpgLaunchResponse,
  onProgress?: (response: RpgLaunchResponse) => void,
): Promise<RpgLaunchResponse> {
  const queued = initial as CampaignCreationResponse;
  const jobId = creationJobId(queued);
  if (!jobId || !ACTIVE_CREATION_STATUSES.has(creationStatus(queued))) {
    return initial;
  }

  onProgress?.(initial);
  const startedAt = Date.now();
  while (Date.now() - startedAt < CAMPAIGN_CREATION_TIMEOUT_MS) {
    await delay(CAMPAIGN_CREATION_POLL_MS);
    const job = await omnixApiClient.getJob(jobId) as unknown as Record<string, unknown>;
    const status = String(job.status ?? '').toLowerCase();
    const sessionResponse = initial.session_id
      ? await omnixApiClient.getRpgSession(initial.session_id)
      : initial;
    const generation = campaignGeneration(sessionResponse);
    const progressResponse: CampaignCreationResponse = {
      ...initial,
      ...sessionResponse,
      status,
      creation_job: {
        id: jobId,
        job_id: jobId,
        status,
        progress: generation.progress ?? generation.percent ?? 0,
        error: generation.error,
      },
      creation_progress: {
        ...generation,
        job_id: jobId,
        status,
        progress: generation.progress ?? generation.percent ?? 0,
      },
    };
    onProgress?.(progressResponse);

    if (status === 'completed') {
      return {
        ...progressResponse,
        ok: true,
        status: 'ready',
        creation_job: { ...progressResponse.creation_job, status: 'completed', progress: 100 },
        creation_progress: {
          ...progressResponse.creation_progress,
          status: 'completed',
          launch_ready: true,
          progress: 100,
        },
      } as RpgLaunchResponse;
    }
    if (status === 'failed' || status === 'canceled' || status === 'stale') {
      return {
        ...progressResponse,
        ok: false,
        error: generation.error || jobErrorMessage(job),
        creation_progress: { ...progressResponse.creation_progress, status: 'failed' },
      } as RpgLaunchResponse;
    }
  }
  throw new Error('Campaign World Forge generation did not finish within 15 minutes.');
}

const depthOptions: Array<{
  value: WorldForgeDepth;
  label: string;
  detail: string;
}> = [
  {
    value: 'quick',
    label: 'Quick',
    detail: '12–20 lore pages, 4–6 major NPCs, 5–8 locations, 3–4 factions.',
  },
  {
    value: 'standard',
    label: 'Standard',
    detail: '30–50 lore pages, 8–12 major NPCs, 10–16 locations, 5–8 factions.',
  },
  {
    value: 'epic',
    label: 'Epic',
    detail: '70–120 lore pages, 15–25 major NPCs, 20–35 locations, 8–14 factions.',
  },
];

export function RpgCreateCampaignWizard(props: RpgCreateCampaignWizardProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const touchedRef = useRef(false);
  const applyingRef = useRef(false);
  const [worldForgeDepth, setWorldForgeDepth] = useState<WorldForgeDepth>('standard');

  useEffect(() => {
    let active = true;
    loadSettingsProfile()
      .then(({ profile }) => {
        if (!active || touchedRef.current || !rootRef.current) return;
        applyingRef.current = true;
        try {
          applyRpgWizardDefaults(rootRef.current, rpgWizardDefaultsFromSettings(profile));
        } finally {
          applyingRef.current = false;
        }
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  const markTouched = () => {
    if (!applyingRef.current) touchedRef.current = true;
  };

  const createCampaign = props.onCreateCampaign
    ? async (
        request: RpgNewGameRequest,
        onProgress?: (response: RpgLaunchResponse) => void,
      ): Promise<RpgLaunchResponse> => {
        const enriched = {
          ...request,
          world_forge: {
            enabled: true,
            depth: worldForgeDepth,
            background_expansion: false,
            use_hermes: true,
            require_consistency_audit: true,
            require_opening_dossiers: true,
          },
        } as RpgNewGameRequest;
        const initial = await props.onCreateCampaign?.(enriched) as RpgLaunchResponse;
        return awaitCampaignCreation(initial, onProgress);
      }
    : undefined;

  return (
    <div ref={rootRef} style={{ display: 'contents' }} onChangeCapture={markTouched} onInputCapture={markTouched}>
      <section
        aria-label="World generation depth"
        style={{
          border: '1px solid var(--border-subtle, rgba(255,255,255,.12))',
          borderRadius: 14,
          padding: 14,
          marginBottom: 14,
          background: 'var(--surface-elevated, rgba(255,255,255,.035))',
        }}
      >
        <div style={{ fontWeight: 700, marginBottom: 4 }}>World Forge depth</div>
        <div style={{ opacity: 0.72, fontSize: 13, marginBottom: 10 }}>
          Omnix creates a linked Campaign Bible, rich opening dossiers, a consistency audit, and a retrieval index before the first turn.
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 8 }}>
          {depthOptions.map((option) => {
            const selected = worldForgeDepth === option.value;
            return (
              <button
                key={option.value}
                type="button"
                aria-pressed={selected}
                onClick={() => setWorldForgeDepth(option.value)}
                style={{
                  textAlign: 'left',
                  borderRadius: 10,
                  border: selected
                    ? '1px solid var(--accent, #8ea7ff)'
                    : '1px solid var(--border-subtle, rgba(255,255,255,.12))',
                  background: selected
                    ? 'color-mix(in srgb, var(--accent, #8ea7ff) 16%, transparent)'
                    : 'transparent',
                  padding: 10,
                  color: 'inherit',
                  cursor: 'pointer',
                }}
              >
                <strong style={{ display: 'block' }}>{option.label}</strong>
                <span style={{ display: 'block', opacity: 0.7, fontSize: 12, marginTop: 4 }}>{option.detail}</span>
              </button>
            );
          })}
        </div>
      </section>
      <LegacyRpgCreateCampaignWizard {...props} onCreateCampaign={createCampaign} />
    </div>
  );
}
