import { describe, expect, it } from 'vitest';
import { createChatContextPlan } from './chat-context';

describe('chat context integration', () => {
  it('uses local sources for stable prompts', () => {
    const result = createChatContextPlan({ prompt: 'Summarize the current project', workspaceId: 'omnix' });
    expect(result.retrievalSourceIds).toContain('memory');
    expect(result.retrievalSourceIds).toContain('workspace_documents');
    expect(result.retrievalSourceIds).not.toContain('web_research');
  });

  it('adds web source only when configured and freshness is required', () => {
    const disabled = createChatContextPlan({ prompt: 'Search latest SDK docs', workspaceId: 'omnix' });
    const enabled = createChatContextPlan({
      prompt: 'Search latest SDK docs',
      workspaceId: 'omnix',
      sourceConfigs: { web_research: { enabled: true, priority: 80 } },
    });

    expect(disabled.retrievalSourceIds).not.toContain('web_research');
    expect(enabled.retrievalSourceIds).toContain('web_research');
  });

  it('packs selected context for provider runtime', () => {
    const result = createChatContextPlan({ prompt: 'Review PR', workspaceId: 'omnix', currentContext: ['Existing session note'] });
    expect(result.pack.sources[0]?.id).toBe('conversation:0');
    expect(result.plan.intent.intent).toBe('review_pull_request');
  });
});
