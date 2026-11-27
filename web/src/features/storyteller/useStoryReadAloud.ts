/**
 * A story page read aloud in the reader (ST-4.3) or the writing manuscript: which page and line is being heard,
 * pause, skip and stop, the pages after it read on in turn when asked for, and "read new pages aloud" (off unless the
 * reader turns it on, as the RPG's). Lines are read with the story's read
 * settings: the paragraph pause between them, the word notes in what is sent.
 */
import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { loadSettingsProfile, storytellerDefaults } from '../settings';
import type { StoryProject } from './api/storyClient';
import { readStoryPage, setStoryAutoplay, storyAutoplay, type StoryReader } from './storySpeech';
import { storyReadSettings } from './storyReadSettings';

export type StorySpeaking = { pageId: string; line: number | null };

export type StoryReadAloud = {
  speaking: StorySpeaking | null;
  paused: boolean;
  /** The last page asked for could not be heard: the speech service is down or the page has no voice. */
  silent: boolean;
  autoplay: boolean;
  setAutoplay: (on: boolean) => void;
  /** Reads the page; once it is heard to its end, the page `next` names after it, if any, and so on. */
  play: (pageId: string, next?: (pageId: string) => string | null) => void;
  pause: () => void;
  resume: () => void;
  skip: () => void;
  stop: () => void;
};

export function useStoryReadAloud(project: StoryProject | null): StoryReadAloud {
  const settingsQuery = useQuery({ queryKey: ['settings', 'profile'], queryFn: () => loadSettingsProfile() });
  const settings = storyReadSettings(storytellerDefaults(settingsQuery.data?.profile), project?.read_settings);
  const read = useRef({ pauseMs: settings.pauseParagraphMs, pronunciation: settings.pronunciation });
  read.current = { pauseMs: settings.pauseParagraphMs, pronunciation: settings.pronunciation };
  const [speaking, setSpeaking] = useState<StorySpeaking | null>(null);
  const [paused, setPaused] = useState(false);
  const [silent, setSilent] = useState(false);
  const [autoplay, setAutoplayState] = useState(storyAutoplay);
  const reader = useRef<StoryReader | null>(null);
  const projectId = project?.id ?? null;

  const stop = useCallback(() => {
    reader.current?.stop();
    reader.current = null;
    setSpeaking(null);
    setPaused(false);
  }, []);

  const play = useCallback((pageId: string, next?: (pageId: string) => string | null) => {
    if (!projectId) return;
    const start = (id: string) => {
      reader.current?.stop();
      setSilent(false);
      setPaused(false);
      setSpeaking({ pageId: id, line: null });
      const current = readStoryPage(projectId, id, {
        ...read.current,
        onLine: (line) => {
          if (reader.current === current && line !== null) setSpeaking({ pageId: id, line });
        },
      });
      reader.current = current;
      void current.outcome.then((outcome) => {
        if (reader.current !== current) return;
        // A page heard to its end goes on to the one after it as the story stands now (a page restored or
        // replaced meanwhile is read as it is); a stop or a silent page ends the reading there.
        const following = outcome === 'played' ? next?.(id) ?? null : null;
        if (following) {
          start(following);
          return;
        }
        reader.current = null;
        setSpeaking(null);
        setPaused(false);
        setSilent(outcome === 'silent');
      });
    };
    start(pageId);
  }, [projectId]);

  useEffect(() => stop, [projectId, stop]);  // another story, or the reader gone: the page stops

  return {
    speaking, paused, silent, autoplay, play, stop,
    setAutoplay: (on) => {
      setStoryAutoplay(on);
      setAutoplayState(on);
    },
    pause: () => {
      reader.current?.pause();
      if (reader.current) setPaused(true);
    },
    resume: () => {
      reader.current?.resume();
      setPaused(false);
    },
    skip: () => reader.current?.skip(),
  };
}
