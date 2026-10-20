import { Button, Text } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { omnixApiClient } from '../../api/client';
import { voiceApiClient } from './api/voiceClient';
import { ENGINES_QUERY_KEY } from './TtsEnginePicker';
import { jobSettled, useJobResult } from './useJobResult';
import { voiceAssetName, voiceReference } from './voiceAssets';

const LIBRARY_QUERY_KEY = ['voice', 'library'] as const;

/** Two library voices and a mix: the blended voice's speaker embedding is their weighted mean. */
export function blendVoices(first: string, second: string, towardSecond: number): { voice: string; weight: number }[] {
  const share = Math.min(0.9, Math.max(0.1, towardSecond));
  return [{ voice: first, weight: Number((1 - share).toFixed(2)) }, { voice: second, weight: Number(share.toFixed(2)) }];
}

/**
 * Blend (§5): a new library voice between two others. Shown only when an engine exposes speaker
 * embeddings (the `voice_blend` capability); hidden elsewhere.
 */
export function BlendPanel({ language, onSaved }: { language: string; onSaved: (name: string) => void }) {
  const queryClient = useQueryClient();
  const engines = useQuery({ queryKey: ENGINES_QUERY_KEY, queryFn: () => voiceApiClient.listTtsEngines(), retry: false });
  const library = useQuery({ queryKey: LIBRARY_QUERY_KEY, queryFn: () => voiceApiClient.listVoiceLibrary(), retry: false });
  const [first, setFirst] = useState('');
  const [second, setSecond] = useState('');
  const [mix, setMix] = useState(0.5);
  const [name, setName] = useState('');
  const [jobId, setJobId] = useState('');
  const job = useJobResult(jobId);
  const blending = Boolean(jobId) && !jobSettled(job.data);
  const blender = engines.data?.engines.find((engine) => engine.voice_blend && engine.installed);
  const voices = library.data?.assets ?? [];
  const start = useMutation({
    mutationFn: () => omnixApiClient.createJob({
      module: 'voice', type: 'voice.blend', resource_class: 'gpu:tts', priority: 0,
      input_payload: { voices: blendVoices(first, second, mix), profile_name: name.trim(), language },
      stages: [{ id: 'blend', label: 'Blend the voices', resource_class: 'gpu:tts', status: 'queued' }],
    }),
    onSuccess: (created) => setJobId(created.id),
  });
  const done = job.data?.status === 'completed';
  useEffect(() => {
    if (!done) return;
    void queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] });
    void queryClient.invalidateQueries({ queryKey: LIBRARY_QUERY_KEY });
    onSaved(name.trim());
    setJobId('');
    setName('');
  }, [done, name, onSaved, queryClient]);

  if (!blender) return null;
  const failure = job.data?.status === 'failed' ? (typeof job.data.error?.message === 'string' ? job.data.error.message : 'Blending failed.') : '';
  const label = (id: string) => voiceAssetName(voices.find((asset) => voiceReference(asset) === id) ?? voices[0]);
  return (
    <div className="voice-design-blend" role="group" aria-label="Blend voices">
      <h4>Blend two voices</h4>
      <Text size="xs">A new voice between two library voices, made by {blender.label} from their speaker embeddings. Saved voices work with every cloning engine.</Text>
      <div className="voice-design-row">
        <label className="voice-design-field">First voice<select aria-label="First voice" value={first} onChange={(event) => setFirst(event.currentTarget.value)}>
          <option value="">Choose a voice</option>
          {voices.map((asset) => <option key={voiceReference(asset)} value={voiceReference(asset)}>{voiceAssetName(asset)}</option>)}
        </select></label>
        <label className="voice-design-field">Second voice<select aria-label="Second voice" value={second} onChange={(event) => setSecond(event.currentTarget.value)}>
          <option value="">Choose a voice</option>
          {voices.filter((asset) => voiceReference(asset) !== first).map((asset) => <option key={voiceReference(asset)} value={voiceReference(asset)}>{voiceAssetName(asset)}</option>)}
        </select></label>
      </div>
      <label className="voice-design-field">Mix{first && second ? `: ${Math.round((1 - mix) * 100)}% ${label(first)}, ${Math.round(mix * 100)}% ${label(second)}` : ''}
        <input aria-label="Blend mix" type="range" min={0.1} max={0.9} step={0.05} value={mix} onChange={(event) => setMix(Number(event.currentTarget.value))} />
      </label>
      <div className="voice-design-save">
        <input aria-label="Blended voice name" placeholder="Voice name" maxLength={80} value={name} onChange={(event) => setName(event.currentTarget.value)} />
        <Button size="xs" disabled={!first || !second || first === second || !name.trim() || blending} loading={start.isPending || blending} onClick={() => start.mutate()}>Blend and save</Button>
      </div>
      {blending ? <Text size="sm" role="status">Blending…</Text> : null}
      {failure || start.isError ? <Text size="sm" role="alert">{failure || 'The blend could not be queued.'}</Text> : null}
    </div>
  );
}
