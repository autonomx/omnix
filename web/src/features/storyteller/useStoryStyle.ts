import { useEffect, useRef, useState } from 'react';
import type { StoryProject } from './api/storyClient';
import { styleOptions } from './storyModel';

/**
 * The tone and writing style the next page is written in. A story opens with its own tone and style, and
 * `onOpen` hears of it (to show it in the mode it was written in), only when another project opens: a refetch
 * of the same one keeps the writer's choices.
 */
export function useStoryStyle(project: StoryProject | null, onOpen: (project: StoryProject) => void) {
  const [tone, setTone] = useState('Cozy');
  const [writingStyle, setWritingStyle] = useState(styleOptions[0]);
  const opened = useRef<string | null>(null);
  const onOpenRef = useRef(onOpen);
  useEffect(() => { onOpenRef.current = onOpen; });

  /** The tone and style a story or a preset gave it (ST-5.2); an empty one leaves the current choice. */
  const apply = (changed: Pick<StoryProject, 'tone' | 'writing_style'>) => {
    if (changed.tone) setTone(changed.tone);
    if (changed.writing_style) setWritingStyle(changed.writing_style);
  };
  useEffect(() => {
    if (!project || opened.current === project.id) return;
    opened.current = project.id;
    onOpenRef.current(project);
    if (project.tone) setTone(project.tone);
    if (project.writing_style) setWritingStyle(project.writing_style);
  }, [project]);

  return {
    tone, setTone, writingStyle, setWritingStyle, apply,
    /** A new draft: the next story opened applies its own tone and style again, even the one just closed. */
    forgetOpened: () => { opened.current = null; },
  };
}
