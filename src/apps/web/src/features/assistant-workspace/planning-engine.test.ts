import { describe, expect, it } from 'vitest';
import { createAssistantPlan, createExecutionPlan, createIntentPlan, createRetrievalPlan } from './planning-engine';
import type { AssistantCapability } from './derived-capabilities';

const capabilities: AssistantCapability[] = [
  { id: 'github.read_pr', label: 'Read PR', source: 'tool', available: true, riskLevel: 'low' },
  { id: 'gmail.create_draft', label: 'Create draft', source: 'tool', available: true, riskLevel: 'medium' },
  { id: 'github.merge_pr', label: 'Merge PR', source: 'tool', available: false, riskLevel: 'high', reason: 'Disabled' },
];

describe('planning engine v2', () => {
  it('detects pull request review intent', () => {
    expect(createIntentPlan('Review PR #123').intent).toBe('review_pull_request');
  });

  it('plans fresh retrieval sources when current context is requested', () => {
    const plan = createRetrievalPlan('Search latest docs and verify with citations');
    expect(plan.sourceIds).toContain('web_research');
    expect(plan.needsFreshness).toBe(true);
    expect(plan.needsVerification).toBe(true);
  });

  it('separates available and unavailable execution actions', () => {
    const plan = createExecutionPlan('Review PR and merge PR then email summary', capabilities);
    expect(plan.actionIds).toEqual(['gmail.create_draft', 'github.read_pr']);
    expect(plan.unavailableActionIds).toEqual(['github.merge_pr']);
  });

  it('creates a structured assistant plan', () => {
    const plan = createAssistantPlan({ prompt: 'Review PR and email me a summary', capabilities });
    expect(plan.intent.intent).toBe('review_pull_request');
    expect(plan.response.outputs).toContain('draft_email');
  });
});
