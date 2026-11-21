import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { LiveConversationProfile } from '../chat/liveConversationProfileClient';
import {
  ASSISTANT_AUDIO_PLAYBACK_STATE_EVENT,
  ASSISTANT_LIVE_VOICE_CALL_CONNECTED_EVENT,
  ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT,
  ASSISTANT_VOICE_INTERRUPT_EVENT,
  ASSISTANT_VOICE_PERF_EVENT,
  emitOmnixEvent,
} from '../../../events/bus';
import { companionInitiativeArbiter } from './companion-initiative-arbiter';
import { liveCallPresentationStore } from './live-call-presentation-store';
import {
  addCallGuest,
  callSceneGuests,
  callSceneHasGuests,
  callSceneKnownEmpty,
  callScenePhraseSource,
  callSceneStore,
  clearCallScene,
  loadCallScene,
  removeCallGuest,
  SCENE_LINE_REASON,
  SCENE_REACTION_REASON,
  SCENE_TALK_REASON,
  sceneSpeakerFrom,
  sceneSpeakerVoiceId,
  type CallSceneGuest,
  type CallSceneMember,
  type CallSceneView,
} from './live-call-scene';
import { initializeLiveCallTasksController, liveCallTasksStore } from './live-call-tasks-controller';
import { initializeLiveConversationInitiativeController } from './live-conversation-initiative-controller';
import { liveConversationStore } from './live-conversation-store';
import { appendDeliveryPhrase, advanceDeliveryLedger, createLiveVoiceDeliveryLedger, handleDeliveryDiagnostic, noteProactiveDelivery } from './live-voice-delivery-ledger';

const SCENE_PATH = '/api/chat/sessions/s1/scene';
const RUNTIME_PATH = '/api/chat/sessions/s1/live-call/runtime';
const STREAM_PATH = '/api/chat/sessions/s1/live-call/greeting/stream';
const DELIVERY_PATH = '/api/chat/sessions/s1/live-conversation/proactive/delivery';
const RELEASE_PATH = '/api/chat/sessions/s1/live-conversation/proactive/release';
const REACTION_TURN = 'scene-reaction:bea:0123456789abcdef0123456789abcdef';

const HOST = { character_id: 'mara', display_name: 'Mara Quinn', role: 'host', seat: 0 } as CallSceneMember;
const BEA = { character_id: 'bea', display_name: 'Bea Hart', role: 'guest', seat: 1 } as CallSceneMember;
const THEO = { character_id: 'theo', display_name: 'Theo Lark', role: 'guest', seat: 2 } as CallSceneMember;

function view(members: CallSceneMember[] = [HOST, BEA]): CallSceneView {
  return { available: true, reason: 'ready', max_guests: 2, members } as CallSceneView;
}

