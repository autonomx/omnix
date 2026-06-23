import { describe, expect, it, vi } from 'vitest';
import { createStaticModelProvider } from './provider';
import { runLiveAssistantTurn } from './live-orchestrator';
import type { SttServiceClient, TtsServiceClient } from './speech-services';

describe('runLiveAssistantTurn', () => {
  it('runs transcription, model response, synthesis, and playback queueing in order', async () => {
    const stt: SttServiceClient = {
      transcribeAudio: vi.fn(async () => ({ text: 'What changed overnight?' })),
    };
    const tts: TtsServiceClient = {
      synthesizeSpeech: vi.fn(async () => ({ audioUrl: 'blob:reply', mimeType: 'audio/wav' })),
    };
    const provider = createStaticModelProvider('local', 'Local model', { streaming: false }, async (request) => ({
      content: [{ kind: 'text', text: `Answering: ${request.messages.at(-1)?.content[0]?.text}` }],
      finishReason: 'stop',
    }));

    const result = await runLiveAssistantTurn({
      sessionId: 'session:voice',
      audio: new ArrayBuffer(4),
      provider,
      model: 'qwen-local',
      stt,
      tts,
      systemPrompt: 'Keep it concise.',
      voice: 'narrator',
      now: () => '2026-06-23T09:00:00Z',
    });

    expect(stt.transcribeAudio).toHaveBeenCalledOnce();
    expect(result.modelRequest.messages[0]).toMatchObject({ role: 'system' });
    expect(result.modelRequest.messages[1]).toMatchObject({ role: 'user' });
    expect(tts.synthesizeSpeech).toHaveBeenCalledWith({
      text: 'Answering: What changed overnight?',
      voice: 'narrator',
      format: 'wav',
    });
    expect(result.playbackItem).toEqual({
      id: 'playback:session:voice:2026-06-23T09:00:00Z',
      text: 'Answering: What changed overnight?',
      createdAt: '2026-06-23T09:00:00Z',
    });
    expect(result.stages).toEqual(['transcribed', 'responded', 'synthesized', 'queued']);
  });
});
