import { liveConversationStore, type LiveConversationStore } from './live-conversation-store';
import {
  classifyLiveInput,
  type LiveAcousticClass,
  type LiveCoordinationAction,
  type LiveInputCoordination,
} from './live-input-coordination';
import {
  liveMaterialClient,
  type LiveMaterialAcknowledgement,
  type LiveMaterialClient,
} from './live-material-client';
import {
  LiveObservationQueue,
  createObservationAnchor,
  fingerprint,
  type LiveObservation,
} from './live-observation-coordinator';
import {
  decideLiveTaskTransition,
  inferLiveTaskContract,
  type LiveTaskContract,
} from './live-task-contract';

export const LIVE_COORDINATION_SUBMIT_EVENT = 'omnix:live-coordination-submit';
export const LIVE_OBSERVATION_CANDIDATE_EVENT = 'omnix:live-observation-candidate';
export const LIVE_TASK_CONTRACT_EVENT = 'omnix:live-task-contract';
export const LIVE_VOICE_INTERRUPT_EVENT = 'omnix:assistant-voice-interrupt';

export type CoordinateLiveTranscriptInput = {
  text: string;
  segmentId: string;
  sourceSequence: number;
  startSample?: number;
  endSample?: number;
  assistantSpeaking: boolean;
  acousticClass?: LiveAcousticClass;
  echoConfidence?: number;
};

export type CoordinateLiveTranscriptResult = {
  coordination: LiveInputCoordination;
  taskContract: LiveTaskContract;
  materialAcknowledgement?: LiveMaterialAcknowledgement;
  observation?: LiveObservation;
  submitted: boolean;
};

type CoordinatorDependencies = {
  store: LiveConversationStore;
  materialClient: Pick<LiveMaterialClient, 'append'>;
  now: () => number;
  dispatchEvent: (event: Event) => boolean;
};

const TASK_INSTRUCTION_PATTERN = /\b(?:translate|translation|interpret|correct my|correct the|grammar|proofread|coach my|pronunciation|just listen|stop correcting|summarize it)\b/i;

export class LiveSessionCoordinator {
  private readonly observations = new LiveObservationQueue();
  private readonly materialSequences = new Map<string, number>();
  private observationCounter = 0;

  constructor(private readonly dependencies: CoordinatorDependencies) {}

  setTaskContract(contract: LiveTaskContract): void {
    const previous = this.dependencies.store.getState().coordination.taskContract;
    const transition = decideLiveTaskTransition(previous, contract);
    this.dependencies.store.dispatch({ type: 'task_contract', contract });
    if (transition.invalidatePendingObservations) this.observations.invalidateTaskContract(contract);
    this.publishObservationQueue();
    if (transition.cancelSpeakingOutput) {
      this.dependencies.dispatchEvent(new CustomEvent(LIVE_VOICE_INTERRUPT_EVENT, {
        detail: { source: 'task-contract-transition', intent: 'hard_stop', confidence: 1 },
      }));
    }
  }

  setTaskInstruction(instruction: string): LiveTaskContract {
    const current = this.dependencies.store.getState().coordination.taskContract;
    const contract = inferLiveTaskContract(instruction, current.version + 1);
    this.setTaskContract(contract);
    return contract;
  }

  async coordinate(input: CoordinateLiveTranscriptInput): Promise<CoordinateLiveTranscriptResult> {
    const text = input.text.replace(/\s+/g, ' ').trim();
    let state = this.dependencies.store.getState();
    let taskContract = state.coordination.taskContract;
    const isTaskInstruction = taskContract.taskContractId === 'conversation' && TASK_INSTRUCTION_PATTERN.test(text);
    if (isTaskInstruction) {
      taskContract = this.setTaskInstruction(text);
      state = this.dependencies.store.getState();
    }
    const coordination = isTaskInstruction
      ? {
          acousticClass: input.acousticClass ?? 'speech',
          inputRole: 'conversation' as const,
          action: input.assistantSpeaking ? 'interrupt_and_respond' as const : 'respond' as const,
          confidence: 0.96,
          reason: 'task_instruction',
        }
      : classifyLiveInput(text, {
          taskContract,
          assistantSpeaking: input.assistantSpeaking,
          acousticClass: input.acousticClass,
          echoConfidence: input.echoConfidence,
        });
    this.dependencies.store.dispatch({ type: 'coordination_action', action: coordination.action });
    this.dependencies.store.dispatch({ type: 'transcript_final', text });

    switch (coordination.action) {
      case 'ignore':
        return { coordination, taskContract, submitted: false };
      case 'stop_output':
        this.dispatchInterrupt('hard_stop', coordination.confidence);
        return { coordination, taskContract, submitted: false };
      case 'respond':
        this.submitConversation(text, false);
        return { coordination, taskContract, submitted: true };
      case 'interrupt_and_respond':
        this.dispatchInterrupt('interrupt', coordination.confidence);
        this.submitConversation(text, true);
        return { coordination, taskContract, submitted: true };
      case 'append':
      case 'append_and_observe': {
        const sessionId = state.sessionId;
        if (!sessionId) throw new Error('Live material requires an active chat session.');
        const sequence = this.nextMaterialSequence(sessionId, state.coordination.acceptedSequence);
        const acknowledgement = await this.dependencies.materialClient.append(sessionId, {
          segment_id: input.segmentId,
          sequence,
          text,
          start_sample: input.startSample ?? 0,
          end_sample: input.endSample ?? 0,
          response_policy: coordination.action === 'append_and_observe' ? 'observe' : 'none',
          retention: taskContract.defaultRetention,
          task_contract_id: taskContract.taskContractId,
          task_contract_version: taskContract.version,
        });
        this.materialSequences.set(sessionId, acknowledgement.accepted_sequence + 1);
        this.dependencies.store.dispatch({
          type: 'material_ack',
          acceptedSequence: acknowledgement.accepted_sequence,
          contextVersion: acknowledgement.context_version,
        });
        if (coordination.action === 'append') {
          return { coordination, taskContract, materialAcknowledgement: acknowledgement, submitted: false };
        }
        const observation = this.createObservation(input, acknowledgement, taskContract);
        const admission = this.observations.admitCandidate(observation, {
          nowMs: this.dependencies.now(),
          contextVersion: acknowledgement.context_version,
          taskContract,
          deliveredEquivalenceKeys: new Set(),
          queuedSpeechMs: this.observations.queuedSpeechMs,
        });
        if (admission.admitted) {
          this.dependencies.dispatchEvent(new CustomEvent(LIVE_OBSERVATION_CANDIDATE_EVENT, {
            detail: { observation, sourceText: text },
          }));
        }
        this.publishObservationQueue();
        return {
          coordination,
          taskContract,
          materialAcknowledgement: acknowledgement,
          observation: admission.admitted ? observation : undefined,
          submitted: false,
        };
      }
      default:
        return assertNever(coordination.action);
    }
  }

