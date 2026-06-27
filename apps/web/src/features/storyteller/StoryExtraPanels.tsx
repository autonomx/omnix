import { StoryChapterMediaPanel } from './StoryChapterMediaPanel';
import { StoryReadPanel } from './StoryReadPanel';
import { StoryRemotePanel } from './StoryRemotePanel';

export function StoryExtraPanels() {
  return (
    <>
      <StoryReadPanel />
      <StoryChapterMediaPanel />
      <StoryRemotePanel />
    </>
  );
}
