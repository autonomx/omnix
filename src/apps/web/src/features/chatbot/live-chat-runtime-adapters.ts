export type LiveChatMirroredAvatar = {
  imageUrl: string | null;
  alt: string;
  backgroundImage: string;
  mouthFrame: string;
  voiceMode: string;
};

/** Mirrors the avatar bridge's rendered output; the bridge remains the only animation owner. */
export function readLiveChatMirroredAvatar(root: ParentNode = document): LiveChatMirroredAvatar {
  const host = root.querySelector<HTMLElement>('.assistant-live-character-avatar');
  const image = host?.querySelector<HTMLImageElement>('img') ?? null;
  return {
    imageUrl: image?.currentSrc || image?.src || null,
    alt: image?.alt || 'Live assistant avatar',
    backgroundImage: host?.style.backgroundImage || '',
    mouthFrame: host?.dataset.mouthFrame || 'closed',
    voiceMode: host?.dataset.voiceMode || 'idle',
  };
}