function guest(patch: Partial<CallSceneGuest> = {}): CallSceneGuest {
  return {
    character_id: 'bea',
    display_name: 'Bea Hart',
    voice_asset_id: 'voice:bea',
    voice_speaker_id: null,
    ...patch,
  } as CallSceneGuest;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

function sse(events: unknown[]): Response {
  return new Response(events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join(''), {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

type Call = { url: URL; method: string; body: unknown };

let scene: CallSceneView = view();
let reacts = true;
// Lines the server still lets the members say; the next ask after them is refused (the thread is at its max).
let linesLeft = 0;
let lineCount = 0;
// A delivery waits on this when set, so a test can see what the call does before the commit resolves.
let deliveryGate: Promise<void> | null = null;
// An add waits on this when set, so a test can end the call while the add is still in flight.
let addGate: Promise<void> | null = null;
let calls: Call[] = [];
let perf: string[] = [];
let disposers: Array<() => void> = [];

function callsTo(path: string, method?: string): Call[] {
  return calls.filter((call) => call.url.pathname === path && (!method || call.method === method));
}

const recordPerf = (event: Event) => {
  const stage = (event as CustomEvent<{ stage?: string }>).detail?.stage;
  if (stage) perf.push(stage);
};

beforeEach(() => {
  scene = view();
  reacts = true;
  linesLeft = 0;
  lineCount = 0;
  deliveryGate = null;
  addGate = null;
  noteProactiveDelivery('s1', null);
  calls = [];
  perf = [];
  window.addEventListener(ASSISTANT_VOICE_PERF_EVENT, recordPerf);
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : null;
    const raw = typeof input === 'string' || input instanceof URL ? input.toString() : input.url;
    const url = new URL(raw, window.location.origin);
    const method = (init?.method ?? request?.method ?? 'GET').toUpperCase();
    const text = typeof init?.body === 'string' ? init.body : request ? await request.clone().text() : '';
    calls.push({ url, method, body: text ? JSON.parse(text) : null });
    if (url.pathname === SCENE_PATH) return json(scene);
    if (url.pathname === `${SCENE_PATH}/guests` && method === 'POST') {
      const body = JSON.parse(text) as { character_id: string };
      if (body.character_id === 'zed') return json({ detail: 'scene_full' }, 409);
      if (addGate) await addGate;
      scene = view([HOST, BEA, THEO]);
      return json(scene);
    }
    if (url.pathname.startsWith(`${SCENE_PATH}/guests`) && method === 'DELETE') {
      scene = view([HOST]);
      return json(scene);
    }
    if (url.pathname === RUNTIME_PATH) return json({ session_id: 's1', scene_guests: [guest()] });
    if (url.pathname === STREAM_PATH) {
      const reason = url.searchParams.get('initiative_reason');
      if (reason === SCENE_LINE_REASON || reason === SCENE_TALK_REASON) {
        if (linesLeft <= 0) return json({ detail: `${reason}_not_due` }, 409);
        linesLeft -= 1;
        lineCount += 1;
        const kind = reason === SCENE_LINE_REASON ? 'line' : 'talk';
        const speaker = lineCount % 2 ? 'bea' : 'mara';
        return sse([
          { type: 'initiative', turn_id: `scene-${kind}:${speaker}:msg:r1:${lineCount}`, initiative_reason: `${reason}:${speaker}` },
          { type: 'complete', content: `Line ${lineCount}. And then some.` },
          { type: 'done' },
        ]);
      }
      if (!reacts) return json({ detail: 'scene_reaction_declined' }, 409);
      return sse([
        { type: 'initiative', turn_id: REACTION_TURN, initiative_reason: 'scene_reaction:bea' },
        { type: 'complete', content: 'I was there too. The rain never stopped.' },
        { type: 'done' },
      ]);
    }
    if (url.pathname === DELIVERY_PATH) {
      if (deliveryGate) await deliveryGate;
      return json({ message_id: 'p1', committed: true });
    }
    if (url.pathname === RELEASE_PATH) return json({ released: true });
    return json(null);
  }));
  liveConversationStore.reset();
  liveCallTasksStore.resetForTests();
  liveCallPresentationStore.resetForTests();
  callSceneStore.resetForTests();
  companionInitiativeArbiter.reset();
});

afterEach(() => {
  disposers.forEach((dispose) => dispose());
  disposers = [];
  window.removeEventListener(ASSISTANT_VOICE_PERF_EVENT, recordPerf);
  vi.unstubAllGlobals();
  liveConversationStore.reset();
  liveCallTasksStore.resetForTests();
  liveCallPresentationStore.resetForTests();
  callSceneStore.resetForTests();
});

describe("a scene turn's voice", () => {
  it("speaks in the named guest's voice, a cloned speaker first, and keeps the call's voice otherwise", () => {
    const guests = [guest(), guest({ character_id: 'theo', voice_asset_id: 'voice:theo', voice_speaker_id: 'speaker:theo' })];

    expect(sceneSpeakerVoiceId('bea', guests, 'voice:mara')).toBe('voice:bea');
    expect(sceneSpeakerVoiceId('theo', guests, 'voice:mara')).toBe('speaker:theo');
    expect(sceneSpeakerVoiceId(null, guests, 'voice:mara')).toBe('voice:mara');
    // A guest the runtime does not list yet, or one without a voice, keeps the call's voice.
    expect(sceneSpeakerVoiceId('zed', guests, 'voice:mara')).toBe('voice:mara');
    expect(sceneSpeakerVoiceId('bea', [guest({ voice_asset_id: null })], 'voice:mara')).toBe('voice:mara');
    expect(sceneSpeakerVoiceId('bea', undefined, null)).toBeNull();
  });

  it('reads the speaker from the response header; none, or an empty one, is the host', () => {
    expect(sceneSpeakerFrom(new Response('', { headers: { 'X-Omnix-Scene-Speaker': 'bea' } }))).toBe('bea');
    expect(sceneSpeakerFrom(new Response('', { headers: { 'X-Omnix-Scene-Speaker': ' ' } }))).toBeNull();
    expect(sceneSpeakerFrom(new Response(''))).toBeNull();
  });
});

describe('the call members', () => {
  it("loads the chat's scene and adds and removes a guest through its routes", async () => {
    await loadCallScene('s1');
    expect(callSceneGuests().map((member) => member.character_id)).toEqual(['bea']);
    expect(callSceneHasGuests('s1')).toBe(true);
    expect(callSceneHasGuests('other')).toBe(false);

    await addCallGuest('s1', 'theo');
    expect(callsTo(`${SCENE_PATH}/guests`, 'POST')[0].body).toEqual({ character_id: 'theo' });
    expect(callSceneGuests().map((member) => member.character_id)).toEqual(['bea', 'theo']);
    // The runtime is read again so the new guest's voice is known for its first turn.
    expect(callsTo(RUNTIME_PATH).length).toBeGreaterThanOrEqual(1);
    // ...and the full-screen call is told, so the guest's tile shows its face.
    expect(callSceneStore.getState().guests?.map((entry) => entry.character_id)).toEqual(['bea']);

    await removeCallGuest('s1', 'bea');
    expect(callsTo(`${SCENE_PATH}/guests/bea`, 'DELETE')).toHaveLength(1);
    expect(callSceneHasGuests('s1')).toBe(false);
    expect(callSceneStore.getState().changing).toBeNull();
  });

  it('clears every guest when a call ends, so the next call starts with the host alone', async () => {
    expect(callSceneKnownEmpty('s1')).toBe(false);
    await loadCallScene('s1');
    expect(callSceneKnownEmpty('s1')).toBe(false);

    await clearCallScene('s1');
    expect(callsTo(`${SCENE_PATH}/guests`, 'DELETE')).toHaveLength(1);
    expect(callSceneGuests()).toEqual([]);
    expect(callSceneStore.getState().guests).toEqual([]);
    expect(callSceneKnownEmpty('s1')).toBe(true);
    // A chat the panel has not read is not known to be empty: its call's end still clears it.
    expect(callSceneKnownEmpty('other')).toBe(false);
  });

  it('lets an add still in flight land before a call that ends clears the guests', async () => {
    await loadCallScene('s1');
    let release = (): void => undefined;
    addGate = new Promise<void>((resolve) => { release = resolve; });
    const adding = addCallGuest('s1', 'theo');
    const clearing = clearCallScene('s1');
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(callsTo(`${SCENE_PATH}/guests`, 'DELETE')).toHaveLength(0);

    release();
    await Promise.all([adding, clearing]);
    // The clear went out after the add was answered, so the guest the add seated does not stay for the next call.
    expect(callsTo(`${SCENE_PATH}/guests`).map((call) => call.method)).toEqual(['POST', 'DELETE']);
    expect(callSceneGuests()).toEqual([]);
    expect(callSceneStore.getState().guests).toEqual([]);
  });

  it("keeps a call's names for speech recognition while the panel shows another chat", async () => {
    await loadCallScene('s1');
    const source = callScenePhraseSource('s1');
    expect(source.current()).toEqual(['Mara Quinn', 'Bea Hart']);

    await loadCallScene('s2');
    expect(source.current()).toEqual(['Mara Quinn', 'Bea Hart']);

    scene = view([HOST]);
    await loadCallScene('s1');
    expect(source.current()).toEqual(['Mara Quinn']);
  });

  it('shows no members when the response is not a scene', async () => {
    scene = { detail: 'proxy page' } as unknown as CallSceneView;
    await loadCallScene('s1');

    expect(callSceneStore.getState().scene).toBeNull();
    expect(callSceneGuests()).toEqual([]);
    expect(callSceneHasGuests('s1')).toBe(false);
  });

  it("shows the server's refusal in words and keeps the members", async () => {
    await loadCallScene('s1');
    await addCallGuest('s1', 'zed');

    expect(callSceneStore.getState().error).toBe('The call already has four guests.');
    expect(callSceneStore.getState().changing).toBeNull();
    expect(callSceneGuests().map((member) => member.character_id)).toEqual(['bea']);
  });
});

function quietProfile(patch: Partial<LiveConversationProfile> = {}): LiveConversationProfile {
  // Social initiative is off and its idle threshold far away: only a scene turn can speak.
  return {
    initiative_mode: 'off',
    idle_threshold_ms: 600_000,
    max_idle_prompts: 0,
    long_pause_behavior: 'wait',
    presence_preset: 'calm',
    conversation_stance: 'companion',
    ...patch,
  } as unknown as LiveConversationProfile;
}

async function startCall(profile: LiveConversationProfile = quietProfile()): Promise<void> {
  await loadCallScene('s1');
  liveCallPresentationStore.update({ autoSpeak: true });
  liveConversationStore.dispatch({ type: 'profile', profile });
  disposers.push(initializeLiveCallTasksController());
  disposers.push(initializeLiveConversationInitiativeController());
  liveConversationStore.dispatch({ type: 'session', sessionId: 's1' });
  liveConversationStore.dispatch({ type: 'conversation', event: { type: 'connection', value: 'connected' } });
  emitOmnixEvent(ASSISTANT_LIVE_VOICE_CALL_CONNECTED_EVENT, { token: 1, timestamp: '2026-11-15T10:00:00Z' });
}

function speakingStarts(): void {
  liveConversationStore.dispatch({ type: 'conversation', event: { type: 'assistant_turn', value: 'speaking' } });
}

function speakingEnds(): void {
  liveConversationStore.dispatch({ type: 'conversation', event: { type: 'assistant_turn', value: 'idle' } });
}

function replyPlays(): void {
  speakingStarts();
  speakingEnds();
}

function userSpeaks(): void {
  emitOmnixEvent(ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT, {
    timestamp: new Date().toISOString(), rms: 0.05, assistantSpeaking: false, assistantOwnsFloor: false,
  });
}

describe('a guest reacting to a reply', () => {
  it('asks once after a reply ends, plays the reaction and commits it under its own turn', async () => {
    await startCall();
    replyPlays();

    await vi.waitFor(() => expect(callsTo(STREAM_PATH)).toHaveLength(1), { timeout: 4_000 });
    const stream = callsTo(STREAM_PATH)[0];
    expect(stream.url.searchParams.get('purpose')).toBe('proactive_reengagement');
    expect(stream.url.searchParams.get('initiative_reason')).toBe(SCENE_REACTION_REASON);
    // The server builds the reaction from the conversation; the call sends no summary of its own.
    expect(stream.url.searchParams.has('state_summary')).toBe(false);

    replyPlays();
    await vi.waitFor(() => expect(callsTo(DELIVERY_PATH)).toHaveLength(1));
    expect(callsTo(DELIVERY_PATH)[0].body).toEqual({
      turn_id: REACTION_TURN,
      content: 'I was there too. The rain never stopped.',
      initiative_reason: 'scene_reaction:bea',
      delivery_status: 'completed',
    });
    await vi.waitFor(() => expect(companionInitiativeArbiter.snapshot().lastDeliveredSource).toBe('scene'));
    // The reaction ending is not a reply to react to.
    await new Promise((resolve) => setTimeout(resolve, 1_200));
    expect(callsTo(STREAM_PATH)).toHaveLength(1);
  });

  it('treats a refusal as nobody reacting', async () => {
    reacts = false;
    await startCall();
    replyPlays();

    await vi.waitFor(() => expect(perf).toContain('scene_reaction_skipped'), { timeout: 4_000 });
    expect(perf).not.toContain('initiative_generation_failed');
    expect(callsTo(DELIVERY_PATH)).toHaveLength(0);
  });

  it('asks nothing without a guest', async () => {
    scene = view([HOST]);
    await startCall();
    replyPlays();

    await new Promise((resolve) => setTimeout(resolve, 1_600));
    expect(callsTo(STREAM_PATH)).toHaveLength(0);
  });

  it('asks nothing once the person speaks after the reply', async () => {
    await startCall();
    replyPlays();
    userSpeaks();

    await new Promise((resolve) => setTimeout(resolve, 1_600));
    expect(callsTo(STREAM_PATH)).toHaveLength(0);
  });

  it('asks nothing while the call is quiet', async () => {
    await startCall();
    liveCallPresentationStore.update({ companionQuiet: true });
    replyPlays();

    await vi.waitFor(() => expect(perf).toContain('scene_reaction_suppressed'), { timeout: 3_000 });
    expect(callsTo(STREAM_PATH)).toHaveLength(0);
  });
});

describe('the members talking to each other', () => {
  const talkProfile = (patch: Partial<LiveConversationProfile> = {}) => quietProfile({
    scene_talk_enabled: true, scene_talk_level: 'often', max_initiatives_per_hour: 4, ...patch,
  });

  it('asks for the next line only once the last one is committed, and a refusal ends the thread', async () => {
    linesLeft = 2;
    await startCall(talkProfile());
    replyPlays();
    await vi.waitFor(() => expect(callsTo(STREAM_PATH)).toHaveLength(1), { timeout: 4_000 });
    expect(callsTo(STREAM_PATH)[0].url.searchParams.get('initiative_reason')).toBe(SCENE_LINE_REASON);
    expect(callsTo(STREAM_PATH)[0].url.searchParams.has('scene_talk_switched_off')).toBe(false);

    let open: () => void = () => undefined;
    deliveryGate = new Promise((resolve) => { open = resolve; });
    replyPlays();  // the first line plays to the end
    await vi.waitFor(() => expect(callsTo(DELIVERY_PATH)).toHaveLength(1));
    await new Promise((resolve) => setTimeout(resolve, 1_600));
    expect(callsTo(STREAM_PATH)).toHaveLength(1);  // nothing is asked while the commit is in flight

    open();
    await vi.waitFor(() => expect(callsTo(STREAM_PATH)).toHaveLength(2), { timeout: 4_000 });
    expect(callsTo(STREAM_PATH)[1].url.searchParams.get('initiative_reason')).toBe(SCENE_LINE_REASON);
    deliveryGate = null;
    replyPlays();
    await vi.waitFor(() => expect(callsTo(DELIVERY_PATH)).toHaveLength(2));
    expect(callsTo(DELIVERY_PATH)[1].body).toMatchObject({ turn_id: 'scene-line:mara:msg:r1:2', delivery_status: 'completed' });

    await vi.waitFor(() => expect(perf).toContain('scene_talk_skipped'), { timeout: 4_000 });
    await new Promise((resolve) => setTimeout(resolve, 1_600));
    expect(callsTo(STREAM_PATH)).toHaveLength(3);
    expect(callsTo(DELIVERY_PATH)).toHaveLength(2);
  }, 15_000);

  it('asks for the single reaction, and says so, when "Let them talk" is off on this call', async () => {
    await startCall(talkProfile());
    liveCallPresentationStore.update({ sceneTalkOn: false });
    replyPlays();

    await vi.waitFor(() => expect(callsTo(STREAM_PATH)).toHaveLength(1), { timeout: 4_000 });
    const stream = callsTo(STREAM_PATH)[0];
    expect(stream.url.searchParams.get('initiative_reason')).toBe(SCENE_REACTION_REASON);
    expect(stream.url.searchParams.get('scene_talk_switched_off')).toBe('true');
  });

  it('holds lines back while the person is muted', async () => {
    linesLeft = 1;
    await startCall(talkProfile());
    liveCallPresentationStore.update({ micMuted: true });
    replyPlays();

    await vi.waitFor(() => expect(perf).toContain('scene_reaction_suppressed'), { timeout: 3_000 });
    expect(callsTo(STREAM_PATH)).toHaveLength(0);
  });

  it('sends the words the person heard when they cut a line off, and asks no next line', async () => {
    linesLeft = 2;
    await startCall(talkProfile());
    replyPlays();
    await vi.waitFor(() => expect(callsTo(STREAM_PATH)).toHaveLength(1), { timeout: 4_000 });
    await vi.waitFor(() => expect(perf).toContain('initiative_generation_completed'));

    // The line's audio: its first phrase played to the end, the second was cut.
    const ledger = createLiveVoiceDeliveryLedger(1_000);
    appendDeliveryPhrase(ledger, 0, ' Line 1. ');
    appendDeliveryPhrase(ledger, 1, 'And then some.');
    handleDeliveryDiagnostic(ledger, 'phrase_buffered', { phrase_index: 0, playback_samples: 500 });
    handleDeliveryDiagnostic(ledger, 'phrase_buffered', { phrase_index: 1, playback_samples: 500 });
    advanceDeliveryLedger(ledger, 700);
    noteProactiveDelivery('s1', ledger);
    speakingStarts();
    window.dispatchEvent(new CustomEvent(ASSISTANT_VOICE_INTERRUPT_EVENT));

    await vi.waitFor(() => expect(callsTo(DELIVERY_PATH)).toHaveLength(1));
    expect(callsTo(DELIVERY_PATH)[0].body).toMatchObject({
      turn_id: 'scene-line:bea:msg:r1:1',
      delivery_status: 'interrupted',
      heard_text: 'Line 1.',
      interrupted_at_phrase: 1,
    });
    speakingEnds();
    await new Promise((resolve) => setTimeout(resolve, 1_600));
    expect(callsTo(STREAM_PATH)).toHaveLength(1);
  });

  // The 2026-11-20 call: the person spoke as each line began, the audio controller stopped it, and the line was
  // committed "completed" only when the next reply's audio ended, a whole exchange later.
  function linePlays(heard: string | null): void {
    const ledger = createLiveVoiceDeliveryLedger(1_000);
    appendDeliveryPhrase(ledger, 0, ' Line 1. ');
    if (heard !== null) {
      handleDeliveryDiagnostic(ledger, 'phrase_buffered', { phrase_index: 0, playback_samples: 500 });
      advanceDeliveryLedger(ledger, 600);
    }
    noteProactiveDelivery('s1', ledger);
    emitOmnixEvent(ASSISTANT_AUDIO_PLAYBACK_STATE_EVENT, { speaking: true, source: 'unified-live-voice', kind: 'greeting' });
    speakingStarts();
  }

  it('settles a line the person speaks over at once, as interrupted, not when the next reply ends', async () => {
    linesLeft = 2;
    await startCall(talkProfile());
    replyPlays();
    await vi.waitFor(() => expect(perf).toContain('initiative_generation_completed'), { timeout: 4_000 });

    linePlays('Line 1.');
    userSpeaks();
    await vi.waitFor(() => expect(callsTo(DELIVERY_PATH)).toHaveLength(1));
    expect(callsTo(DELIVERY_PATH)[0].body).toMatchObject({
      turn_id: 'scene-line:bea:msg:r1:1', delivery_status: 'interrupted', heard_text: 'Line 1.',
    });
    emitOmnixEvent(ASSISTANT_AUDIO_PLAYBACK_STATE_EVENT, { speaking: false, source: 'unified-live-voice', kind: 'greeting' });
    replyPlays();  // the answer to the person
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(callsTo(DELIVERY_PATH)).toHaveLength(1);
  });

  it('drops a line stopped before a word of it was heard and gives its lease back', async () => {
    linesLeft = 1;
    await startCall(talkProfile());
    replyPlays();
    await vi.waitFor(() => expect(perf).toContain('initiative_generation_completed'), { timeout: 4_000 });

    linePlays(null);
    userSpeaks();
    await vi.waitFor(() => expect(callsTo(RELEASE_PATH, 'POST')).toHaveLength(1));
    expect(callsTo(RELEASE_PATH)[0].body).toEqual({ turn_id: 'scene-line:bea:msg:r1:1' });
    replyPlays();
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(callsTo(DELIVERY_PATH)).toHaveLength(0);
  });

  it("commits a line when its own audio ends, though the call's speaking state stays set", async () => {
    linesLeft = 1;
    await startCall(talkProfile());
    replyPlays();
    await vi.waitFor(() => expect(perf).toContain('initiative_generation_completed'), { timeout: 4_000 });

    linePlays('Line 1.');
    emitOmnixEvent(ASSISTANT_AUDIO_PLAYBACK_STATE_EVENT, { speaking: false, source: 'unified-live-voice', kind: 'greeting' });
    await vi.waitFor(() => expect(callsTo(DELIVERY_PATH)).toHaveLength(1));
    expect(callsTo(DELIVERY_PATH)[0].body).toMatchObject({ turn_id: 'scene-line:bea:msg:r1:1', delivery_status: 'completed' });
  });

  it('gives the lease back for a line dropped before it played', async () => {
    linesLeft = 1;
    await startCall(talkProfile());
    replyPlays();
    await vi.waitFor(() => expect(perf).toContain('initiative_generation_completed'), { timeout: 4_000 });

    userSpeaks();
    await vi.waitFor(() => expect(callsTo(RELEASE_PATH, 'POST')).toHaveLength(1));
    expect(callsTo(RELEASE_PATH)[0].body).toEqual({ turn_id: 'scene-line:bea:msg:r1:1' });
    expect(callsTo(DELIVERY_PATH)).toHaveLength(0);
  });

  it('lets a member start the others talking after the level\'s silence, once per silence', async () => {
    linesLeft = 0;  // the start is refused: not due yet on the server
    vi.spyOn(performance, 'now').mockReturnValue(1_000);
    await startCall(talkProfile({ initiative_mode: 'gentle' }));
    await new Promise((resolve) => setTimeout(resolve, 1_000));
    expect(callsTo(STREAM_PATH)).toHaveLength(0);

    vi.spyOn(performance, 'now').mockReturnValue(1_000 + 21_000);  // past "often"'s 20 s
    await vi.waitFor(() => expect(callsTo(STREAM_PATH)).toHaveLength(1), { timeout: 3_000 });
    expect(callsTo(STREAM_PATH)[0].url.searchParams.get('initiative_reason')).toBe(SCENE_TALK_REASON);
    await vi.waitFor(() => expect(perf).toContain('scene_talk_skipped'));
    await new Promise((resolve) => setTimeout(resolve, 1_600));
    expect(callsTo(STREAM_PATH)).toHaveLength(1);  // a refused start waits another silence
    vi.restoreAllMocks();
  });

  it('starts nothing with initiative off, in quiet hours, or with the switch off', async () => {
    vi.spyOn(performance, 'now').mockReturnValue(1_000);
    await startCall(talkProfile({ max_initiatives_per_hour: 0 }));
    liveCallPresentationStore.update({ sceneTalkOn: true });
    vi.spyOn(performance, 'now').mockReturnValue(1_000 + 100_000);
    await new Promise((resolve) => setTimeout(resolve, 1_600));
    expect(callsTo(STREAM_PATH)).toHaveLength(0);

    liveConversationStore.dispatch({ type: 'profile', profile: talkProfile({ initiative_mode: 'gentle', quiet_hours_enabled: true, quiet_hours_start: '00:00', quiet_hours_end: '23:59' }) });
    await new Promise((resolve) => setTimeout(resolve, 1_600));
    expect(callsTo(STREAM_PATH)).toHaveLength(0);

    liveConversationStore.dispatch({ type: 'profile', profile: talkProfile({ initiative_mode: 'gentle' }) });
    liveCallPresentationStore.update({ sceneTalkOn: false });
    await new Promise((resolve) => setTimeout(resolve, 1_600));
    expect(callsTo(STREAM_PATH)).toHaveLength(0);
    vi.restoreAllMocks();
  });
});
