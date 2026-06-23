import type { MessageContent } from './conversation';
import type { ModelProvider, ModelRequest, ModelResponse } from './provider';
import type { PlaybackItem } from './playback';
import type { SpeechAudioInput, SttServiceClient, SttTranscriptionResponse, TtsServiceClient, TtsSynthesisResponse } from './speech-services';

export type LiveAssistantTurnInput = {
  sessionId: string;
  audio: SpeechAudioInput;
  provider: ModelProvider;
  model: string;
  stt: SttServiceClient;
  tts: TtsServiceClient;
  systemPrompt?: string;
  voice?: string;
  now?: () => string;
};

export type LiveAssistantTurnResult = {
  sessionId: string;
  transcript: SttTranscriptionResponse;
  modelRequest: ModelRequest;
  modelResponse: ModelResponse;
  assistantText: string;
  synthesis: TtsSynthesisResponse;
  playbackItem: PlaybackItem;
  stages: Array<'transcribed' | 'responded' | 'synthesized' | 'queued'>;
};

export async function runLiveAssistantTurn(input: LiveAssistantTurnInput): Promise<LiveAssistantTurnResult> {
  const now = input.now ?? (() => new Date().toISOString());
  const transcript = await input.stt.transcribeAudio({ audio: input.audio });
  const messages = [
    ...(input.systemPrompt
      ? [
          {
            role: 'system' as const,
            content: [{ kind: 'text' as const, text: input.systemPrompt }],
          },
        ]
      : []),
    {
      role: 'user' as const,
      content: [{ kind: 'text' as const, text: transcript.text }],
    },
  ];
  const modelRequest: ModelRequest = {
    provider: input.provider.id,
    model: input.model,
    messages,
    metadata: {
      sessionId: input.sessionId,
      inputMode: 'voice',
    },
  };
  const modelResponse = await input.provider.execute(modelRequest);
  const assistantText = flattenModelResponseText(modelResponse.content);
  const synthesis = await input.tts.synthesizeSpeech({
    text: assistantText,
    voice: input.voice,
    format: 'wav',
  });
  const createdAt = now();
  const playbackItem: PlaybackItem = {
    id: `playback:${input.sessionId}:${createdAt}`,
    text: assistantText,
    createdAt,
  };

  return {
    sessionId: input.sessionId,
    transcript,
    modelRequest,
    modelResponse,
    assistantText,
    synthesis,
    playbackItem,
    stages: ['transcribed', 'responded', 'synthesized', 'queued'],
  };
}

export function flattenModelResponseText(content: MessageContent[]): string {
  return content
    .map((item) => item.text.trim())
    .filter(Boolean)
    .join('\n')
    .trim();
}
