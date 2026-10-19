import { describe, expect, it } from 'vitest';
import { chatMessageSpeech, chatMessageText } from './chatMessageProjection';
import type { FormBlock } from './schema';
import { chatUiSubmissions, fillFormTemplate, initialFormValues, missingRequiredFields } from './uiActions';

const content = 'Revenue held.\n\n```omnix-ui\n{"type": "stats", "items": [{"label": "Revenue", "value": "$6,930"}]}\n```';
const ui = {
  version: 1,
  compiler_version: 'gui-compiler-1',
  compiled_at: '2026-10-11T00:00:00Z',
  segments: [{ kind: 'markdown', start: 0, end: 15 }, { kind: 'block', id: 'b1', text: 'Revenue: $6,930.' }],
  blocks: { b1: { type: 'stats', id: 'b1', v: 1, items: [{ label: 'Revenue', value: '$6,930' }], provenance: 'model', bindings: [] } },
  text: 'Revenue held.\n\nRevenue: $6,930.',
  speech: 'Revenue held.\n\nRevenue $6,930.',
  diagnostics: [],
};

const form: FormBlock = {
  type: 'form', id: 'f1', v: 1, provenance: 'model', bindings: [],
  template: 'Run {symbol} at {risk}{unit} {flag} {note}',
  fields: [
    { name: 'symbol', label: 'Symbol', kind: 'select', required: true, options: ['AAPL', 'MSFT'] },
    { name: 'risk', label: 'Risk', kind: 'slider', required: false, min: 1, max: 5, step: 0.5, default: 2.5 },
    { name: 'flag', label: 'Flag', kind: 'toggle', required: false },
    { name: 'note', label: 'Note', kind: 'text', required: true, max_length: 50 },
  ],
};

describe('chat message projections', () => {
  it('copies the text projection and speaks the speech projection of a reply with UI', () => {
    const message = { content, metadata: { ui } };

    expect(chatMessageText(message)).toBe('Revenue held.\n\nRevenue: $6,930.');
    expect(chatMessageSpeech(message)).toBe('Revenue held.\n\nRevenue $6,930.');
    expect(chatMessageText(message)).not.toContain('{');
  });

  it('uses the content for a message without UI, or whose UI does not belong to it', () => {
    expect(chatMessageText({ content: 'Plain', metadata: {} })).toBe('Plain');
    expect(chatMessageSpeech({ content: 'Plain' })).toBe('Plain');
    expect(chatMessageText({ content: 'Short', metadata: { ui } })).toBe('Short');
    expect(chatMessageSpeech({ content, metadata: { ui, delivery_status: 'interrupted' } })).toBe(content);
  });
});

describe('ui actions', () => {
  it('fills a template in one pass, leaving braces typed into values alone', () => {
    const values = { ...initialFormValues(form), note: '{symbol} stays' };

    expect(fillFormTemplate(form, values)).toBe('Run AAPL at 2.5{unit} no {symbol} stays');
  });

  it('reports required fields that are still empty', () => {
    expect(missingRequiredFields(form, initialFormValues(form))).toEqual(['note']);
    expect(missingRequiredFields(form, { ...initialFormValues(form), note: 'x' })).toEqual([]);
  });

  it('rebuilds each widget submission from the latest user message that answered it', () => {
    const action = (index: number) => ({ source_message_id: 'msg:a', block_id: 'b1', action: 'choose', option_index: index });
    const submissions = chatUiSubmissions([
      { id: 'u1', role: 'user', content: 'First', metadata: { ui_action: action(0) } },
      { id: 'a1', role: 'assistant', content: 'x', metadata: { ui_action: action(5) } },
      { id: 'u2', role: 'user', content: 'Second', metadata: { ui_action: action(1) } },
      { id: 'u3', role: 'user', content: 'Forged', metadata: { ui_action: { block_id: 'b1' } } },
    ]);

    expect([...submissions.keys()]).toEqual(['msg:a']);
    expect(submissions.get('msg:a')?.b1).toEqual({ content: 'Second', action: { ...action(1), values: null } });
  });
});

describe('the fullscreen live-chat shell', () => {
  it('shows a block reply as its text projection', async () => {
    const { liveChatMessagesFor } = await import('../chatMessageModel');
    const rows = liveChatMessagesFor(
      [{ id: 'msg:ui', role: 'assistant', content, created_at: '2026-10-11T00:00:00Z', metadata: { ui } }],
      { rows: [], delivery: null } as unknown as Parameters<typeof liveChatMessagesFor>[1],
    );

    expect(rows[0].text).toBe('Revenue held.\n\nRevenue: $6,930.');
  });
});
