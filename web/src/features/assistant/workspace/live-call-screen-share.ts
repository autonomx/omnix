import { unwrap } from '../../../api/http';
import { ASSISTANT_LIVE_VOICE_CALL_START_EVENT, ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT } from '../../../events/bus';
import { api } from '../api/gateway';
import { assistantContextStore, stopDesktopShare } from './assistant-context-store';
import { cameraFrameFrom } from './live-call-camera';
import { failureStatus, reportLiveCallFailure } from './live-call-health';
import { liveConversationStore } from './live-conversation-store';

/**
 * The shared screen in a live call (D2, 2026-11-23). The screen is shared the way typed chat shares it (the person's
 * Share screen press, `toggleDesktopShare`); typed chat sends its frames with the message, but a call's spoken turn
 * must not wait on a picture. In a call, one frame goes to the gateway as the person begins (a glance): when their
 * speech is confirmed and as the call starts. The vision model describes it in the background, and the turn says
 * `screen_shared`, so the reply takes the newest description. The gateway keeps only the description.
 */

/** A screen glance's longest side: text on a screen needs more pixels than a face. */
export const SCREEN_SHARE_LONGEST_SIDE = 1280;
/** A turn whose chat had no screen glance this recently sends one first. */
export const SCREEN_SHARE_TURN_FRESH_MS = 15_000;
/** Glances on speech are at most this often. */
export const SCREEN_SHARE_MIN_GLANCE_MS = 4_000;

const UNAVAILABLE: Record<string, string> = {
  vision_not_configured: 'No vision model is set up, so the call cannot see the shared screen.',
  remote_vision_not_allowed: 'The screen picture would go to a remote model; allow remote vision in Settings → Assistant & Chat → Desktop Companion to share it in a call.',
  vision_unavailable: 'The vision model is unavailable, so the call cannot see the shared screen.',
};

let lastGlance: { sessionId: string; at: number } | null = null;

export function screenShared(): boolean {
  return assistantContextStore.getState().desktopShare !== null;
}

function glanceOnSpeech(): void {
  const sessionId = liveConversationStore.getState().sessionId;
  if (!sessionId || !screenShared()) return;
  const recent = lastGlance && lastGlance.sessionId === sessionId && Date.now() - lastGlance.at < SCREEN_SHARE_MIN_GLANCE_MS;
  if (!recent) void glanceScreenShare(sessionId);
}

/** Sends one frame of the shared screen for this chat's next spoken turn. Returns whether it is being described. */
export async function glanceScreenShare(sessionId: string): Promise<boolean> {
  const share = assistantContextStore.getState().desktopShare;
  if (!share) return false;
  const image = cameraFrameFrom(share.video, SCREEN_SHARE_LONGEST_SIDE);
  if (!image) return false;
  lastGlance = { sessionId, at: Date.now() };
  let status: string;
  try {
    const data = await unwrap(api.POST('/api/chat/sessions/{session_id}/screen/glance', {
      params: { path: { session_id: sessionId } },
      body: { image },
    }));
    status = data.status;
  } catch (error) {
    lastGlance = null;
    reportLiveCallFailure('screen_glance', { status: failureStatus(error) });
    return false;
  }
  const unavailable = UNAVAILABLE[status];
  if (unavailable) {
    // The call cannot see the screen: sharing stops rather than going on unseen, and says why.
    stopDesktopShare({ resetStatus: false });
    assistantContextStore.update({ desktopStatus: unavailable });
    return false;
  }
  return true;
}

/**
 * The fields a call's spoken turn adds while the screen is shared. A chat without a recent glance sends one first, so
 * the turn finds a description being made; the turn itself never carries a picture.
 */
export async function screenShareTurnFields(sessionId: string): Promise<{ screen_shared?: true }> {
  if (!screenShared()) return {};
  const fresh = lastGlance && lastGlance.sessionId === sessionId && Date.now() - lastGlance.at < SCREEN_SHARE_TURN_FRESH_MS;
  if (!fresh) await glanceScreenShare(sessionId);
  return screenShared() ? { screen_shared: true } : {};
}

export function initializeLiveCallScreenShare(): () => void {
  window.addEventListener(ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT, glanceOnSpeech);
  window.addEventListener(ASSISTANT_LIVE_VOICE_CALL_START_EVENT, glanceOnSpeech);
  return () => {
    window.removeEventListener(ASSISTANT_LIVE_VOICE_USER_SPEECH_EVENT, glanceOnSpeech);
    window.removeEventListener(ASSISTANT_LIVE_VOICE_CALL_START_EVENT, glanceOnSpeech);
    lastGlance = null;
  };
}

export function resetLiveCallScreenShareForTests(): void {
  lastGlance = null;
}
