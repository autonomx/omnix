import { fireEvent, render, screen } from '@testing-library/react';
import type { UseFormRegisterReturn } from 'react-hook-form';
import { describe, expect, it, vi } from 'vitest';
import { RpgActionComposer } from './RpgActionComposer';
import { previewSessionSummary, quickActions } from './rpgUiState';

function registration(name: 'sessionId' | 'command'): UseFormRegisterReturn<typeof name> {
  return {
    name,
    onBlur: vi.fn(),
    onChange: vi.fn(),
    ref: vi.fn(),
  };
}

describe('RpgActionComposer', () => {
  it('renders replay-preserving turn controls and quick actions', () => {
    const onQuickAction = vi.fn();
    const onSubmit = vi.fn((event: React.FormEvent<HTMLFormElement>) => event.preventDefault());

    render(
      <RpgActionComposer
        commandRegistration={registration('command')}
        hasCommandError={false}
        isPending={false}
        onQuickAction={onQuickAction}
        onSubmit={onSubmit}
        quickActions={quickActions}
        sessionRegistration={registration('sessionId')}
        sessionSummaries={[previewSessionSummary]}
      />
    );

    expect(screen.getByRole('heading', { name: 'Turn request' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Queue RPG turn' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Session' })).toHaveTextContent('Preview campaign — preview-session');
    expect(screen.getByRole('textbox', { name: 'Command' })).toHaveAttribute('aria-invalid', 'false');

    fireEvent.click(screen.getByRole('button', { name: 'Investigate' }));

    expect(onQuickAction).toHaveBeenCalledWith('Investigate the clawed tracks and torn Northern Watch banner.');
  });

  it('renders pending and invalid states for queued turn submission', () => {
    render(
      <RpgActionComposer
        commandRegistration={registration('command')}
        hasCommandError
        isPending
        onQuickAction={vi.fn()}
        onSubmit={vi.fn()}
        quickActions={quickActions}
        sessionRegistration={registration('sessionId')}
        sessionSummaries={[]}
      />
    );

    expect(screen.getByRole('button', { name: /Queueing/ })).toBeDisabled();
    expect(screen.getByRole('textbox', { name: 'Command' })).toHaveAttribute('aria-invalid', 'true');
  });
});