  markSelfCorrected(anchorId: string): string[] {
    const superseded = this.observations.markAnchorState(anchorId, 'self_corrected');
    this.publishObservationQueue();
    return superseded;
  }

  private nextMaterialSequence(sessionId: string, acceptedSequence: number): number {
    const known = this.materialSequences.get(sessionId);
    if (known !== undefined) return known;
    return acceptedSequence + 1;
  }

  private createObservation(
    input: CoordinateLiveTranscriptInput,
    acknowledgement: LiveMaterialAcknowledgement,
    taskContract: LiveTaskContract,
  ): LiveObservation {
    const anchor = createObservationAnchor(input.segmentId, input.text);
    const priority = /\b(?:danger|wrong recipient|password|credit card|social insurance|urgent)\b/i.test(input.text)
      ? 'critical'
      : taskContract.observationPolicy.minorFeedback === 'consolidate' ? 'deferred' : 'normal';
    return {
      observationId: `observation-${++this.observationCounter}`,
      basedOnSequence: input.sourceSequence,
      contextVersion: acknowledgement.context_version,
      taskContractId: taskContract.taskContractId,
      taskContractVersion: taskContract.version,
      anchors: [anchor],
      priority,
      status: 'candidate',
      createdAtMs: this.dependencies.now(),
      estimatedSpeechMs: Math.min(taskContract.observationPolicy.preferredMaximumSpeechMs, 3_000),
      equivalenceKey: `${taskContract.taskContractId}:${fingerprint(input.text)}`,
    };
  }

  private submitConversation(text: string, interrupted: boolean): void {
    this.dependencies.dispatchEvent(new CustomEvent(LIVE_COORDINATION_SUBMIT_EVENT, {
      detail: { text, interrupted },
    }));
  }

  private dispatchInterrupt(intent: string, confidence: number): void {
    this.dependencies.dispatchEvent(new CustomEvent(LIVE_VOICE_INTERRUPT_EVENT, {
      detail: { source: 'live-session-coordinator', intent, confidence },
    }));
  }

  private publishObservationQueue(): void {
    const active = this.observations.snapshot.filter((item) => item.status !== 'superseded' && item.status !== 'completed' && item.status !== 'failed');
    this.dependencies.store.dispatch({
      type: 'observation_queue',
      count: active.length,
      speechMs: this.observations.queuedSpeechMs,
    });
  }
}

export const liveSessionCoordinator = new LiveSessionCoordinator({
  store: liveConversationStore,
  materialClient: liveMaterialClient,
  now: () => performance.now(),
  dispatchEvent: (event) => window.dispatchEvent(event),
});

let initialized = false;

export function initializeLiveSessionCoordinator(): void {
  if (initialized || typeof window === 'undefined') return;
  initialized = true;
  window.addEventListener(LIVE_COORDINATION_SUBMIT_EVENT, (event) => {
    const detail = (event as CustomEvent<{ text?: string }>).detail;
    const text = detail?.text?.trim();
    if (!text) return;
    const textarea = document.querySelector<HTMLTextAreaElement>('.assistant-message-input textarea');
    const form = document.querySelector<HTMLFormElement>('.assistant-composer');
    if (!textarea || !form) return;
    textarea.value = text;
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    if (typeof form.requestSubmit === 'function') form.requestSubmit();
    else form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  });
  window.addEventListener(LIVE_TASK_CONTRACT_EVENT, (event) => {
    const detail = (event as CustomEvent<{ instruction?: string; contract?: LiveTaskContract }>).detail;
    if (detail?.contract) liveSessionCoordinator.setTaskContract(detail.contract);
    else if (detail?.instruction?.trim()) liveSessionCoordinator.setTaskInstruction(detail.instruction);
  });
}

function assertNever(value: never): never {
  throw new Error(`Unsupported Live coordination action: ${String(value)}`);
}
