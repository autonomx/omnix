import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { CapabilityNotice } from '../../../setup';
import {
  applyCharacterAvatarPackToTrackedRuntimes,
  readLatestTrustedCharacterRuntime,
  type CharacterAvatarPack,
} from '../characterClient';
import { characterAvatarAssetUrl, characterAvatarClient, type PortraitPreviewResponse } from '../characterAvatarClient';
import { runtimeAvatarOwner } from '../liveCharacterAvatarBridge';

/**
 * A character's live portrait (docs/architecture/OMNIX_LIVE_PORTRAIT_ROADMAP.md, Phase 4): an image of a face that
 * talks in live calls. The image is checked and previewed on the portrait service before it is saved; the
 * fallback is what calls show when the portrait cannot (the image itself, the character's Live2D rig, or the orb).
 */

const UPLOAD_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);
const MAX_UPLOAD_BYTES = 12 * 1024 * 1024;
const EMOTIONS = ['angry', 'disgust', 'fear', 'happy', 'neutral', 'sad', 'surprise'] as const;
type PortraitEmotion = 'character' | (typeof EMOTIONS)[number];
type Fallback = 'sprite' | 'live2d' | 'orb';

const PREVIEW_PROBLEMS: Record<string, string> = {
  portrait_not_configured: 'The portrait service is not set up on this server.',
  no_face: 'No face was found in this image. Use a clear, front-facing portrait.',
  image_too_large: 'This image is too large (12 MB or 40 megapixels at most).',
  image_unreadable: 'This image could not be read.',
  portrait_busy: 'A live call is using the portrait. Try the preview after the call.',
  model_missing: 'The live portrait models are not installed. Download them in Settings, Models.',
  warming: 'The portrait model is still loading. Try again in a minute.',
};

export function PortraitAvatarSetup({ characterId, displayName, pack, removable = false }: {
  characterId: string;
  displayName: string;
  pack: CharacterAvatarPack | null | undefined;
  /** Offer to turn the saved portrait off: for an avatar with nothing else to fall back on (the System Assistant). */
  removable?: boolean;
}) {
  const queryClient = useQueryClient();
  const current = pack?.renderer === 'portrait' ? pack : null;
  const [file, setFile] = useState<File | null>(null);
  const [assetId, setAssetId] = useState<string>(current?.base_asset_id ?? '');
  const [emotion, setEmotion] = useState<PortraitEmotion>((current?.portrait_emotion as PortraitEmotion | undefined) ?? 'character');
  const [fallback, setFallback] = useState<Fallback>(current?.fallback_renderer ?? 'sprite');
  const [status, setStatus] = useState<string | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stopPreview = useRef<(() => void) | null>(null);

  useEffect(() => () => stopPreview.current?.(), []);

  const upload = async (): Promise<string> => {
    if (!file) {
      if (assetId) return assetId;
      throw new Error('Choose a portrait image first.');
    }
    if (!UPLOAD_TYPES.has(file.type)) throw new Error('Use a JPEG, PNG, or WebP image.');
    if (file.size > MAX_UPLOAD_BYTES) throw new Error('Portrait images must be 12 MB or smaller.');
    const asset = await characterAvatarClient.uploadSourceImage(file);
    setAssetId(asset.id);
    setFile(null);
    return asset.id;
  };

  const preview = useMutation({
    mutationFn: async () => {
      const id = await upload();
      const runtime = readLatestTrustedCharacterRuntime();
      const speaker = runtime && runtimeAvatarOwner(runtime) === characterId ? runtime.voice_asset_id ?? undefined : undefined;
      return characterAvatarClient.previewPortrait({
        asset_id: id, emotion: emotion === 'character' ? 'neutral' : emotion, speaker,
      });
    },
    onSuccess: (result) => {
      if (!result.ok) {
        setStatus(PREVIEW_PROBLEMS[result.code] ?? (result.message || 'The portrait could not be previewed.'));
        return;
      }
      setStatus('Previewing the portrait.');
      stopPreview.current?.();
      if (canvasRef.current) stopPreview.current = playPreview(result, canvasRef.current, () => setStatus(null));
    },
    onError: (error) => setStatus(error instanceof Error ? error.message : 'The portrait could not be previewed.'),
  });

  const save = useMutation({
    mutationFn: async () => {
      const id = await upload();
      return characterAvatarClient.savePack(characterId, {
        expected_version: pack?.version ?? null,
        render_mode: 'static',
        renderer: 'portrait',
        base_asset_id: id,
        // A Live2D fallback draws the character's rig, kept from its pack.
        rig_asset_id: fallback === 'live2d' ? pack?.rig_asset_id ?? null : null,
        fallback_renderer: fallback,
        portrait_emotion: emotion,
      });
    },
    onSuccess: (saved) => {
      applyCharacterAvatarPackToTrackedRuntimes(characterId, saved);
      setStatus(`The live portrait is saved. Live calls with ${displayName} now show it.`);
      void queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'character-avatar-pack', characterId] });
      void queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'live-call-runtime'] });
    },
    onError: (error) => setStatus(error instanceof Error ? error.message : 'The portrait could not be saved.'),
  });

  const remove = useMutation({
    mutationFn: () => characterAvatarClient.deletePack(characterId),
    onSuccess: () => {
      applyCharacterAvatarPackToTrackedRuntimes(characterId, null);
      setStatus('The live portrait is off. Live calls show the voice orb until another avatar is selected.');
      void queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'character-avatar-pack', characterId] });
      void queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'character-live2d-models', characterId] });
      void queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'live-call-runtime'] });
    },
    onError: (error) => setStatus(error instanceof Error ? error.message : 'The portrait could not be turned off.'),
  });

  const busy = preview.isPending || save.isPending || remove.isPending;
  const ready = Boolean(file || assetId);

  return <div className="character-portrait-setup">
    <CapabilityNotice capability="live_portrait" purpose="The live portrait" />
    <div className="character-portrait-stage">
      {assetId && !file ? <img src={characterAvatarAssetUrl(assetId)} alt={`${displayName} portrait`} /> : null}
      <canvas ref={canvasRef} width={512} height={512} aria-label={`${displayName} portrait preview`} />
    </div>
    <p>Use a clear, front-facing photo or painting of one face. The portrait moves its head and lips with the voice in live calls.</p>
    <label className="character-avatar-upload-picker">
      <span>{file || assetId ? 'Replace image' : 'Choose image'}</span>
      <input
        aria-label="Portrait image"
        type="file"
        accept="image/jpeg,image/png,image/webp"
        onChange={(event) => setFile(event.currentTarget.files?.[0] ?? null)}
      />
    </label>
    {file ? <small>{file.name} · {Math.max(1, Math.round(file.size / 1024))} KB</small> : null}
    <label>Emotion
      <select aria-label="Portrait emotion" value={emotion} onChange={(event) => setEmotion(event.currentTarget.value as PortraitEmotion)}>
        <option value="character">{displayName}&apos;s speaking style</option>
        {EMOTIONS.map((label) => <option key={label} value={label}>{label[0].toUpperCase() + label.slice(1)}</option>)}
      </select>
    </label>
    <label>When the portrait is not available
      <select aria-label="Portrait fallback" value={fallback} onChange={(event) => setFallback(event.currentTarget.value as Fallback)}>
        <option value="sprite">Show the image</option>
        {pack?.rig_asset_id ? <option value="live2d">Show the Live2D avatar</option> : null}
        <option value="orb">Show the voice orb</option>
      </select>
    </label>
    <div className="character-avatar-actions">
      <button type="button" disabled={!ready || busy} onClick={() => preview.mutate()}>
        {preview.isPending ? 'Preparing the preview…' : 'Preview'}
      </button>
      <button type="button" disabled={!ready || busy} onClick={() => save.mutate()}>
        {save.isPending ? 'Saving…' : current ? 'Save the portrait' : 'Use this portrait'}
      </button>
      {removable && current ? <button type="button" disabled={busy} onClick={() => remove.mutate()}>
        {remove.isPending ? 'Turning off…' : 'Turn off the portrait'}
      </button> : null}
    </div>
    {status ? <p className="character-avatar-status" role="status">{status}</p> : null}
  </div>;
}

