/**
 * The live portrait's binary frames (gateway `/api/tts/live-call/avatar-websocket`, server
 * `app/conversation/portrait_stream_contract.py`): a 4-byte big-endian header length, a UTF-8 JSON
 * header, then a JPEG.
 */

export type PortraitFrameHeader = {
  output_id: string;
  epoch: number;
  segment_id: string;
  /** The frame's position in its segment (phrase), in that phrase's own TTS samples; in the idle loop, its index. */
  offset: number;
  /** The idle loop's frames only: how many there are and their period. */
  count?: number;
  frame_ms?: number;
};

/** The idle loop's frames carry this output id (and segment id). */
export const IDLE_OUTPUT_ID = 'idle';

export type PortraitFrameMessage = {
  header: PortraitFrameHeader;
  jpeg: Uint8Array<ArrayBuffer>;
};

const MAX_HEADER_BYTES = 1024;
const decoder = new TextDecoder();

export function parsePortraitFrame(data: ArrayBuffer): PortraitFrameMessage | null {
  if (data.byteLength < 4) return null;
  const length = new DataView(data).getUint32(0, false);
  if (length > MAX_HEADER_BYTES || 4 + length > data.byteLength) return null;
  let header: unknown;
  try {
    header = JSON.parse(decoder.decode(new Uint8Array(data, 4, length)));
  } catch {
    return null;
  }
  if (!isFrameHeader(header)) return null;
  return { header, jpeg: new Uint8Array(data, 4 + length) };
}

function isFrameHeader(value: unknown): value is PortraitFrameHeader {
  if (!value || typeof value !== 'object') return false;
  const header = value as Record<string, unknown>;
  return typeof header.output_id === 'string'
    && typeof header.epoch === 'number'
    && typeof header.segment_id === 'string'
    && typeof header.offset === 'number' && header.offset >= 0;
}
