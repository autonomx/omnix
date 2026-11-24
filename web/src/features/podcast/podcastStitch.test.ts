import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { PreviewStitcher } from './podcastStitch';

/** A one-channel, 16-bit WAV of `samples` samples at 1 kHz (so a sample is a millisecond). */
function wav(samples: number): ArrayBuffer {
  const bytes = new Uint8Array(44 + samples * 2);
  const view = new DataView(bytes.buffer);
  const ascii = (offset: number, text: string) => [...text].forEach((char, index) => { bytes[offset + index] = char.charCodeAt(0); });
  ascii(0, 'RIFF'); view.setUint32(4, 36 + samples * 2, true); ascii(8, 'WAVE');
  ascii(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, 1000, true); view.setUint32(28, 2000, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  ascii(36, 'data'); view.setUint32(40, samples * 2, true);
  return bytes.buffer;
}

const piece = (index: number) => ({ dataUrl: `/api/assets/line-${index}/content`, duration: 0.5, jobId: `job-${index}`, key: `live:${index}`, title: '', live: true, line: index });

let fetched: string[] = [];
let blobs: Blob[] = [];
let revoked: string[] = [];

beforeEach(() => {
  fetched = [];
  blobs = [];
  revoked = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    fetched.push(new URL(String(input), 'http://localhost').pathname);
    return new Response(wav(500));
  }));
  vi.spyOn(URL, 'createObjectURL').mockImplementation((blob) => {
    blobs.push(blob as Blob);
    return `blob:${blobs.length}`;
  });
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation((url) => { revoked.push(url); });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('the stitched live preview', () => {
  it('fetches each line once, and joins them into one WAV with each line\'s start', async () => {
    const stitcher = new PreviewStitcher();
    await stitcher.stitch([piece(0)]);
    await stitcher.stitch([piece(0), piece(1)]);
    const joined = await stitcher.stitch([piece(0), piece(1), piece(2)]);

    expect(fetched).toEqual(['/api/assets/line-0/content', '/api/assets/line-1/content', '/api/assets/line-2/content']);
    expect(joined).toMatchObject({ dataUrl: 'blob:3', live: true, duration: 1.5, title: 'Live preview stitched 3 / 3' });
    expect(joined?.timeline).toEqual([{ line: 0, start: 0 }, { line: 1, start: 0.5 }, { line: 2, start: 1 }]);
    expect(blobs[2].size).toBe(44 + 3 * 1000);
  });

  it('lets go of the blobs no longer played, and of all of them on a reset', async () => {
    const stitcher = new PreviewStitcher();
    for (let count = 1; count <= 3; count += 1) await stitcher.stitch(Array.from({ length: count }, (_, index) => piece(index)));
    stitcher.keepOnly('blob:2', 'blob:3');
    expect(revoked).toEqual(['blob:1']);
    stitcher.reset();
    expect(revoked).toEqual(['blob:1', 'blob:2', 'blob:3']);
  });

  it('stitches nothing once overtaken or closed', async () => {
    const stitcher = new PreviewStitcher();
    const overtaken = stitcher.stitch([piece(0)]);
    const newer = stitcher.stitch([piece(0), piece(1)]);
    await expect(overtaken).resolves.toBeNull();
    await expect(newer).resolves.not.toBeNull();

    stitcher.close();
    await expect(stitcher.stitch([piece(0), piece(1), piece(2)])).resolves.toBeNull();
    expect(blobs).toHaveLength(1);
  });
});
