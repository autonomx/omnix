import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { LiveConversationControls } from './LiveConversationControls';

beforeEach(() => {
  window.localStorage.clear();
});

describe('LiveConversationControls', () => {
  it('renders the existing live conversation settings as React controls', () => {
    render(<LiveConversationControls />);

    expect(screen.getByLabelText('Conversation pace')).toHaveValue('balanced');
    expect(screen.getByLabelText('Interruption behavior')).toHaveValue('balanced');
    expect(screen.getByLabelText('Spoken acknowledgements')).toHaveValue('off');
  });

  it('persists changes without removing other assistant settings', () => {
    window.localStorage.setItem('omnix.chatbot.assistantSettings', JSON.stringify({ voiceId: 'Maya' }));
    render(<LiveConversationControls />);

    fireEvent.change(screen.getByLabelText('Conversation pace'), { target: { value: 'reflective' } });
    fireEvent.change(screen.getByLabelText('Interruption behavior'), { target: { value: 'easy' } });
    fireEvent.change(screen.getByLabelText('Spoken acknowledgements'), { target: { value: 'natural' } });

    const canonical = JSON.parse(window.localStorage.getItem('omnix.liveConversation.settings') || '{}');
    const legacy = JSON.parse(window.localStorage.getItem('omnix.chatbot.assistantSettings') || '{}');
    expect(canonical).toEqual({
      conversationPace: 'reflective',
      interruptionPreference: 'easy',
      backchannelMode: 'natural',
    });
    expect(legacy).toMatchObject({ voiceId: 'Maya', conversationPace: 'reflective' });
  });
});
