import type { LiveSpeechClientEvent } from './realtimeTypes';

export type LiveSpeechTransport = {
  send: (payload: string) => void;
};

export function encodeLiveSpeechEvent(event: LiveSpeechClientEvent): string {
  return JSON.stringify(event);
}

export function sendLiveSpeechEvent(transport: LiveSpeechTransport, event: LiveSpeechClientEvent): void {
  transport.send(encodeLiveSpeechEvent(event));
}

export function sessionUpdateEvent(session: Record<string, unknown>): LiveSpeechClientEvent {
  return { type: 'session.update', session };
}

export function audioAppendEvent(audio: string): LiveSpeechClientEvent {
  return { type: 'input_audio_buffer.append', audio };
}

export function audioCommitEvent(): LiveSpeechClientEvent {
  return { type: 'input_audio_buffer.commit' };
}

export function textItemEvent(text: string): LiveSpeechClientEvent {
  return { type: 'conversation.item.create', item: { type: 'input_text', text } };
}

export function responseCreateEvent(response: Record<string, unknown> = {}): LiveSpeechClientEvent {
  return { type: 'response.create', response };
}

export function responseCancelEvent(): LiveSpeechClientEvent {
  return { type: 'response.cancel' };
}
