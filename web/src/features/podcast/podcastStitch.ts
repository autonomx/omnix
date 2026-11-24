import { ApiError } from '../../api/errors';
import { fetchBytes } from '../../api/transport';
import type { Output } from './PodcastWorkspace';
import { stitchedTimeline } from './podcastTimeline';

/**
 * The stitched live preview: the preview lines so far joined into one WAV, so the player plays the episode as it is
 * spoken. Each line's audio is fetched once and kept as PCM; a new line makes a new blob from the kept parts (the
 * blob is built from parts, not one copy of the whole episode), and a blob no longer played is let go.
 */
export const stitchedKey = 'live:stitched-preview';

type WavChunk = {
  data: Uint8Array<ArrayBuffer>;
  sampleRate: number;
  channels: number;
  bitsPerSample: number;
};

function readAscii(view: DataView, offset: number, length: number) {
  let value = '';
  for (let index = 0; index < length && offset + index < view.byteLength; index += 1) value += String.fromCharCode(view.getUint8(offset + index));
  return value;
}

function writeAscii(bytes: Uint8Array, offset: number, value: string) {
  for (let index = 0; index < value.length; index += 1) bytes[offset + index] = value.charCodeAt(index);
}

function parseWavChunk(bytes: Uint8Array<ArrayBuffer>): WavChunk {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (bytes.byteLength >= 44 && readAscii(view, 0, 4) === 'RIFF' && readAscii(view, 8, 4) === 'WAVE') {
    let cursor = 12;
    let sampleRate = 24000;
    let channels = 1;
    let bitsPerSample = 16;
    let data: Uint8Array<ArrayBuffer> | null = null;

    while (cursor + 8 <= view.byteLength) {
      const id = readAscii(view, cursor, 4);
      const size = view.getUint32(cursor + 4, true);
      const start = cursor + 8;
      const end = Math.min(start + size, bytes.byteLength);

      if (id === 'fmt ' && size >= 16 && start + 16 <= view.byteLength) {
        channels = view.getUint16(start + 2, true) || 1;
        sampleRate = view.getUint32(start + 4, true) || 24000;
        bitsPerSample = view.getUint16(start + 14, true) || 16;
      }
      if (id === 'data' && end > start) data = bytes.slice(start, end);
      cursor = end + (size % 2);
    }

    if (data) return { data, sampleRate, channels, bitsPerSample };
  }

  return { data: bytes, sampleRate: 24000, channels: 1, bitsPerSample: 16 };
}

function wavHeader(chunks: readonly WavChunk[]) {
  const first = chunks[0] ?? { sampleRate: 24000, channels: 1, bitsPerSample: 16, data: new Uint8Array() };
  const sampleRate = first.sampleRate || 24000;
  const channels = first.channels || 1;
  const bitsPerSample = first.bitsPerSample || 16;
  const blockAlign = Math.max(1, Math.floor((channels * bitsPerSample) / 8));
  const byteRate = sampleRate * blockAlign;
  const dataSize = chunks.reduce((sum, chunk) => sum + chunk.data.byteLength, 0);
  const bytes = new Uint8Array(44);
  const view = new DataView(bytes.buffer);

  writeAscii(bytes, 0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  writeAscii(bytes, 8, 'WAVE');
  writeAscii(bytes, 12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, channels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitsPerSample, true);
  writeAscii(bytes, 36, 'data');
  view.setUint32(40, dataSize, true);
  return { header: bytes, duration: dataSize / Math.max(1, byteRate) };
}

async function loadAudioBytes(url: string) {
  const response = await fetchBytes(url).catch((error: unknown) => {
    throw error instanceof ApiError ? new Error(`Audio fetch failed: ${error.status}`) : error;
  });
  return new Uint8Array(await response.arrayBuffer());
}

export class PreviewStitcher {
  private chunks = new Map<string, WavChunk>();
  private urls = new Set<string>();
  private run = 0;
  private closed = false;

  /** Every piece so far as one output; null when a newer stitch, a reset or the close overtook it. */
  async stitch(outputs: readonly Output[]): Promise<Output | null> {
    if (this.closed || !outputs.length) return null;
    const run = ++this.run;
    for (const output of outputs) {
      if (!this.chunks.has(output.key)) this.chunks.set(output.key, parseWavChunk(await loadAudioBytes(output.dataUrl)));
      if (run !== this.run) return null;
    }
    const chunks = outputs.map((output) => this.chunks.get(output.key) as WavChunk);
    const wav = wavHeader(chunks);
    const dataUrl = URL.createObjectURL(new Blob([wav.header, ...chunks.map((chunk) => chunk.data)], { type: 'audio/wav' }));
    this.urls.add(dataUrl);
    const dataBytes = Math.max(1, chunks.reduce((sum, chunk) => sum + chunk.data.byteLength, 0));
    const timeline = stitchedTimeline(outputs.map((output, index) => output.line ?? index), chunks.map((chunk) => (chunk.data.byteLength / dataBytes) * wav.duration));
    const last = outputs[outputs.length - 1];
    const summedDuration = outputs.reduce((sum, output) => sum + Number(output.duration || 0), 0);
    return {
      ...last,
      dataUrl,
      key: `${stitchedKey}:${outputs.length}:${last.key}`,
      title: `Live preview stitched ${outputs.length} / ${outputs.length}`,
      live: true,
      duration: wav.duration || summedDuration || last.duration,
      timeline,
    };
  }

  /** Lets go of every stitched blob but those still played or waiting to be. */
  keepOnly(...inUse: Array<string | null | undefined>): void {
    for (const url of this.urls) {
      if (inUse.includes(url)) continue;
      URL.revokeObjectURL(url);
      this.urls.delete(url);
    }
  }

  /** A new run: no stitch under way stands, and nothing kept is reused. */
  reset(): void {
    this.run += 1;
    this.keepOnly();
    this.chunks.clear();
  }

  /** The studio closed: a run still going stitches nothing more. */
  close(): void {
    this.reset();
    this.closed = true;
  }
}
