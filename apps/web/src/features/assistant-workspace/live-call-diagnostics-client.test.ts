import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  createLiveCallDiagnosticsReporter,
  sanitizeDiagnosticDetails,
} from './live-call-diagnostics-client';

describe('live call diagnostics client', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it('emits a sanitized local diagnostic event before nonblocking upload', async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const listener = vi.fn();
    window.addEventListener('omnix:live-call-diagnostic', listener);
    const reporter = createLiveCallDiagnosticsReporter('live-call:test');

    reporter.record('llm_text_chunk_received', {
      transcript: 'private text',
      text_length: 12,
    }, 'controller');
    await reporter.close();

    const event = listener.mock.calls
      .map((call) => call[0] as CustomEvent)
      .find((candidate) => candidate.detail.event === 'llm_text_chunk_received');
    expect(event?.detail).toEqual(expect.objectContaining({
      traceId: 'live-call:test',
      source: 'controller',
      event: 'llm_text_chunk_received',
      details: expect.objectContaining({
        transcript_chars: 12,
        text_length: 12,
      }),
    }));
    expect(event?.detail.details.transcript).toBeUndefined();
    expect(fetchMock).toHaveBeenCalled();
  });

  it('keeps transcript sanitization policy unchanged', () => {
    expect(sanitizeDiagnosticDetails({ transcript: 'secret' }, 'none')).toEqual({});
    expect(sanitizeDiagnosticDetails({ transcript: 'secret' }, 'redacted')).toEqual({ transcript: '[redacted]' });
    expect(sanitizeDiagnosticDetails({ transcript: 'secret' }, 'lengths_only')).toEqual({ transcript_chars: 6 });
  });
});
