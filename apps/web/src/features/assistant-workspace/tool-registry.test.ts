import { describe, expect, it } from 'vitest';
import { canExecuteToolAction } from './tool-actions';
import { createDefaultAssistantToolRegistry } from './tool-registry';

describe('assistant workspace tool registry', () => {
  it('registers default assistant tools by category', () => {
    const registry = createDefaultAssistantToolRegistry();
    const tools = registry.list();

    expect(tools.map((tool) => tool.id)).toEqual(['gmail', 'calendar', 'contacts', 'github']);
    expect(registry.get('github')?.category).toBe('development');
    expect(registry.get('gmail')?.category).toBe('communication');
    expect(registry.get('calendar')?.category).toBe('productivity');
    expect(registry.get('contacts')?.category).toBe('productivity');
  });

  it('discovers actions across registered tools', () => {
    const registry = createDefaultAssistantToolRegistry();
    const match = registry.getAction('github.merge_pr');

    expect(match?.tool.id).toBe('github');
    expect(match?.action.label).toBe('Merge pull requests');
    expect(match?.action.requiresConfirmation).toBe(true);
  });

  it('keeps destructive defaults disabled or approval gated', () => {
    const registry = createDefaultAssistantToolRegistry();
    const deleteBranch = registry.getAction('github.delete_branch');

    expect(deleteBranch?.action.isDestructive).toBe(true);
    expect(deleteBranch ? canExecuteToolAction(deleteBranch.action).allowed : true).toBe(false);
  });

  it('validates connection-backed tool config', () => {
    const registry = createDefaultAssistantToolRegistry();
    const gmail = registry.get('gmail');

    expect(gmail).toBeDefined();
    expect(gmail?.validateConfig({ enabled: true, connectionStatus: 'not_configured' })).toEqual({
      valid: false,
      status: 'not_configured',
      messages: ['Tool must be connected before actions can run.'],
    });
    expect(gmail?.validateConfig({ enabled: true, connectionStatus: 'connected' }).valid).toBe(true);
  });
});