/** Play a preview's audio and draw its frames by the audio's clock; returns a function that stops it. */
export function playPreview(result: PortraitPreviewResponse, canvas: HTMLCanvasElement, onEnded: () => void): () => void {
  const context = canvas.getContext('2d');
  const AudioContextCtor = window.AudioContext;
  if (!context || !AudioContextCtor) return () => undefined;
  const audioContext = new AudioContextCtor();
  const bytes = Uint8Array.from(atob(result.audio), (character) => character.charCodeAt(0));
  const samples = new Int16Array(bytes.buffer, 0, Math.floor(bytes.length / 2));
  const buffer = audioContext.createBuffer(1, Math.max(1, samples.length), result.sample_rate);
  const channel = buffer.getChannelData(0);
  for (let index = 0; index < samples.length; index += 1) channel[index] = samples[index] / 32768;
  let stopped = false;
  let handle = 0;
  const frames: (ImageBitmap | null)[] = result.frames.map(() => null);
  result.frames.forEach((frame, index) => {
    const jpeg = Uint8Array.from(atob(frame), (character) => character.charCodeAt(0));
    void createImageBitmap(new Blob([jpeg], { type: 'image/jpeg' })).then((image) => {
      if (stopped) image.close();
      else frames[index] = image;
    }).catch(() => undefined);
  });
  const source = audioContext.createBufferSource();
  source.buffer = buffer;
  source.connect(audioContext.destination);
  const startAt = audioContext.currentTime + 0.1;
  source.start(startAt);
  const draw = () => {
    if (stopped) return;
    const index = Math.floor((audioContext.currentTime - startAt) * result.fps);
    const frame = index >= 0 ? frames[Math.min(index, frames.length - 1)] : null;
    if (frame) context.drawImage(frame, 0, 0, canvas.width, canvas.height);
    handle = requestAnimationFrame(draw);
  };
  handle = requestAnimationFrame(draw);
  const stop = () => {
    if (stopped) return;
    stopped = true;
    cancelAnimationFrame(handle);
    source.onended = null;
    try { source.stop(); } catch { /* already over */ }
    void audioContext.close().catch(() => undefined);
    for (const frame of frames) frame?.close();
  };
  source.onended = () => {
    stop();
    onEnded();
  };
  return stop;
}
