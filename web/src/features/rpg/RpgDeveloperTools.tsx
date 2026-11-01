import type { JobRecord } from '../../api/client';
import type { HermesRpgApprovedFlowResponse } from './api/hermesRpgApprovedFlowClient';
import { RpgHermesExecutionResult } from './RpgHermesExecutionResult';
import { RpgHermesSequenceJobPanel } from './RpgHermesSequenceJobPanel';
import { RpgOperationsPanel } from './RpgOperationsPanel';

export type RpgHermesJobAction = 'start' | 'pause' | 'resume' | 'cancel';

interface RpgDeveloperToolsProps {
  executionResult: HermesRpgApprovedFlowResponse | null;
  activeJob?: JobRecord | null;
  isPending: boolean;
  onJobAction: (action: RpgHermesJobAction) => void;
}

/** What Developer mode shows beside the story (RQ-7.1): Hermes' last run and its job, and the turn record (RQ-8.4). */
export function RpgDeveloperTools({ executionResult, activeJob, isPending, onJobAction }: RpgDeveloperToolsProps) {
  return (
    <section className="rpg-developer-tools" aria-label="Developer tools">
      <RpgHermesExecutionResult result={executionResult} />
      <RpgHermesSequenceJobPanel
        activeJob={activeJob}
        isPending={isPending}
        onCancel={() => onJobAction('cancel')}
        onPause={() => onJobAction('pause')}
        onResume={() => onJobAction('resume')}
        onStart={() => onJobAction('start')}
      />
      <RpgOperationsPanel />
    </section>
  );
}
