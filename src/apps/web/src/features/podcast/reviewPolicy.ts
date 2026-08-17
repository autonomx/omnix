import type { ProductionGenerationStyle, ProductionStage, ReviewMode, ReviewPolicy } from '../conversation-production/types';
import { automaticReviewPolicy } from '../conversation-production/types';

export interface ReviewStopOption {
  id: keyof ReviewPolicy;
  stage: ProductionStage;
  label: string;
  description: string;
}

export interface GenerationStyleOption {
  id: ProductionGenerationStyle;
  label: string;
  description: string;
}

export const generationStyleOptions: GenerationStyleOption[] = [
  {
    id: 'automatic',
    label: 'Automatic (Recommended)',
    description: 'AI researches, writes, voices, mixes, and publishes automatically.',
  },
  {
    id: 'guided',
    label: 'Guided',
    description: 'Pause at selected stages for review.',
  },
];

export const reviewStopOptions: ReviewStopOption[] = [
  {
    id: 'research',
    stage: 'research',
    label: 'Research',
    description: 'Review gathered facts, sources, and uncertainty before planning.',
  },
  {
    id: 'producerPlan',
    stage: 'producer_plan',
    label: 'Producer Plan',
    description: 'Approve audience fit, tension, pacing, and segment direction.',
  },
  {
    id: 'canonicalScript',
    stage: 'canonical_script',
    label: 'Canonical Script',
    description: 'Edit clean source-of-truth dialogue before delivery markup.',
  },
  {
    id: 'performanceScript',
    stage: 'performance_script',
    label: 'Performance Script',
    description: 'Review pauses, emphasis, interruptions, and emotion cues.',
  },
  {
    id: 'voiceTakes',
    stage: 'voice_takes',
    label: 'Voice Takes',
    description: 'Approve or regenerate cloned-voice takes.',
  },
  {
    id: 'mix',
    stage: 'mix',
    label: 'Final Mix',
    description: 'Review loudness, chapters, and final exports before publishing.',
  },
];

export function buildReviewPolicy(style: ProductionGenerationStyle, manualStops: Array<keyof ReviewPolicy>): ReviewPolicy {
  if (style === 'automatic') {
    return { ...automaticReviewPolicy };
  }

  return reviewStopOptions.reduce<ReviewPolicy>((policy, option) => {
    policy[option.id] = manualStops.includes(option.id) ? 'manual' : 'auto';
    return policy;
  }, { ...automaticReviewPolicy });
}

export function reviewModeLabel(mode: ReviewMode): string {
  return mode === 'manual' ? 'Manual review' : 'Auto-approved';
}
