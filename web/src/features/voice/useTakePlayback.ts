import { useEffect, useRef, useState, type RefObject } from 'react';
import { downloadUrl } from '../../shared/download';
import { safeDownloadName } from './voiceAssets';
import type { PlayableVoiceOutput } from './voiceOutputs';

/**
 * The transport's playback: play and pause (Space when focus is not in a field), scrub, step
 * between takes, A/B against the previous take at the same position, and download.
 */
export function useTakePlayback({ audioRef, outputs, current, previous, selectOutput, onMessage }: {
  audioRef: RefObject<HTMLAudioElement | null>;
  outputs: PlayableVoiceOutput[];
  current: PlayableVoiceOutput | null;
  previous: PlayableVoiceOutput | null;
  selectOutput: (key: string) => void;
  onMessage: (message: string) => void;
}) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackTime, setPlaybackTime] = useState(0);
  const [playbackDuration, setPlaybackDuration] = useState(0);
  const pendingSeek = useRef<number | null>(null);
  const toggleRef = useRef<() => void>(() => {});

  useEffect(() => {
    setPlaybackTime(0);
    setPlaybackDuration(current?.duration ?? 0);
    setIsPlaying(false);
    audioRef.current?.pause();
  }, [audioRef, current?.duration, current?.key]);

  useEffect(() => {
    function onKeyDown(event: globalThis.KeyboardEvent) {
      const target = event.target instanceof HTMLElement ? event.target : null;
      const inField = target?.closest('input, textarea, select, button, a, [contenteditable="true"], .cm-editor');
      if (event.key === ' ' && !inField && !event.repeat) {
        event.preventDefault();
        toggleRef.current();
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  async function toggle() {
    const audio = audioRef.current;
    if (!audio || !current) {
      onMessage('Generate speech before playing audio.');
      return;
    }
    if (isPlaying) {
      audio.pause();
      setIsPlaying(false);
      return;
    }
    try {
      await audio.play();
      setIsPlaying(true);
    } catch (error) {
      onMessage(error instanceof Error ? error.message : 'Audio playback could not start.');
    }
  }

  useEffect(() => {
    toggleRef.current = () => { void toggle(); };
  });

  function seek(value: number) {
    setPlaybackTime(value);
    if (audioRef.current) audioRef.current.currentTime = value;
  }

  function selectOffset(offset: number) {
    if (!outputs.length) return;
    const index = Math.max(0, outputs.findIndex((output) => output.key === current?.key));
    selectOutput(outputs[(index + offset + outputs.length) % outputs.length].key);
  }

  function compare() {
    if (!previous) return;
    pendingSeek.current = playbackTime;
    selectOutput(previous.key);
  }

  function download() {
    if (!current) {
      onMessage('Generate speech before saving output.');
      return;
    }
    const url = current.assetId ? `/api/assets/${encodeURIComponent(current.assetId)}/download` : current.dataUrl;
    downloadUrl(url, `${safeDownloadName(current.title)}.wav`);
  }

  function loadedDuration(duration: number) {
    setPlaybackDuration(duration);
    if (pendingSeek.current !== null) {
      seek(Math.min(pendingSeek.current, duration));
      pendingSeek.current = null;
    }
  }

  return {
    isPlaying,
    setIsPlaying,
    playbackTime,
    setPlaybackTime,
    playbackDuration,
    toggle,
    seek,
    selectOffset,
    compare,
    download,
    loadedDuration,
  };
}
