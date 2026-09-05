import { useQuery } from '@tanstack/react-query';
import { omnixApiClient } from '../../api/client';
import { OmnixRunCard as OmnixRunCardCore } from './OmnixRunCardCore';
import './OmnixRunCardQuality.css';

type Metadata = Record<string, unknown>;

type QualityStage =
  | 'inspect'
  | 'planning'
  | 'implementing'
  | 'self_review'
  | 'validating'
  | 'reviewing'
  | 'repairing'
  | 'acceptance';

type QualityAwareAgentRun = {
  status?: unknown;
  quality_stage?: unknown;
  quality_attempt?: unknown;
  workspace_state_id?: unknown;
  spec?: {
    profile?: unknown;
    quality_policy?: unknown;
  };
};

const QUALITY_STAGES: Array<{ id: QualityStage; label: string }> = [
  { id: 'inspect', label: 'Inspect' },
  { id: 'planning', label: 'Plan' },
  { id: 'implementing', label: 'Implement' },
  { id: 'self_review', label: 'Self-review' },
  { id: 'validating', label: 'Validate' },
  { id: 'reviewing', label: 'Independent review' },
  { id: 'acceptance', label: 'Acceptance' },
];

function asRecord(value: unknown): Metadata | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Metadata : null;
}

function initialAgentRunId(metadata?: Metadata): string {
  const agent = asRecord(metadata?.agent_run);
  return typeof agent?.run_id === 'string' ? agent.run_id : '';
}

function normalizedStage(value: unknown): QualityStage | null {
  if (typeof value !== 'string') return null;
  return [
    'inspect',
    'planning',
    'implementing',
    'self_review',
    'validating',
    'reviewing',
    'repairing',
    'acceptance',
  ].includes(value) ? value as QualityStage : null;
}

function stageLabel(stage: QualityStage): string {
  if (stage === 'repairing') return 'Repairing reviewer / acceptance findings';
  if (stage === 'self_review') return 'Implementer self-review';
  if (stage === 'validating') return 'Validating final workspace state';
  if (stage === 'reviewing') return 'Independent code review';
  if (stage === 'acceptance') return 'Omnix final acceptance';
  if (stage === 'planning') return 'Planning implementation';
  if (stage === 'inspect') return 'Inspecting repository';
  return 'Implementing';
}

function QualityProgress({ stage, attempt }: { stage: QualityStage; attempt: number }) {
  const effectiveStage: QualityStage = stage === 'repairing' ? 'implementing' : stage;
  const currentIndex = QUALITY_STAGES.findIndex((item) => item.id === effectiveStage);
  return (
    <section
      className="assistant-runtime-quality"
      data-quality-stage={stage}
      aria-label="Coding quality pipeline"
    >
      <div className="assistant-runtime-quality-heading">
        <strong>{stageLabel(stage)}</strong>
        <span>{attempt > 1 ? `Quality attempt ${attempt}` : 'Quality gate active'}</span>
      </div>
      <ol className="assistant-runtime-quality-steps">
        {QUALITY_STAGES.map((item, index) => {
          const state = stage === 'repairing'
            ? (item.id === 'implementing' ? 'active' : 'pending')
            : index < currentIndex
              ? 'complete'
              : index === currentIndex
                ? 'active'
                : 'pending';
          return (
            <li data-state={state} key={item.id}>
              <span aria-hidden="true">{state === 'complete' ? '✓' : state === 'active' ? '●' : '○'}</span>
              {item.label}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

export function OmnixRunCard({ metadata }: { metadata?: Metadata }) {
  const id = initialAgentRunId(metadata);
  const query = useQuery({
    queryKey: ['agent-run', id],
    queryFn: () => omnixApiClient.getAgentRun(id),
    enabled: Boolean(id),
    refetchInterval: (state) => {
      const run = state.state.data as QualityAwareAgentRun | undefined;
      const status = String(run?.status ?? '');
      return ['completed', 'failed', 'cancelled'].includes(status) ? false : 1500;
    },
  });
  // AgentRunSnapshot is intentionally hand-written in the legacy web client and
  // can lag the server OpenAPI model. Treat the quality fields as a typed
  // additive extension so the run card remains compatible while the generated
  // contract catches up.
  const run = query.data as QualityAwareAgentRun | undefined;
  const stage = normalizedStage(run?.quality_stage);
  const profile = String(run?.spec?.profile ?? '');
  const qualityPolicy = String(run?.spec?.quality_policy ?? 'off');
  const attempt = Math.max(1, Number(run?.quality_attempt ?? 1) || 1);

  return (
    <>
      {id && profile === 'coding' && qualityPolicy !== 'off' && stage ? (
        <QualityProgress stage={stage} attempt={attempt} />
      ) : null}
      <OmnixRunCardCore metadata={metadata} />
    </>
  );
}