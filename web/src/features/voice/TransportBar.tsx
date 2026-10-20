import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState, type KeyboardEvent, type MouseEvent, type RefObject } from 'react';
import { voiceApiClient } from './api/voiceClient';
import { formatPlaybackTime } from './voiceAssets';
import type { PlayableVoiceOutput } from './voiceOutputs';

/**
 * Play, scrub and loop the current take; A/B against the previous one. The waveform is the
 * take's peaks, computed on the server and drawn on a canvas (no waveform library).
 */
export function TransportBar({
  audioRef,
  current,
  previous,
  title,
  isPlaying,
  playbackTime,
  duration,
  onTogglePlayback,
  onSeek,
  onSelectOffset,
  onCompare,
  onDownload,
  onLoadedDuration,
  onTimeUpdate,
  onEnded,
}: {
  audioRef: RefObject<HTMLAudioElement | null>;
  current: PlayableVoiceOutput | null;
  previous: PlayableVoiceOutput | null;
  title: string;
  isPlaying: boolean;
  playbackTime: number;
  duration: number;
  onTogglePlayback: () => void;
  onSeek: (time: number) => void;
  onSelectOffset: (offset: number) => void;
  onCompare: () => void;
  onDownload: () => void;
  onLoadedDuration: (duration: number) => void;
  onTimeUpdate: (time: number) => void;
  onEnded: () => void;
}) {
  const [loop, setLoop] = useState<{ start: number; end: number } | null>(null);
  const peaksQuery = useQuery({
    queryKey: ['voice', 'take-peaks', current?.assetId],
    queryFn: () => voiceApiClient.getTakePeaks(current?.assetId ?? ''),
    enabled: Boolean(current?.assetId),
    staleTime: Infinity,
    retry: false,
  });

  // Loop region: playback returns to its start when it passes the end.
  useEffect(() => {
    if (loop && playbackTime >= loop.end) onSeek(loop.start);
  }, [loop, onSeek, playbackTime]);
  useEffect(() => setLoop(null), [current?.key]);

  function waveformPosition(event: MouseEvent<HTMLCanvasElement>): number {
    const bounds = event.currentTarget.getBoundingClientRect();
    const fraction = bounds.width ? Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width)) : 0;
    return fraction * Math.max(duration, 0);
  }

  function onWaveformKey(event: KeyboardEvent<HTMLCanvasElement>) {
    if (event.key === 'ArrowLeft') onSeek(Math.max(0, playbackTime - 2));
    if (event.key === 'ArrowRight') onSeek(Math.min(duration, playbackTime + 2));
  }

  return (
    <footer className="voice-transport" aria-label="Transport">
      <audio
        ref={audioRef}
        src={current?.dataUrl ?? undefined}
        preload="metadata"
        onLoadedMetadata={(event) => onLoadedDuration(event.currentTarget.duration || current?.duration || 0)}
        onTimeUpdate={(event) => onTimeUpdate(event.currentTarget.currentTime)}
        onEnded={onEnded}
      />
      <div className="voice-transport-controls">
        <button type="button" aria-label="Previous take" onClick={() => onSelectOffset(-1)}>↢</button>
        <button className="main-play" type="button" aria-label={isPlaying ? 'Pause' : 'Play'} onClick={onTogglePlayback}>{isPlaying ? 'Ⅱ' : '▶'}</button>
        <button type="button" aria-label="Next take" onClick={() => onSelectOffset(1)}>↣</button>
      </div>
      <div className="voice-transport-title"><b>Now Playing</b><span>{title}</span></div>
      <div className="voice-transport-wave">
        <PeaksCanvas
          peaks={peaksQuery.data?.peaks ?? null}
          progress={duration ? playbackTime / duration : 0}
          loop={loop && duration ? { start: loop.start / duration, end: loop.end / duration } : null}
          onClick={(event) => onSeek(waveformPosition(event))}
          onShiftDrag={(start, end) => setLoop(end - start > 0.2 ? { start, end } : null)}
          toTime={waveformPosition}
          onKeyDown={onWaveformKey}
        />
        <input aria-label="Voice playback position" className="now-playing-seek" type="range" min={0} max={Math.max(duration, 0.1)} step="0.01" value={Math.min(playbackTime, duration)} onChange={(event) => onSeek(Number(event.currentTarget.value))} />
      </div>
      <span className="voice-transport-time">{formatPlaybackTime(playbackTime)} / {formatPlaybackTime(duration)}</span>
      <div className="voice-transport-actions">
        <button type="button" aria-pressed={Boolean(loop)} title="Shift-drag on the waveform to set a loop region" onClick={() => setLoop(null)} disabled={!loop}>Loop off</button>
        <button type="button" title="Switch to the previous take at the same position" disabled={!previous} onClick={onCompare}>A/B</button>
        <button type="button" aria-label="Download take" onClick={onDownload} disabled={!current}>⇩</button>
      </div>
    </footer>
  );
}

export function PeaksCanvas({ peaks, progress, loop, onClick, onShiftDrag, toTime, onKeyDown }: {
  peaks: number[] | null;
  progress: number;
  loop: { start: number; end: number } | null;
  onClick: (event: MouseEvent<HTMLCanvasElement>) => void;
  onShiftDrag: (start: number, end: number) => void;
  toTime: (event: MouseEvent<HTMLCanvasElement>) => number;
  onKeyDown: (event: KeyboardEvent<HTMLCanvasElement>) => void;
}) {
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const dragStart = useRef<number | null>(null);

  useEffect(() => {
    const element = canvas.current;
    // Nothing to draw until the take's peaks arrive.
    if (!element || !peaks?.length) return;
    const context = element.getContext('2d');
    if (!context) return;
    const width = element.clientWidth || 600;
    const height = element.clientHeight || 40;
    const scale = window.devicePixelRatio || 1;
    element.width = width * scale;
    element.height = height * scale;
    context.setTransform(scale, 0, 0, scale, 0, 0);
    context.clearRect(0, 0, width, height);
    const style = getComputedStyle(element);
    const played = style.getPropertyValue('--voice-wave-played').trim() || '#6366f1';
    const rest = style.getPropertyValue('--voice-wave-rest').trim() || '#64748b';
    const region = style.getPropertyValue('--voice-wave-loop').trim() || 'rgba(245, 158, 11, 0.18)';
    if (loop) {
      context.fillStyle = region;
      context.fillRect(loop.start * width, 0, (loop.end - loop.start) * width, height);
    }
    const values = peaks && peaks.length ? peaks : [];
    const bar = values.length ? width / values.length : width;
    values.forEach((peak, index) => {
      const barHeight = Math.max(1, peak * (height - 4));
      context.fillStyle = index / values.length <= progress ? played : rest;
      context.fillRect(index * bar, (height - barHeight) / 2, Math.max(1, bar - 1), barHeight);
    });
  }, [loop, peaks, progress]);

  return (
    <canvas
      ref={canvas}
      className="voice-waveform"
      role="img"
      aria-label={peaks ? 'Waveform of the current take; click to seek, Shift-drag to loop' : 'No waveform yet'}
      tabIndex={0}
      onKeyDown={onKeyDown}
      onMouseDown={(event) => { dragStart.current = event.shiftKey ? toTime(event) : null; }}
      onMouseUp={(event) => {
        if (dragStart.current !== null) {
          const end = toTime(event);
          onShiftDrag(Math.min(dragStart.current, end), Math.max(dragStart.current, end));
          dragStart.current = null;
        } else {
          onClick(event);
        }
      }}
    />
  );
}
