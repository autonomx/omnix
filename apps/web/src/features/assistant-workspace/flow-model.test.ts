import { describe, expect, it } from 'vitest';
import { createDefaultFlowRegistry, createFlowRegistry } from './flows';

describe('flow model', () => {
  it('lists default flows', () => {
    expect(createDefaultFlowRegistry().list().length).toBeGreaterThan(3);
  });

  it('compiles a default flow', () => {
    const plan = createDefaultFlowRegistry().compile('weekly_project_report', 'include risks');
    expect(plan?.flowId).toBe('weekly_project_report');
    expect(plan?.outputs).toEqual(['report']);
  });

  it('registers one custom flow', () => {
    const registry = createFlowRegistry();
    registry.register({ id: 'custom', label: 'Custom', description: 'Custom flow', triggers: ['manual'], outputs: ['chat_response'], promptPrefix: 'Custom' });
    expect(registry.list()).toHaveLength(1);
  });
});
