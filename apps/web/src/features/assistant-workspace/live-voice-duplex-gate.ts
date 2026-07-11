const PLAYBACK_STATE_EVENT = 'omnix:assistant-audio-playback-state';
const trackedStreams = new Set<MediaStream>();
let assistantSpeaking = false;

export function initializeLiveVoiceDuplexGate(): () => void {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') return () => undefined;
  const mediaDevices = navigator.mediaDevices;
  if (!mediaDevices?.getUserMedia) return () => undefined;

  const originalGetUserMedia = mediaDevices.getUserMedia.bind(mediaDevices);
  const patchedGetUserMedia: typeof mediaDevices.getUserMedia = async (constraints) => {
    const stream = await originalGetUserMedia(constraints);
    if (constraints?.audio && document.querySelector('.assistant-live-card')) trackLiveVoiceStream(stream);
    return stream;
  };
  mediaDevices.getUserMedia = patchedGetUserMedia;

  const handlePlaybackState = (event: Event): void => {
    const detail = (event as CustomEvent<{ speaking?: boolean }>).detail;
    assistantSpeaking = Boolean(detail?.speaking);
    applyDuplexGate();
  };
  window.addEventListener(PLAYBACK_STATE_EVENT, handlePlaybackState);

  const observer = new MutationObserver(() => {
    const speaking = Array.from(document.querySelectorAll<HTMLElement>('.assistant-voice-orb'))
      .some((orb) => orb.dataset.voiceMode === 'speaking');
    if (speaking !== assistantSpeaking) {
      assistantSpeaking = speaking;
      applyDuplexGate();
    }
  });
  if (document.body) {
    observer.observe(document.body, {
      subtree: true,
      attributes: true,
      attributeFilter: ['data-voice-mode'],
    });
  }

  return () => {
    observer.disconnect();
    window.removeEventListener(PLAYBACK_STATE_EVENT, handlePlaybackState);
    mediaDevices.getUserMedia = originalGetUserMedia;
    assistantSpeaking = false;
    applyDuplexGate();
    trackedStreams.clear();
  };
}

export function shouldMuteLiveMic(speaking: boolean): boolean {
  return speaking;
}

function trackLiveVoiceStream(stream: MediaStream): void {
  if (!stream.getAudioTracks().length) return;
  trackedStreams.add(stream);
  for (const track of stream.getAudioTracks()) {
    track.addEventListener('ended', () => {
      if (stream.getAudioTracks().every((candidate) => candidate.readyState === 'ended')) {
        trackedStreams.delete(stream);
      }
    }, { once: true });
  }
  applyDuplexGate();
}

function applyDuplexGate(): void {
  const enabled = !shouldMuteLiveMic(assistantSpeaking);
  for (const stream of Array.from(trackedStreams)) {
    const tracks = stream.getAudioTracks();
    if (!tracks.length || tracks.every((track) => track.readyState === 'ended')) {
      trackedStreams.delete(stream);
      continue;
    }
    for (const track of tracks) track.enabled = enabled;
  }
  document.querySelectorAll<HTMLElement>('.assistant-live-card').forEach((card) => {
    card.dataset.duplexGate = assistantSpeaking ? 'assistant-speaking' : 'listening';
  });
}

if (typeof window !== 'undefined') initializeLiveVoiceDuplexGate();
