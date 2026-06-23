import { describe, expect, it } from 'vitest';
import type { ModelRequest } from './provider';
import {
  flattenMessageContent,
  fromAnthropicMessagesResponse,
  fromOpenAiChatResponse,
  toAnthropicMessagesRequest,
  toOpenAiChatRequest,
} from './provider-adapters';

const request: ModelRequest = {
  provider: 'openai-compatible',
  model: 'gpt-test',
  messages: [
    { role: 'system', content: [{ kind: 'text', text: 'Be precise.' }] },
    { role: 'user', content: [{ kind: 'text', text: 'Hello' }] },
  ],
  tools: [
    {
      id: 'tool-1',
      name: 'lookup',
      description: 'Lookup a fact',
      inputSchema: { type: 'object' },
    },
  ],
  jsonMode: true,
  stream: true,
  temperature: 0.2,
  metadata: { workspaceId: 'workspace-1' },
};

describe('assistant workspace provider adapters', () => {
  it('flattens internal message content', () => {
    expect(flattenMessageContent([{ kind: 'text', text: 'A' }, { kind: 'status', text: 'B' }])).toBe('A\nB');
  });

  it('maps internal requests to OpenAI-compatible chat requests', () => {
    const mapped = toOpenAiChatRequest(request);

    expect(mapped.model).toBe('gpt-test');
    expect(mapped.messages).toEqual([
      { role: 'system', content: 'Be precise.' },
      { role: 'user', content: 'Hello' },
    ]);
    expect(mapped.tools?.[0]?.function.name).toBe('lookup');
    expect(mapped.response_format).toEqual({ type: 'json_object' });
    expect(mapped.stream).toBe(true);
  });

  it('maps OpenAI-compatible responses back to internal responses', () => {
    const mapped = fromOpenAiChatResponse({
      choices: [{ message: { content: 'Done' }, finish_reason: 'stop' }],
      usage: { prompt_tokens: 2, completion_tokens: 3, total_tokens: 5 },
    });

    expect(mapped.content).toEqual([{ kind: 'text', text: 'Done' }]);
    expect(mapped.finishReason).toBe('stop');
    expect(mapped.tokenUsage).toEqual({ inputTokens: 2, outputTokens: 3, totalTokens: 5 });
  });

  it('maps internal requests to Anthropic messages requests', () => {
    const mapped = toAnthropicMessagesRequest(request);

    expect(mapped.system).toBe('Be precise.');
    expect(mapped.messages).toEqual([{ role: 'user', content: 'Hello' }]);
    expect(mapped.tools?.[0]?.input_schema).toEqual({ type: 'object' });
    expect(mapped.temperature).toBe(0.2);
  });

  it('maps Anthropic responses back to internal responses', () => {
    const mapped = fromAnthropicMessagesResponse({
      content: [{ type: 'text', text: 'Done' }],
      stop_reason: 'end_turn',
      usage: { input_tokens: 4, output_tokens: 6 },
    });

    expect(mapped.content).toEqual([{ kind: 'text', text: 'Done' }]);
    expect(mapped.finishReason).toBe('end_turn');
    expect(mapped.tokenUsage).toEqual({ inputTokens: 4, outputTokens: 6, totalTokens: 10 });
  });
});
