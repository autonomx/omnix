from __future__ import annotations

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"expected patch context missing in {path}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "src/apps/web/src/api/client.ts",
    "export type CreateChatSessionRequest = components['schemas']['CreateChatSessionRequest'];",
    """type GeneratedCreateChatSessionRequest = components['schemas']['CreateChatSessionRequest'];
export type CreateChatSessionRequest = Partial<GeneratedCreateChatSessionRequest>;""",
)
replace(
    "src/apps/web/src/api/client.ts",
    "export type SendChatMessageRequest = components['schemas']['SendChatMessageRequest'];",
    """type GeneratedSendChatMessageRequest = components['schemas']['SendChatMessageRequest'];
export type SendChatMessageRequest = Pick<GeneratedSendChatMessageRequest, 'content'>
  & Partial<Omit<GeneratedSendChatMessageRequest, 'content'>>;""",
)

replace(
    "src/apps/web/src/features/assistant-workspace/live-voice-pcm-session.ts",
    """type OutputTimestampSource = {
  getOutputTimestamp?: () => {
    contextTime: number;
    performanceTime: number;
  };
};""",
    """type OutputTimestampSource = {
  getOutputTimestamp?: () => {
    contextTime?: number;
    performanceTime?: number;
  };
};""",
)
replace(
    "src/apps/web/src/features/assistant-workspace/live-voice-pcm-session.ts",
    """    const timestamp = audioContext.getOutputTimestamp();
    if (!Number.isFinite(timestamp.contextTime) || !Number.isFinite(timestamp.performanceTime)) return null;
    const projected = timestamp.performanceTime
      + ((eventContextTime - timestamp.contextTime) * 1_000);""",
    """    const timestamp = audioContext.getOutputTimestamp();
    const { contextTime, performanceTime } = timestamp;
    if (typeof contextTime !== 'number' || !Number.isFinite(contextTime)
      || typeof performanceTime !== 'number' || !Number.isFinite(performanceTime)) return null;
    const projected = performanceTime
      + ((eventContextTime - contextTime) * 1_000);""",
)
