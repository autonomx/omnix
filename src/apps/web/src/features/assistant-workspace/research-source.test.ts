import { describe, expect, it } from 'vitest';
import { DEFAULT_WEB_RESEARCH_CONFIG, RETRIEVAL_PROFILES, createQueryPlan, decideWebResearch } from './web-research';

describe('research source model', () => {
  it('keeps disabled config inactive', () => {
    expect(decideWebResearch(DEFAULT_WEB_RESEARCH_CONFIG, { explicitRequest: true })).toMatchObject({ shouldRetrieve: false, reason: 'disabled' });
  });

  it('runs automatically when fresh context is needed', () => {
    const decision = decideWebResearch({ ...DEFAULT_WEB_RESEARCH_CONFIG, enabled: true, mode: 'automatic' }, { freshnessRequired: true });
    expect(decision.shouldRetrieve).toBe(true);
    expect(decision.reason).toBe('freshness_required');
  });

  it('limits query plans by profile', () => {
    expect(createQueryPlan('omnix assistant architecture', RETRIEVAL_PROFILES.fast)).toHaveLength(2);
    expect(createQueryPlan('omnix assistant architecture', RETRIEVAL_PROFILES.research).length).toBeGreaterThan(2);
  });
});
