import { parseChatUi } from './schema';

type ProjectableMessage = { content: string; metadata?: Record<string, unknown> | null };

/**
 * What copying a message gives: the reply's text projection when it renders generative UI,
 * otherwise its content. Copy never contains block JSON (roadmap §6.4).
 */
export function chatMessageText(message: ProjectableMessage): string {
  return parseChatUi(message.metadata, message.content)?.text ?? message.content;
}

/**
 * What audio reads: the speech projection (blocks summarized, tables and code described)
 * when the reply renders generative UI, otherwise its content. Audio never reads JSON.
 */
export function chatMessageSpeech(message: ProjectableMessage): string {
  return parseChatUi(message.metadata, message.content)?.speech ?? message.content;
}
