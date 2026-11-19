import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixTheme } from '../../../design/theme';
import { encodeWav16k, wav16kBytes } from '../workspace/voiceprint-recording';
import { LiveVoiceprintPanel } from './LiveVoiceprintPanel';

type Call = { method: string; path: string; files: number };

const notEnrolled = { enrolled: false, can_enrol: true, created_at: null, samples: 0, model: null };
const enrolled = { enrolled: true, can_enrol: true, created_at: '2026-11-15T10:00:00+00:00', samples: 3, model: 'titanet-large' };

function serve(initial: object, { enrolFails = false } = {}) {
  const calls: Call[] = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : null;
    const url = new URL(request ? request.url : input.toString(), 'http://localhost');
    const method = request?.method ?? init?.method ?? 'GET';
    const body = init?.body instanceof FormData ? init.body : null;
    calls.push({ method, path: url.pathname, files: body ? body.getAll('files').length : 0 });
    if (method === 'POST' && enrolFails) {
      return Response.json({ detail: { error: 'voices_differ', message: 'The passages did not sound like one voice' } }, { status: 422 });
    }
    if (method === 'POST') return Response.json(enrolled);
    if (method === 'DELETE') return Response.json(notEnrolled);
    return Response.json(initial);
  }));
  return calls;
}

function renderPanel(record = vi.fn(async () => new Blob(['x'], { type: 'audio/wav' }))) {
  render(<MantineProvider theme={omnixTheme} defaultColorScheme="dark"><LiveVoiceprintPanel record={record} /></MantineProvider>);
  return record;
}

afterEach(() => vi.unstubAllGlobals());

describe('LiveVoiceprintPanel', () => {
  it('records three passages and sends them to be learned', async () => {
    const calls = serve(notEnrolled);
    const record = renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Learn my voice' }));

    expect(await screen.findByText('Omnix knows your voice now.')).toBeInTheDocument();
    expect(record).toHaveBeenCalledTimes(3);
    expect(calls.find((call) => call.method === 'POST')).toEqual({ method: 'POST', path: '/api/stt/voiceprint', files: 3 });
    expect(screen.getByRole('button', { name: 'Learn my voice again' })).toBeEnabled();
    expect(screen.getByText(/from 3 passages/)).toBeInTheDocument();
  });

  it('says why a print was refused', async () => {
    serve(notEnrolled, { enrolFails: true });
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Learn my voice' }));

    expect(await screen.findByText('The passages did not sound like one voice')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Learn my voice' })).toBeEnabled();
  });

  it('deletes a print', async () => {
    const calls = serve(enrolled);
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: 'Delete my voiceprint' }));

    expect(await screen.findByText('Your voiceprint is deleted.')).toBeInTheDocument();
    expect(calls.some((call) => call.method === 'DELETE' && call.path === '/api/stt/voiceprint')).toBe(true);
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Delete my voiceprint' })).toBeNull());
  });

  it('offers "Only respond to me" once the voice is learned, off by default, and remembers the choice', async () => {
    window.localStorage.clear();
    serve(enrolled);
    renderPanel();

    const toggle = await screen.findByRole('checkbox', { name: 'Only respond to me' });
    expect(toggle).not.toBeChecked();
    fireEvent.click(toggle);

    expect(toggle).toBeChecked();
    expect(JSON.parse(window.localStorage.getItem('omnix.liveConversation.settings') ?? '{}')).toMatchObject({ onlyRespondToMe: true });
    window.localStorage.clear();
  });

  it('does not offer "Only respond to me" without a voiceprint', async () => {
    serve(notEnrolled);
    renderPanel();

    await screen.findByRole('button', { name: 'Learn my voice' });
    expect(screen.queryByRole('checkbox', { name: 'Only respond to me' })).toBeNull();
  });

  it('offers a guest no enrolment', async () => {
    serve({ ...notEnrolled, can_enrol: false });
    const record = renderPanel();

    expect(await screen.findByText('Sign up to teach Omnix your voice.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /learn my voice/i })).toBeNull();
    expect(record).not.toHaveBeenCalled();
  });
});

describe('wav16kBytes', () => {
  it('writes a 16 kHz mono 16-bit WAV header over the samples', () => {
    const bytes = wav16kBytes(new Float32Array([0, 0.5, -1]));
    const view = new DataView(bytes.buffer);

    expect(encodeWav16k(new Float32Array(3)).type).toBe('audio/wav');
    expect(bytes.byteLength).toBe(44 + 6);
    expect(String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3))).toBe('RIFF');
    expect([view.getUint16(22, true), view.getUint32(24, true), view.getUint16(34, true), view.getUint32(40, true)])
      .toEqual([1, 16_000, 16, 6]);
    expect([view.getInt16(44, true), view.getInt16(46, true), view.getInt16(48, true)]).toEqual([0, 16383, -32767]);
  });
});
