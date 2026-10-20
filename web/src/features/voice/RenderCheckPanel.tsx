import { Button, Text } from '@mantine/core';
import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { omnixApiClient } from '../../api/client';
import { firstOutput, jobSettled, useJobResult } from './useJobResult';

interface RenderCheckLine {
  index: number;
  speaker: string;
  text: string;
  heard: string;
  word_error_rate: number;
}

interface RenderCheckReport {
  word_error_rate: number;
  reference_words: number;
  lines: RenderCheckLine[];
}

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

/**
 * "Check render": transcribe the current render and compare it with its script,
 * so a mispronounced or skipped line shows up without listening to everything.
 */
export function RenderCheckPanel({ assetId }: { assetId: string }) {
  const [jobId, setJobId] = useState('');
  const job = useJobResult(jobId);
  const queue = useMutation({
    mutationFn: () => omnixApiClient.createJob({
      module: 'stt',
      type: 'stt.transcribe',
      resource_class: 'gpu:stt',
      priority: 0,
      input_ref: { asset_id: assetId },
      input_payload: { asset_id: assetId, check_render: true, timed: true, diarize: false },
      stages: [{ id: 'transcribe', label: 'Transcribe the render', resource_class: 'gpu:stt', status: 'queued' }],
    }),
    onSuccess: (created) => setJobId(created.id),
  });
  const settled = jobSettled(job.data);
  const report = settled ? (firstOutput(job.data)?.render_check as RenderCheckReport | undefined) : undefined;
  const worst = report?.lines.filter((line) => line.word_error_rate > 0).sort((a, b) => b.word_error_rate - a.word_error_rate).slice(0, 3) ?? [];
  const failure = job.data?.status === 'failed' ? (typeof job.data.error?.message === 'string' ? job.data.error.message : 'The check failed.') : '';

  return (
    <div className="voice-render-check" aria-label="Render check">
      <div className="voice-render-check-head">
        <Button size="xs" variant="light" disabled={!assetId} loading={queue.isPending || (Boolean(jobId) && !settled)} onClick={() => queue.mutate()} title="Transcribe this render and compare it with its script.">Check render</Button>
        {report ? <Text size="sm" role="status">Word error {percent(report.word_error_rate)} over {report.reference_words} words</Text> : null}
      </div>
      {failure || queue.isError ? <Text size="sm" role="alert" className="voice-disabled-reason">{failure || 'The check could not be queued.'}</Text> : null}
      {worst.length ? (
        <ul className="voice-render-check-lines">
          {worst.map((line) => (
            <li key={line.index}>
              <b>Line {line.index + 1}{line.speaker ? ` (${line.speaker})` : ''}: {percent(line.word_error_rate)}</b>
              <span>Script: {line.text}</span>
              <span>Heard: {line.heard || '(nothing)'}</span>
            </li>
          ))}
        </ul>
      ) : report && report.word_error_rate === 0 ? <Text size="xs">Every word matched the script.</Text> : null}
    </div>
  );
}
