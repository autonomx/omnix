import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CharacterLiveCallRuntime } from './characterClient';
import {
  characterAvatarAssetUrl,
  mouthFrameForRms,
  pcmMouthTimeline,
  presentationStateFromDom,
  publishCharacterAvatarRuntime,
} from './liveCharacterAvatarBridge';

const runtime: CharacterLiveCallRuntime = {
  session_id: 'chat:maya',
  interaction_mode: 'character',
  display_name: 'Maya',
  character_id: 'maya',
  character_profile_version: 1,
  effective_identity_hash: 'identity:maya',
  voice_asset_id: 'voice:maya',
  greeting: 'Hello.',
  avatar_pack: {
    character_id: 'maya',
    version: 1,
    render_mode: 'audio_envelope',
    renderer: 'sprite',
    rig_asset_id: null,
    base_asset_id: 'image:maya-base',
    mouth_frames: { closed: 'image:maya-closed', wide: 'image:maya-wide' },
    blink_frames: {},
    expression_frames: {},
    outfit_frames: {},
    background_asset_ids: {},
    active_outfit: null,
    active_background: null,
    mouth_anchor: {},
    created_at: '2026-07-10T00:00:00Z',
    updated_at: '2026-07-10T00:00:00Z',
  },
  speech_style: {
    speed: 1,
    temperature: 0.7,
    top_k: 20,
    top_p: 0.8,
    repetition_penalty: 1.05,
    expressiveness: 'conversational',
    emotion: 'neutral',
    interruption_style: 'natural',
  },
  read_memory: true,
  write_memory: true,
  shared_memory_access: 'none',
  memory_snapshot_id: null,
  preload: {
    profile_loaded: true,
    voice_resolved: true,
    avatar_pack_loaded: true,
    memory_snapshot_loaded: true,
    memory_record_count: 0,
    preload_ms: 1,
    resolved_at: '2026-07-10T00:00:00Z',
  },
};

afterEach(() => {
  vi.useRealTimers();
  publishCharacterAvatarRuntime(null);
  document.body.innerHTML = '';
});

describe('live character avatar audio envelope', () => {
  it('maps RMS levels to four stable mouth states', () => {
    expect(mouthFrameForRms(0)).toBe('closed');
    expect(mouthFrameForRms(0.02)).toBe('small');
    expect(mouthFrameForRms(0.05)).toBe('medium');
    expect(mouthFrameForRms(0.2)).toBe('wide');
  });

  it('produces a compact timeline and browser-safe asset URL', () => {
    const samples = new Int16Array(4800);
    samples.fill(0, 0, 1200);
    samples.fill(4000, 1200, 2400);
    samples.fill(14000, 2400, 3600);
    samples.fill(0, 3600);
    const timeline = pcmMouthTimeline(samples, 24_000, 50);
    expect(timeline[0]).toEqual({ offsetMs: 0, frame: 'closed' });
    expect(timeline.some((point) => point.frame === 'wide')).toBe(true);
    expect(characterAvatarAssetUrl('image:maya closed')).toBe('/api/assets/image%3Amaya%20closed/file');
  });

  it('derives listening, thinking, speaking, and error presentation states', () => {
    expect(presentationStateFromDom('listening', '')).toBe('listening');
    expect(presentationStateFromDom('listening', 'Assistant response streaming.')).toBe('thinking');
    expect(presentationStateFromDom('speaking', 'Synthesizing response voice…')).toBe('speaking');
    expect(presentationStateFromDom('error', '')).toBe('error');
    expect(presentationStateFromDom('idle', '')).toBe('idle');
  });

  it('uses the microphone position for the avatar and moves the transcript below call controls', () => {
    document.body.innerHTML = `
      <section class="assistant-live-card">
        <div class="assistant-voice-orb" data-voice-mode="idle"></div>
        <div class="assistant-voice-controls"></div>
        <label class="assistant-voice-toggle"></label>
        <div class="assistant-live-draft"></div>
        <div class="assistant-voice-transcript"></div>
      </section>
    `;

    publishCharacterAvatarRuntime(runtime);

    const stage = document.querySelector<HTMLElement>('.assistant-live-visual-stage');
    const orb = document.querySelector<HTMLElement>('.assistant-voice-orb');
    const controls = document.querySelector<HTMLElement>('.assistant-voice-controls');
    const transcript = document.querySelector<HTMLElement>('.assistant-voice-transcript');
    const avatar = stage?.querySelector<HTMLElement>('.assistant-live-character-avatar');

    expect(stage?.getAttribute('aria-label')).toBe('Live character visual');
    expect(orb?.parentElement).toBe(stage);
    expect(avatar?.parentElement).toBe(stage);
    expect(orb?.hidden).toBe(true);
    expect(stage?.dataset.hasCharacterAvatar).toBe('true');
    expect(controls?.nextElementSibling).toBe(transcript);
    expect(controls?.getAttribute('aria-label')).toBe('Live voice controls');
    expect(transcript?.getAttribute('aria-label')).toBe('Live voice transcript');

    publishCharacterAvatarRuntime(null);

    expect(stage?.querySelector('.assistant-live-character-avatar')).toBeNull();
    expect(orb?.hidden).toBe(false);
    expect(stage?.dataset.hasCharacterAvatar).toBeUndefined();
  });

  it('animates mouth frames from live-call WebSocket PCM events', () => {
    vi.useFakeTimers();
    document.body.innerHTML = `
      <section class="assistant-live-card">
        <div class="assistant-voice-orb" data-voice-mode="speaking"></div>
        <div class="assistant-voice-controls"></div>
        <div class="assistant-voice-transcript"></div>
      </section>
      <div class="assistant-inline-status"></div>
    `;
    publishCharacterAvatarRuntime(runtime);

    const samples = new Int16Array(2_400);
    samples.fill(16_000);
    window.dispatchEvent(new CustomEvent('omnix:character-avatar-pcm', {
      detail: { samples, sampleRate: 24_000 },
    }));
    vi.advanceTimersByTime(30);

    const avatar = document.querySelector<HTMLElement>('.assistant-live-character-avatar');
    const image = avatar?.querySelector<HTMLImageElement>('img');
    expect(avatar?.dataset.mouthFrame).toBe('wide');
    expect(image?.getAttribute('src')).toBe('/api/assets/image%3Amaya-wide/file');
  });
});
