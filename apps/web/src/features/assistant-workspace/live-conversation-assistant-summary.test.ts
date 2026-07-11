import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  LIVE_ASSISTANT_TURN_SUMMARY_EVENT,
  observeAssistantDiagnostic,
  resetAssistantDiagnosticSummaries,
  summarizeAssistantTurn,
  type LiveAssistantTurnSummary,
} from './live-conversation-assistant-summary';

afterEach(() => resetAssistantDiagnosticSummaries());

describe('assistant turn summaries', () => {
  it('derives only bounded content-free features', () => {
    const summary = summarizeAssistantTurn(
      'Would you like to revisit the launch schedule tomorrow?',
      'assistant-one',
      'response',
    );

    expect(summary).toMatchObject({
      turnId: 'assistant-one',
      turnKind: 'response',
      questionCount: 1,
      createsObligation: true,
    });
    expect(summary.wordCount).toBeGreaterThan(5);
    expect(summary.topicFingerprint).toMatch(/^topic-[0-9a-f]{8}$/);
    expect(JSON.stringify(summary)).not.toContain('launch schedule');
  });

  it('emits the summary after the final text chunk and before audio drain', () => {
    const received: LiveAssistantTurnSummary[] = [];
    const listener = (event: Event) => {
      received.push((event as CustomEvent<LiveAssistantTurnSummary>).detail);
    };
    window.addEventListener(LIVE_ASSISTANT_TURN_SUMMARY_EVENT, listener);

    observeAssistantDiagnostic('trace-one', 'turn_intercepted', { turn_kind: 'response' });
    observeAssistantDiagnostic('trace-one', 'assistant_turn_linked', { assistant_turn_id: 'assistant-one' });
    observeAssistantDiagnostic('trace-one', 'llm_text_chunk_received', { text: 'Should we revisit ' });
    observeAssistantDiagnostic('trace-one', 'llm_text_chunk_received', { text: 'the launch schedule?' });
    observeAssistantDiagnostic('trace-one', 'llm_stream_finished', {});

    expect(received).toHaveLength(1);
    expect(received[0]).toMatchObject({
      turnId: 'assistant-one', questionCount: 1, createsObligation: true,
    });
    expect(JSON.stringify(received[0])).not.toContain('launch schedule');
    window.removeEventListener(LIVE_ASSISTANT_TURN_SUMMARY_EVENT, listener);
  });

  it('drops interrupted text without emitting a summary', () => {
    const listener = vi.fn();
    window.addEventListener(LIVE_ASSISTANT_TURN_SUMMARY_EVENT, listener);
    observeAssistantDiagnostic('trace-two', 'turn_intercepted', { turn_kind: 'response' });
    observeAssistantDiagnostic('trace-two', 'llm_text_chunk_received', { text: 'private text' });
    observeAssistantDiagnostic('trace-two', 'turn_stopped', {});
    expect(listener).not.toHaveBeenCalled();
    window.removeEventListener(LIVE_ASSISTANT_TURN_SUMMARY_EVENT, listener);
  });
});
