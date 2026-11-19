/** Recording the passages a voiceprint is learned from (companion 2.1).
 *
 * The microphone is opened with the call's own processing (echo cancellation, noise suppression, gain), so the print
 * is made from audio that sounds like what a call sends. Each passage goes to the gateway as 16 kHz mono 16-bit WAV;
 * nothing is kept in the browser.
 */
import { downsampleFloat32To16Khz, encodePcm16 } from './live-voice-websocket';

export const VOICEPRINT_SAMPLE_RATE = 16_000;
export const VOICEPRINT_PASSAGE_SECONDS = 7;
/** About twenty seconds of ordinary speech, read in three parts. */
export const VOICEPRINT_PASSAGES = [
  'The morning light came through the kitchen window while the kettle began to whistle on the stove.',
  'On Saturdays I usually walk to the market, pick up some fruit, and stop for a coffee on the way home.',
  'If you ask me a question, I will do my best to answer it clearly, and then we can talk about whatever comes next.',
] as const;

/** The bytes of a 16 kHz mono 16-bit WAV of ``samples`` (floats in -1..1). */
export function wav16kBytes(samples: Float32Array): Uint8Array<ArrayBuffer> {
  const pcm = encodePcm16(samples);
  const bytes = new Uint8Array(44 + pcm.byteLength);
  const view = new DataView(bytes.buffer);
  const ascii = (offset: number, text: string) => {
    for (let index = 0; index < text.length; index += 1) view.setUint8(offset + index, text.charCodeAt(index));
  };
  ascii(0, 'RIFF');
  view.setUint32(4, 36 + pcm.byteLength, true);
  ascii(8, 'WAVE');
  ascii(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, VOICEPRINT_SAMPLE_RATE, true);
  view.setUint32(28, VOICEPRINT_SAMPLE_RATE * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  ascii(36, 'data');
  view.setUint32(40, pcm.byteLength, true);
  bytes.set(pcm, 44);
  return bytes;
}

export function encodeWav16k(samples: Float32Array): Blob {
  return new Blob([wav16kBytes(samples)], { type: 'audio/wav' });
}

/** Record one passage of ``seconds`` from the microphone, as the WAV the gateway expects. */
export async function recordVoiceprintPassage(seconds: number = VOICEPRINT_PASSAGE_SECONDS): Promise<Blob> {
  if (typeof window === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
    throw new Error('This browser cannot use the microphone.');
  }
  const AudioContextCtor = window.AudioContext
    || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioContextCtor) throw new Error('This browser cannot record audio.');
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
  const context = new AudioContextCtor();
  try {
    const source = context.createMediaStreamSource(stream);
    const processor = context.createScriptProcessor(4096, 1, 1);
    const chunks: Float32Array[] = [];
    processor.onaudioprocess = (event) => chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
    source.connect(processor);
    processor.connect(context.destination);
    await new Promise((resolve) => window.setTimeout(resolve, seconds * 1_000));
    processor.disconnect();
    source.disconnect();
    const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    const audio = new Float32Array(total);
    let offset = 0;
    for (const chunk of chunks) {
      audio.set(chunk, offset);
      offset += chunk.length;
    }
    return encodeWav16k(downsampleFloat32To16Khz(audio, context.sampleRate, VOICEPRINT_SAMPLE_RATE));
  } finally {
    stream.getTracks().forEach((track) => track.stop());
    void context.close();
  }
}
