import { Button, Text } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { omnixApiClient, type AssetListResponse } from '../../api/client';
import { voiceApiClient } from './api/voiceClient';
import { jobSettled, useJobResult } from './useJobResult';

type Asset = AssetListResponse['assets'][number];

export const AUDIO_TOOLS_QUERY_KEY = ['voice', 'audio-tools'] as const;

const SOURCE_TYPES = new Set(['audio', 'voice_sample', 'voice_profile', 'voice_take', 'chapter_audio', 'render', 'export']);
const TOOLS = {
  isolate: { type: 'audio.isolate', label: 'Isolate vocals', stage: 'Separate the voice from the background' },
  enhance: { type: 'audio.enhance', label: 'Clean up speech', stage: 'Remove noise from the recording' },
  detect: { type: 'audio.watermark-detect', label: 'Check watermark', stage: 'Look for an AudioSeal watermark' },
} as const;

type ToolId = keyof typeof TOOLS;

interface ToolOutput {
  kind?: string;
  title?: string;
  audio_url?: string;
  asset_id?: string;
  detected?: boolean;
  probability?: number;
  this_workspace?: boolean;
}

function assetTitle(asset: Asset): string {
  const title = asset.metadata?.title ?? asset.metadata?.profile_name;
  return typeof title === 'string' && title.trim() ? title : asset.file_name || asset.id;
}

/** Audio Tools: isolate a voice, clean up a recording, check for a watermark; and the watermark switch. */
export function AudioToolsTool({ assets }: { assets: Asset[] }) {
  const queryClient = useQueryClient();
  const sources = assets.filter((asset) => SOURCE_TYPES.has(asset.type) && asset.mime_type.startsWith('audio/'));
  const [sourceId, setSourceId] = useState('');
  const [model, setModel] = useState('roformer');
  const [jobId, setJobId] = useState('');
  const status = useQuery({ queryKey: AUDIO_TOOLS_QUERY_KEY, queryFn: () => voiceApiClient.audioToolsStatus(), retry: false });
  const job = useJobResult(jobId);
  const available = Boolean(status.data?.available);

  const run = useMutation({
    mutationFn: (tool: ToolId) => omnixApiClient.createJob({
      module: 'voice',
      type: TOOLS[tool].type,
      resource_class: 'gpu:audio',
      priority: 0,
      input_ref: { asset_id: sourceId },
      input_payload: { asset_id: sourceId, ...(tool === 'isolate' ? { model } : {}) },
      stages: [{ id: tool, label: TOOLS[tool].stage, resource_class: 'gpu:audio', status: 'queued' }],
    }),
    onSuccess: (created) => setJobId(created.id),
  });
  const watermark = useMutation({
    mutationFn: (enabled: boolean) => voiceApiClient.saveWatermark(enabled),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: AUDIO_TOOLS_QUERY_KEY }),
  });

  const running = Boolean(jobId) && !jobSettled(job.data);
  const outputs = job.data?.status === 'completed' ? (job.data.output_refs ?? []) as unknown as ToolOutput[] : [];
  const failure = job.data?.status === 'failed' ? (typeof job.data.error?.message === 'string' ? job.data.error.message : 'The tool failed.') : '';
  const madeAssets = job.data?.status === 'completed' && outputs.some((output) => output.audio_url);
  useEffect(() => {
    // New stems or a cleaned recording join the library once the job finishes.
    if (madeAssets) void queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] });
  }, [jobId, madeAssets, queryClient]);
  const watermarkOn = Boolean(status.data?.watermark.enabled);

  return (
    <section className="voice-audio-tools" aria-label="Audio Tools">
      <div className="voice-section-head">
        <div><h3>Audio Tools</h3><Text size="sm">Isolate a voice from music or noise, clean up a recording, or check a file for a watermark.</Text></div>
      </div>
      {status.data && !available ? (
        <div className="voice-notice" role="note">The audio service is not running{status.data.detail ? `: ${status.data.detail}` : '.'}</div>
      ) : null}
      <div className="voice-audio-tools-form">
        <label>Recording<select aria-label="Audio source" value={sourceId} onChange={(event) => setSourceId(event.currentTarget.value)}>
          <option value="">Choose a stored recording</option>
          {sources.map((asset) => <option key={asset.id} value={asset.id}>{assetTitle(asset)}</option>)}
        </select></label>
        <label title="Mel-Band RoFormer is cleaner on speech; Demucs also handles busy music.">Separation model<select aria-label="Separation model" value={model} onChange={(event) => setModel(event.currentTarget.value)}>
          <option value="roformer">Mel-Band RoFormer</option>
          <option value="demucs">Demucs (htdemucs_ft)</option>
        </select></label>
      </div>
      <div className="voice-audio-tools-actions">
        {(Object.keys(TOOLS) as ToolId[]).map((tool) => (
          <Button key={tool} variant={tool === 'isolate' ? 'filled' : 'light'} disabled={!sourceId || !available || running} loading={running && run.variables === tool} onClick={() => run.mutate(tool)}>{TOOLS[tool].label}</Button>
        ))}
      </div>
      {running ? <Text size="sm" role="status">Working… ({job.data?.status ?? 'queued'})</Text> : null}
      {failure || run.isError ? <Text size="sm" role="alert">{failure || 'The tool could not be queued.'}</Text> : null}
      {outputs.length ? (
        <ul className="voice-audio-tools-results">
          {outputs.map((output, index) => (
            <li key={output.asset_id ?? index}>
              <b>{output.title}</b>
              {output.audio_url ? <audio controls preload="none" src={output.audio_url} aria-label={`${output.title ?? 'Result'} playback`} /> : null}
              {typeof output.probability === 'number' ? <small>Detection probability {(output.probability * 100).toFixed(0)}%</small> : null}
            </li>
          ))}
        </ul>
      ) : null}

      <div className="voice-inspector-section" aria-label="Watermarking">
        <label className="voice-audio-tools-switch">
          <input type="checkbox" checked={watermarkOn} disabled={!status.data || watermark.isPending} onChange={(event) => watermark.mutate(event.currentTarget.checked)} />
          Watermark every render
        </label>
        <Text size="xs">An inaudible AudioSeal mark goes into every take, render and design preview before it is saved; exports refuse renders made without one. Live speech is not marked. Needs the audio service; workspace admins only.</Text>
        {watermark.isError ? <Text size="xs" role="alert">Only workspace admins can change watermarking.</Text> : null}
      </div>
    </section>
  );
}
