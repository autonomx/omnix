import { describe, expect, it } from 'vitest';
import { codexReasoningOptions } from './ProviderDefaultsSection';

describe('Codex reasoning effort options', () => {
  it('offers extra high for GPT-5.6 Luna even when the catalog stops at high', () => {
    const options = codexReasoningOptions(undefined, 'gpt-5.6-luna', 'high');

    expect(options).toEqual([
      { id: 'none', label: 'Off (no reasoning)' },
      { id: 'low', label: 'low' },
      { id: 'medium', label: 'medium' },
      { id: 'high', label: 'high' },
      { id: 'xhigh', label: 'extra high' },
    ]);
  });

  it('does not add Luna-only extra high to other models', () => {
    const options = codexReasoningOptions(undefined, 'gpt-5.6-sol', 'high');

    expect(options.map((option) => option.id)).toEqual(['none', 'low', 'medium', 'high']);
  });

  it('does not duplicate extra high when Codex advertises it', () => {
    const options = codexReasoningOptions({
      providers: [],
      models: [{
        id: 'llm:chatgpt_codex:gpt-5.6-luna',
        label: 'GPT-5.6 Luna',
        provider_id: 'llm:chatgpt_codex',
        capabilities: ['chat'],
        location: 'unknown',
        metadata: { supported_reasoning_efforts: ['none', 'high', 'xhigh'] },
      }],
    }, 'gpt-5.6-luna', 'xhigh');

    expect(options.map((option) => option.id)).toEqual(['none', 'high', 'xhigh']);
  });
});
