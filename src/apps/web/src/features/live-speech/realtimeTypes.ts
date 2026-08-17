export type LiveSpeechEventType =
  | 'session.created'
  | 'session.updated'
  | 'input_audio_buffer.speech_started'
  | 'input_audio_buffer.speech_stopped'
  | 'conversation.item.created'
  | 'conversation.item.input_audio_transcription.delta'
  | 'conversation.item.input_audio_transcription.completed'
  | 'response.created'
  | 'response.text.delta'
  | 'response.output_audio.delta'
  | 'response.output_audio.done'
  | 'response.output_audio_transcript.done'
  | 'response.metrics'
  | 'response.done'
  | 'error';

export type LiveSpeechWireEvent = {
  type: LiveSpeechEventType;
  event_id?: string;
  session_id?: string;
  turn_id?: string | null;
  response_id?: string | null;
  generation?: number;
  [key: string]: unknown;
};

export type LiveSpeechClientEvent =
  | { type: 'session.update'; session: Record<string, unknown> }
  | { type: 'input_audio_buffer.append'; audio: string }
  | { type: 'input_audio_buffer.commit' }
  | { type: 'conversation.item.create'; item: Record<string, unknown> }
  | { type: 'response.create'; response?: Record<string, unknown> }
  | { type: 'response.cancel' };

export function defaultRealtimeUrl(locationLike: Pick<Location, 'protocol' | 'host'> = window.location): string {
  const protocol = locationLike.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${locationLike.host}/v1/realtime`;
}

export function pcm16ToBase64(pcm: Int16Array): string {
  const bytes = new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength);
  let binary = '';
  const chunkSize = 8192;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return btoa(binary);
}
