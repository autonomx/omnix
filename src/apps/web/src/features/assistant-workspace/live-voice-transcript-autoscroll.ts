const TRANSCRIPT_SELECTOR = '.assistant-voice-transcript';
const installedTranscripts = new WeakSet<HTMLElement>();

export function initializeLiveVoiceTranscriptAutoscroll(root: ParentNode = document): () => void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return () => undefined;

  const attach = (): void => {
    root.querySelectorAll<HTMLElement>(TRANSCRIPT_SELECTOR).forEach((transcript) => {
      if (installedTranscripts.has(transcript)) return;
      installedTranscripts.add(transcript);
      const observer = new MutationObserver(() => scrollTranscriptToLatest(transcript));
      observer.observe(transcript, {
        childList: true,
        subtree: true,
        characterData: true,
      });
      transcript.addEventListener('omnix:transcript-dispose', () => observer.disconnect(), { once: true });
      scrollTranscriptToLatest(transcript);
    });
  };

  attach();
  const rootNode = root instanceof Document ? root.documentElement : root as Node;
  const observer = new MutationObserver(attach);
  observer.observe(rootNode, { childList: true, subtree: true });

  return () => {
    observer.disconnect();
    root.querySelectorAll<HTMLElement>(TRANSCRIPT_SELECTOR).forEach((transcript) => {
      transcript.dispatchEvent(new Event('omnix:transcript-dispose'));
    });
  };
}

export function scrollTranscriptToLatest(transcript: HTMLElement): void {
  const schedule = typeof window.requestAnimationFrame === 'function'
    ? window.requestAnimationFrame.bind(window)
    : (callback: FrameRequestCallback) => Number(window.setTimeout(() => callback(performance.now()), 0));
  schedule(() => {
    transcript.scrollTop = transcript.scrollHeight;
  });
}

if (typeof window !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => initializeLiveVoiceTranscriptAutoscroll(), { once: true });
  } else initializeLiveVoiceTranscriptAutoscroll();
}
