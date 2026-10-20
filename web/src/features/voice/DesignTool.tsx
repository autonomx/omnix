import { Button, Text } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { omnixApiClient } from '../../api/client';
import { voiceApiClient } from './api/voiceClient';
import { BlendPanel } from './BlendPanel';
import { MODELS_QUERY_KEY } from './SpeechModelsPanel';
import { firstOutput, jobSettled, useJobResult } from './useJobResult';

const DESIGN_MODEL = 'qwen3-tts-1.7b-voicedesign';
const MAX_SEED = 2 ** 31 - 1;

/** One choice per row; each adds a phrase to the description. */
const CHIP_ROWS = [
  { id: 'age', label: 'Age', options: ['a child', 'a young adult', 'middle-aged', 'elderly'] },
  { id: 'gender', label: 'Gender', options: ['female', 'male', 'gender-neutral'] },
  { id: 'accent', label: 'Accent', options: ['American', 'British', 'Irish', 'Scottish', 'Australian', 'Indian'] },
  { id: 'pace', label: 'Pace', options: ['slow', 'measured', 'quick'] },
  { id: 'energy', label: 'Energy', options: ['calm', 'warm', 'energetic', 'dramatic'] },
  { id: 'recording', label: 'Recording', options: ['studio-clean', 'close mic', 'over the phone', 'in a large room'] },
] as const;

// Languages with a reference passage for saving (`design.REFERENCE_PASSAGES`).
const DESIGN_LANGUAGES = [
  { code: 'en', label: 'English' }, { code: 'de', label: 'German' }, { code: 'fr', label: 'French' },
  { code: 'es', label: 'Spanish' }, { code: 'it', label: 'Italian' }, { code: 'pt', label: 'Portuguese' },
];

type ChipId = (typeof CHIP_ROWS)[number]['id'];

interface Candidate {
  asset_id: string;
  audio_url: string;
  seed: number;
  title: string;
}

/** The description sent to the model: the chosen chips, then the free text. */
export function composeDescription(chips: Partial<Record<ChipId, string>>, text: string): string {
  const who = [chips.age, chips.gender, chips.accent ? `${chips.accent}-accented` : ''].filter(Boolean).join(' ');
  const parts = [
    who ? `${who} voice` : '',
    chips.pace ? `${chips.pace} pace` : '',
    chips.energy ? `${chips.energy} delivery` : '',
    chips.recording ? `recorded ${chips.recording}` : '',
    text.trim(),
  ].filter(Boolean);
  return parts.join(', ');
}

function randomSeed(): number {
  return Math.floor(Math.random() * MAX_SEED);
}

