import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ProviderFacadePayload } from '../../api/client';
import { MEMORY_ROUTE_KEY, MemoryModelSection } from './MemoryModelSection';
import { DEFAULT_SETTINGS_DOCUMENT } from './settingsDefaults';

const dispatch = vi.fn();
let taskOverrides: Record<string, { providerId: string; modelId: string }> = {};

vi.mock('./SettingsProfileContext', () => ({
  useSettingsProfileContext: () => ({
    state: {
      draft: {
        ...DEFAULT_SETTINGS_DOCUMENT,
        global: {
          ...DEFAULT_SETTINGS_DOCUMENT.global,
          providers: { ...DEFAULT_SETTINGS_DOCUMENT.global.providers, llm: 'claude_cli' },
          routing: { fallbackBehavior: 'next-available', taskOverrides },
        },
      },
    },
    dispatch,
  }),
}));

const payload = {
  providers: [
    { id: 'llm:claude_cli', family: 'llm', label: 'Claude (Claude Code CLI)', capabilities: ['chat'] },
    { id: 'llm:chatgpt_codex', family: 'llm', label: 'ChatGPT (Codex)', capabilities: ['chat'] },
  ],
  models: [
    { id: 'claude-sonnet-5-5', label: 'Sonnet 5.5', provider_id: 'llm:claude_cli', capabilities: ['chat'], metadata: {} },
    { id: 'gpt-5.6-sol', label: 'GPT-5.6', provider_id: 'llm:chatgpt_codex', capabilities: ['chat'], metadata: {} },
  ],
} as unknown as ProviderFacadePayload;

beforeEach(() => {
  dispatch.mockClear();
  taskOverrides = { 'story.generate': { providerId: 'openrouter', modelId: 'story-model' } };
});

describe('Memory model', () => {
  it('follows the default provider until one is chosen, and says what the default does', () => {
    render(<MemoryModelSection payload={payload} />);

    const provider = screen.getByLabelText('Memory provider') as HTMLSelectElement;
    expect(provider.value).toBe('');
    expect(screen.getByRole('option', { name: 'Same as the default: Claude (Claude Code CLI)' })).toBeInTheDocument();
    expect(screen.getByText('Provider default: Sonnet reads chats; the Claude CLI model picks memories.')).toBeInTheDocument();
  });

  it('stores a chosen provider as a routing override, keeping the other overrides', () => {
    render(<MemoryModelSection payload={payload} />);

    fireEvent.change(screen.getByLabelText('Memory provider'), { target: { value: 'chatgpt_codex' } });

    expect(dispatch).toHaveBeenLastCalledWith({
      type: 'update', path: 'global.routing.taskOverrides',
      value: {
        'story.generate': { providerId: 'openrouter', modelId: 'story-model' },
        [MEMORY_ROUTE_KEY]: { providerId: 'chatgpt_codex', modelId: '' },
      },
    });
  });

  it('offers the chosen provider’s models, and going back to the default removes the override', () => {
    taskOverrides = { ...taskOverrides, [MEMORY_ROUTE_KEY]: { providerId: 'chatgpt_codex', modelId: '' } };
    render(<MemoryModelSection payload={payload} />);

    expect(screen.getByRole('option', { name: 'GPT-5.6' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Sonnet 5.5' })).toBeNull();
    fireEvent.change(screen.getByLabelText('Memory model'), { target: { value: 'gpt-5.6-sol' } });
    expect(dispatch).toHaveBeenLastCalledWith(expect.objectContaining({
      value: expect.objectContaining({ [MEMORY_ROUTE_KEY]: { providerId: 'chatgpt_codex', modelId: 'gpt-5.6-sol' } }),
    }));

    fireEvent.change(screen.getByLabelText('Memory provider'), { target: { value: '' } });
    expect(dispatch).toHaveBeenLastCalledWith({
      type: 'update', path: 'global.routing.taskOverrides',
      value: { 'story.generate': { providerId: 'openrouter', modelId: 'story-model' } },
    });
  });
});
