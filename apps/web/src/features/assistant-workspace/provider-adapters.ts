import type { MessageContent, TokenUsage } from './conversation';
import type { ModelRequest, ModelResponse, ProviderMessage, ProviderToolDefinition } from './provider';

export type OpenAiChatMessage = {
  role: ProviderMessage['role'];
  content: string;
};

export type OpenAiToolDefinition = {
  type: 'function';
  function: {
    name: string;
    description: string;
    parameters: Record<string, unknown>;
  };
};

export type OpenAiChatRequest = {
  model: string;
  messages: OpenAiChatMessage[];
  tools?: OpenAiToolDefinition[];
  response_format?: { type: 'json_object' };
  stream?: boolean;
  temperature?: number;
  metadata?: Record<string, unknown>;
};

export type OpenAiChatResponse = {
  choices?: Array<{
    message?: { content?: string };
    finish_reason?: string;
  }>;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
};

export type AnthropicMessage = {
  role: 'user' | 'assistant';
  content: string;
};

export type AnthropicMessagesRequest = {
  model: string;
  system?: string;
  messages: AnthropicMessage[];
  tools?: Array<{
    name: string;
    description: string;
    input_schema: Record<string, unknown>;
  }>;
  stream?: boolean;
  temperature?: number;
  metadata?: Record<string, unknown>;
};

export type AnthropicMessagesResponse = {
  content?: Array<{ type: 'text'; text: string }>;
  stop_reason?: string;
  usage?: {
    input_tokens?: number;
    output_tokens?: number;
  };
};

export function flattenMessageContent(content: MessageContent[]): string {
  return content
    .map((part) => part.text.trim())
    .filter(Boolean)
    .join('\n');
}

function toTextContent(text: string): MessageContent[] {
  return text.trim() ? [{ kind: 'text', text }] : [];
}

function toOpenAiTool(tool: ProviderToolDefinition): OpenAiToolDefinition {
  return {
    type: 'function',
    function: {
      name: tool.name,
      description: tool.description,
      parameters: tool.inputSchema ?? {},
    },
  };
}

function toAnthropicTool(tool: ProviderToolDefinition): NonNullable<AnthropicMessagesRequest['tools']>[number] {
  return {
    name: tool.name,
    description: tool.description,
    input_schema: tool.inputSchema ?? {},
  };
}

function toTokenUsage(usage: OpenAiChatResponse['usage']): TokenUsage | undefined {
  if (!usage) return undefined;
  return {
    inputTokens: usage.prompt_tokens,
    outputTokens: usage.completion_tokens,
    totalTokens: usage.total_tokens,
  };
}

function toAnthropicTokenUsage(usage: AnthropicMessagesResponse['usage']): TokenUsage | undefined {
  if (!usage) return undefined;
  return {
    inputTokens: usage.input_tokens,
    outputTokens: usage.output_tokens,
    totalTokens:
      typeof usage.input_tokens === 'number' && typeof usage.output_tokens === 'number'
        ? usage.input_tokens + usage.output_tokens
        : undefined,
  };
}

export function toOpenAiChatRequest(request: ModelRequest): OpenAiChatRequest {
  return {
    model: request.model,
    messages: request.messages.map((message) => ({
      role: message.role,
      content: flattenMessageContent(message.content),
    })),
    tools: request.tools?.map(toOpenAiTool),
    response_format: request.jsonMode ? { type: 'json_object' } : undefined,
    stream: request.stream,
    temperature: request.temperature,
    metadata: request.metadata,
  };
}

export function fromOpenAiChatResponse(response: OpenAiChatResponse): ModelResponse {
  const firstChoice = response.choices?.[0];
  return {
    content: toTextContent(firstChoice?.message?.content ?? ''),
    finishReason: firstChoice?.finish_reason,
    tokenUsage: toTokenUsage(response.usage),
    raw: response,
  };
}

export function toAnthropicMessagesRequest(request: ModelRequest): AnthropicMessagesRequest {
  const systemMessages = request.messages.filter((message) => message.role === 'system');
  const messages = request.messages
    .filter((message) => message.role !== 'system')
    .map<AnthropicMessage>((message) => ({
      role: message.role === 'assistant' ? 'assistant' : 'user',
      content: flattenMessageContent(message.content),
    }));

  return {
    model: request.model,
    system: systemMessages.map((message) => flattenMessageContent(message.content)).filter(Boolean).join('\n\n') || undefined,
    messages,
    tools: request.tools?.map(toAnthropicTool),
    stream: request.stream,
    temperature: request.temperature,
    metadata: request.metadata,
  };
}

export function fromAnthropicMessagesResponse(response: AnthropicMessagesResponse): ModelResponse {
  return {
    content: toTextContent(response.content?.map((part) => part.text).join('\n') ?? ''),
    finishReason: response.stop_reason,
    tokenUsage: toAnthropicTokenUsage(response.usage),
    raw: response,
  };
}