/** Design: describe a voice, hear three candidates, keep the one you like as a library voice. */
export function DesignTool({ onSaved }: { onSaved: (name: string) => void }) {
  const queryClient = useQueryClient();
  const [chips, setChips] = useState<Partial<Record<ChipId, string>>>({});
  const [text, setText] = useState('');
  // Empty: the candidates read a 15-20 s passage, which a saved voice then clones from most faithfully.
  const [preview, setPreview] = useState('');
  const [language, setLanguage] = useState('en');
  const [seed, setSeed] = useState('');
  const [designJob, setDesignJob] = useState('');
  const [saveJob, setSaveJob] = useState('');
  const [names, setNames] = useState<Record<string, string>>({});
  const models = useQuery({ queryKey: MODELS_QUERY_KEY, queryFn: () => voiceApiClient.listSpeechModels(), retry: false });
  const design = useJobResult(designJob);
  const saving = useJobResult(saveJob);
  const description = composeDescription(chips, text);
  const model = models.data?.models.find((entry) => entry.id === DESIGN_MODEL);
  const installed = model?.status === 'installed';

  const generate = useMutation({
    mutationFn: (seeds: number[]) => omnixApiClient.createJob({
      module: 'voice',
      type: 'voice.design',
      resource_class: 'gpu:tts',
      priority: 0,
      input_payload: { description, preview_text: preview, language, seeds },
      stages: [{ id: 'design', label: 'Design voice candidates', resource_class: 'gpu:tts', status: 'queued' }],
    }),
    onSuccess: (job) => setDesignJob(job.id),
  });
  const save = useMutation({
    mutationFn: (candidate: Candidate) => omnixApiClient.createJob({
      module: 'voice',
      type: 'voice.design.save',
      resource_class: 'gpu:tts',
      priority: 0,
      // The voice saved is the candidate heard: its own audio and words are the clone reference.
      input_payload: { description: String(firstOutput(design.data)?.description ?? description), seed: candidate.seed, language, profile_name: names[candidate.asset_id] ?? '', candidate_asset_id: candidate.asset_id },
      stages: [{ id: 'save', label: 'Render the reference passage and save the voice', resource_class: 'gpu:tts', status: 'queued' }],
    }),
    onSuccess: (job) => setSaveJob(job.id),
  });

  const designing = Boolean(designJob) && !jobSettled(design.data);
  const candidates = design.data?.status === 'completed'
    ? ((design.data.output_refs ?? []) as unknown as Candidate[]).filter((ref) => typeof ref.audio_url === 'string')
    : [];
  const savingNow = Boolean(saveJob) && !jobSettled(saving.data);
  const savedName = saving.data?.status === 'completed' ? String(firstOutput(saving.data)?.title ?? '') : '';
  const failure = [design.data, saving.data].find((job) => job?.status === 'failed');
  const failureMessage = failure ? (typeof failure.error?.message === 'string' ? failure.error.message : 'Voice design failed.') : '';
  // A queued job that already started was deferred: it waits for the swap controller to load the model.
  const waitingForModel = designing && design.data?.status === 'queued' && Boolean(design.data.started_at);

  function generateThree() {
    const base = seed.trim() ? Math.min(MAX_SEED - 3, Math.max(0, Number(seed))) : randomSeed();
    generate.mutate([base, base + 1, base + 2]);
  }
  function vary() {
    const seeds = [randomSeed(), randomSeed(), randomSeed()];
    setSeed(String(seeds[0]));
    generate.mutate(seeds);
  }
  useEffect(() => {
    if (!savedName) return;
    // Once: the library refreshes and the parent says where the voice went.
    setSaveJob('');
    void queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] });
    onSaved(savedName);
  }, [onSaved, queryClient, savedName]);

  return (
    <section className="voice-design" aria-label="Design">
      <div className="voice-section-head">
        <div><h3>Design a voice</h3><Text size="sm">Describe a voice, hear three takes on it, and keep the one you like. Saved voices work with every cloning engine.</Text></div>
      </div>
      {models.data && !installed ? (
        <div className="voice-notice" role="note">Install “Qwen3-TTS 1.7B VoiceDesign” in the Models tool to design voices.</div>
      ) : null}
      <div className="voice-design-chips">
        {CHIP_ROWS.map((row) => (
          <div key={row.id} role="group" aria-label={row.label} className="voice-design-chip-row">
            <span>{row.label}</span>
            {row.options.map((option) => (
              <button key={option} type="button" aria-pressed={chips[row.id] === option} className={chips[row.id] === option ? 'active' : ''} onClick={() => setChips((current) => ({ ...current, [row.id]: current[row.id] === option ? undefined : option }))}>{option}</button>
            ))}
          </div>
        ))}
      </div>
      <label className="voice-design-field">More detail<textarea aria-label="Voice description" rows={2} maxLength={400} placeholder="e.g. gentle, slightly husky, smiles while talking" value={text} onChange={(event) => setText(event.currentTarget.value)} /></label>
      <Text size="xs" className="voice-design-summary">Sent to the model: {description || 'nothing yet'}</Text>
      <div className="voice-design-row">
        <label className="voice-design-field" title="Leave empty to hear a 15-20 second passage: the voice you save keeps that audio to clone from, and a short sentence clones less faithfully.">Preview sentence (optional)<input aria-label="Preview sentence" maxLength={300} placeholder="A longer passage that clones best" value={preview} onChange={(event) => setPreview(event.currentTarget.value)} /></label>
        <label className="voice-design-field">Language<select aria-label="Design language" value={language} onChange={(event) => setLanguage(event.currentTarget.value)}>
          {DESIGN_LANGUAGES.map((entry) => <option key={entry.code} value={entry.code}>{entry.label}</option>)}
        </select></label>
        <label className="voice-design-field" title="The same description and seed give a similar voice again.">Seed<input aria-label="Seed" inputMode="numeric" placeholder="random" value={seed} onChange={(event) => setSeed(event.currentTarget.value.replace(/\D/g, '').slice(0, 10))} /></label>
      </div>
      <div className="voice-design-actions">
        <Button disabled={!description || !installed || designing} loading={generate.isPending || designing} onClick={generateThree}>Generate 3</Button>
        <Button variant="light" disabled={!description || !installed || designing} onClick={vary} title="Same description, new seeds">Vary</Button>
      </div>
      {designing ? <Text size="sm" role="status">{waitingForModel ? 'Waiting for the design model to load…' : 'Designing…'}</Text> : null}
      {failureMessage || generate.isError || save.isError ? <Text size="sm" role="alert">{failureMessage || 'The request could not be queued.'}</Text> : null}
      {candidates.length ? (
        <ol className="voice-design-candidates">
          {candidates.map((candidate) => (
            <li key={candidate.asset_id}>
              <b>{candidate.title}</b> <small>seed {candidate.seed}</small>
              <audio controls preload="none" src={candidate.audio_url} aria-label={`${candidate.title} preview`} />
              <div className="voice-design-save">
                <input aria-label={`Name for ${candidate.title}`} placeholder="Voice name" maxLength={80} value={names[candidate.asset_id] ?? ''} onChange={(event) => { const value = event.currentTarget.value; setNames((current) => ({ ...current, [candidate.asset_id]: value })); }} />
                <Button size="xs" disabled={!(names[candidate.asset_id] ?? '').trim() || savingNow} loading={savingNow && save.variables?.asset_id === candidate.asset_id} onClick={() => save.mutate(candidate)}>Save as voice</Button>
              </div>
            </li>
          ))}
        </ol>
      ) : null}
      <BlendPanel language={language} onSaved={onSaved} />
    </section>
  );
}
