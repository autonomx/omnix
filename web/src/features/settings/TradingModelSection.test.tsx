import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ProviderFacadePayload } from '../../api/client';
import { TRADING_ROUTE_KEY, TradingModelSection } from './TradingModelSection';
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
    { id: 'llm:lmstudio', family: 'llm', label: 'LM Studio', capabilities: ['chat'] },
  ],
  models: [
    { id: 'claude-sonnet-5-5', label: 'Sonnet 5.5', provider_id: 'llm:claude_cli', capabilities: ['chat'], metadata: {} },
    { id: 'qwen/qwen3.8-27b', label: 'Qwen 3.8 27B', provider_id: 'llm:lmstudio', capabilities: ['chat'], metadata: {} },
  ],
} as unknown as ProviderFacadePayload;

beforeEach(() => {
  dispatch.mockClear();
  taskOverrides = { 'assistant-memory': { providerId: 'chatgpt_codex', modelId: '' } };
});

describe('Trading model', () => {
  it('follows the default provider until one is chosen', () => {
    render(<TradingModelSection payload={payload} />);

    expect((screen.getByLabelText('Trading provider') as HTMLSelectElement).value).toBe('');
    expect(screen.getByRole('option', { name: 'Same as the default: Claude (Claude Code CLI)' })).toBeInTheDocument();
  });

  it('stores LM Studio and its model under the key the backend reads, keeping other overrides', () => {
    expect(TRADING_ROUTE_KEY).toBe('trading-research');
    taskOverrides = { ...taskOverrides, [TRADING_ROUTE_KEY]: { providerId: 'lmstudio', modelId: '' } };
    render(<TradingModelSection payload={payload} />);

    expect(screen.getByText('Blank uses whichever model is loaded. Enter a model key to pin it: trading then pauses if another model is loaded.')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/^Trading model/), { target: { value: 'qwen/qwen3.8-27b' } });

    expect(dispatch).toHaveBeenLastCalledWith({
      type: 'update', path: 'global.routing.taskOverrides',
      value: {
        'assistant-memory': { providerId: 'chatgpt_codex', modelId: '' },
        [TRADING_ROUTE_KEY]: { providerId: 'lmstudio', modelId: 'qwen/qwen3.8-27b' },
      },
    });
  });

  it('going back to the default removes only its own override', () => {
    taskOverrides = { ...taskOverrides, [TRADING_ROUTE_KEY]: { providerId: 'lmstudio', modelId: '' } };
    render(<TradingModelSection payload={payload} />);

    fireEvent.change(screen.getByLabelText('Trading provider'), { target: { value: '' } });

    expect(dispatch).toHaveBeenLastCalledWith({
      type: 'update', path: 'global.routing.taskOverrides',
      value: { 'assistant-memory': { providerId: 'chatgpt_codex', modelId: '' } },
    });
  });
});
