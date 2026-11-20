import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { MemberPortrait } from './MemberPortrait';
import { loadMemberLoop, memberLoop, rememberMemberLoop, resetMemberLoops } from './memberIdleLoops';

const IDLE_PATH = '/api/tts/live-call/portrait-idle';

type Reply = Record<string, unknown>;
let replies: Reply[] = [];
let asked: URL[] = [];
let blobs = 0;

const base64 = (byte: number) => btoa(String.fromCharCode(byte));

beforeEach(() => {
  replies = [];
  asked = [];
  blobs = 0;
  vi.spyOn(URL, 'createObjectURL').mockImplementation(() => `blob:${(blobs += 1)}`);
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const raw = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
    const url = new URL(raw, window.location.origin);
    asked.push(url);
    const body = url.pathname === IDLE_PATH ? replies.shift() ?? { ok: false, code: 'portrait_failed' } : {};
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
  }));
});

afterEach(() => {
  cleanup();
  resetMemberLoops();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("a group call's member idle loops", () => {
  it("asks the gateway once for a guest's loop, naming the guest, and keeps it", async () => {
    replies.push({ ok: true, frame_ms: 80, idle: [base64(1), base64(2)], blink: [base64(3)] });
    await loadMemberLoop('chat:maya', 'char:abhishek', 'char:abhishek');
    await loadMemberLoop('chat:maya', 'char:abhishek', 'char:abhishek');
    expect(asked).toHaveLength(1);
    expect(asked[0].searchParams.get('session_id')).toBe('chat:maya');
    expect(asked[0].searchParams.get('speaker_id')).toBe('char:abhishek');
    expect(memberLoop('char:abhishek')).toEqual({ frameMs: 80, idle: ['blob:1', 'blob:2'], blink: ['blob:3'] });

    await loadMemberLoop('chat:maya', 'char:maya', null); // the chat's own character names no speaker
    expect(asked[1].searchParams.has('speaker_id')).toBe(false);
  });

  it('asks again after a busy service, never after a refusal for good, and forgets a previous chat', async () => {
    replies.push({ ok: false, code: 'portrait_busy' }, { ok: false, code: 'not_a_portrait' });
    await loadMemberLoop('chat:maya', 'char:abhishek', 'char:abhishek');
    await loadMemberLoop('chat:maya', 'char:abhishek', 'char:abhishek');
    await loadMemberLoop('chat:maya', 'char:abhishek', 'char:abhishek');
    expect(asked).toHaveLength(2);
    expect(memberLoop('char:abhishek')).toBeNull();

    rememberMemberLoop('chat:maya', 'char:bea', { frameMs: 40, idle: [new Uint8Array([1])], blink: [] });
    expect(memberLoop('char:bea')).not.toBeNull();
    rememberMemberLoop('chat:other', 'char:theo', { frameMs: 40, idle: [new Uint8Array([1])], blink: [] });
    expect(memberLoop('char:bea')).toBeNull();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:1');
  });

  it("shows a member's picture until its loop is known, then plays the loop", () => {
    vi.useFakeTimers();
    render(<MemberPortrait characterId="char:abhishek" imageUrl="/still.png" label="Abhishek" live={false} streaming />);
    expect(screen.getByAltText('Abhishek').getAttribute('src')).toBe('/still.png');

    act(() => {
      rememberMemberLoop('chat:maya', 'char:abhishek',
        { frameMs: 80, idle: [new Uint8Array([1]), new Uint8Array([2])], blink: [] });
    });
    const frame = screen.getByAltText('Abhishek');
    expect(frame.getAttribute('data-portrait-idle')).toBe('true');
    expect(frame.getAttribute('src')).toBe('blob:1');
    act(() => { vi.advanceTimersByTime(80); });
    expect(screen.getByAltText('Abhishek').getAttribute('src')).toBe('blob:2');
  });
});
