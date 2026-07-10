import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import type { CharacterProfile } from './characterClient';
import { characterAvatarAssetUrl, characterAvatarClient } from './characterAvatarClient';
import './CharacterAvatarPanel.css';

const ACTIVE_GENERATION_STATES = new Set(['queued', 'generating_base', 'generating_variants']);

export function CharacterAvatarPanel({ character }: { character: CharacterProfile }) {
  const queryClient = useQueryClient();
  const [appearancePrompt, setAppearancePrompt] = useState('');
  const [style, setStyle] = useState('illustrated character portrait');
  const [outfitPrompt, setOutfitPrompt] = useState('');
  const [backgroundPrompt, setBackgroundPrompt] = useState('');
  const [generationId, setGenerationId] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const packQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'character-avatar-pack', character.id],
    queryFn: () => characterAvatarClient.optionalPack(character.id),
    retry: false,
  });
  const generationQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'character-avatar-generation', generationId],
    queryFn: () => characterAvatarClient.generation(generationId ?? ''),
    enabled: Boolean(generationId),
    refetchInterval: (query) => ACTIVE_GENERATION_STATES.has(query.state.data?.status ?? '') ? 1_500 : false,
  });

  useEffect(() => {
    setGenerationId(null);
    setStatus(null);
  }, [character.id]);

  useEffect(() => {
    const batch = generationQuery.data;
    if (!batch) return;
    if (batch.status === 'completed') {
      setStatus(`Avatar pack v${batch.avatar_pack_version ?? 1} is ready.`);
      void queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'character-avatar-pack', character.id] });
    } else if (batch.status === 'failed') {
      setStatus(batch.error || 'Avatar generation failed.');
    }
  }, [character.id, generationQuery.data, queryClient]);

  const generateMutation = useMutation({
    mutationFn: () => characterAvatarClient.createGeneration(character.id, {
      appearance_prompt: appearancePrompt,
      style,
      outfit_prompt: outfitPrompt,
      background_prompt: backgroundPrompt,
      include_blink: true,
      include_expressions: true,
      include_outfit: Boolean(outfitPrompt.trim()),
      include_background: Boolean(backgroundPrompt.trim()),
    }),
    onSuccess: (batch) => {
      setGenerationId(batch.id);
      setStatus('Canonical portrait generation queued. Mouth and expression frames follow automatically.');
    },
    onError: (error) => setStatus(error instanceof Error ? error.message : 'Avatar generation could not be queued.'),
  });

  const pack = packQuery.data;
  const previewAssetId = pack?.mouth_frames.closed || pack?.base_asset_id || '';
  const generation = generationQuery.data;
  const generatedVariants = useMemo(() => Object.keys(generation?.asset_ids ?? {}).length, [generation?.asset_ids]);

  return <section className="character-avatar-panel" aria-labelledby={`character-avatar-${character.id}`}>
    <header>
      <div>
        <h4 id={`character-avatar-${character.id}`}>Live avatar</h4>
        <p>Generate a locked portrait and synchronized mouth, blink, expression, outfit, and background frames through Omnix Image Generation.</p>
      </div>
    </header>

    <div className="character-avatar-layout">
      <div className="character-avatar-preview">
        {previewAssetId ? <img src={characterAvatarAssetUrl(previewAssetId)} alt={`${character.display_name} avatar preview`} /> : <div className="character-avatar-empty"><span aria-hidden="true">◌</span><strong>No avatar pack</strong><small>Generate one from the character profile.</small></div>}
        {pack ? <p><strong>Pack v{pack.version}</strong><span>{pack.render_mode.replace('_', ' ')}</span></p> : null}
      </div>

      <div className="character-avatar-form">
        <label>Appearance direction<textarea rows={3} value={appearancePrompt} placeholder="Hair, clothing, age range, visual mood, framing…" onChange={(event) => setAppearancePrompt(event.currentTarget.value)} /></label>
        <label>Visual style<input value={style} onChange={(event) => setStyle(event.currentTarget.value)} /></label>
        <div className="character-avatar-form-grid">
          <label>Alternate outfit<input value={outfitPrompt} placeholder="Optional" onChange={(event) => setOutfitPrompt(event.currentTarget.value)} /></label>
          <label>Alternate background<input value={backgroundPrompt} placeholder="Optional" onChange={(event) => setBackgroundPrompt(event.currentTarget.value)} /></label>
        </div>
        <button type="button" disabled={generateMutation.isPending || ACTIVE_GENERATION_STATES.has(generation?.status ?? '')} onClick={() => generateMutation.mutate()}>
          {generateMutation.isPending ? 'Queueing…' : generation && ACTIVE_GENERATION_STATES.has(generation.status) ? 'Generating avatar pack…' : pack ? 'Regenerate avatar pack' : 'Generate avatar pack'}
        </button>
        {generation ? <div className="character-avatar-progress"><strong>{generation.status.replaceAll('_', ' ')}</strong><span>{generatedVariants} assets ready</span>{generation.error ? <small>{generation.error}</small> : null}</div> : null}
      </div>
    </div>
    {status ? <p className="character-avatar-status" role="status">{status}</p> : null}
  </section>;
}
