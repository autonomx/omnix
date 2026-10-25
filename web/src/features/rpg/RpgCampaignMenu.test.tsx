import { fireEvent, screen, within } from '@testing-library/react';
import type { UseFormRegisterReturn } from 'react-hook-form';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RpgCampaignMenu } from './RpgCampaignMenu';
import { rpgSessionClient } from './api/rpgSessionClient';
import { renderWithProviders } from '../../test/renderWithProviders';

function registration(): UseFormRegisterReturn<'sessionId'> {
  return { name: 'sessionId', onBlur: vi.fn(), onChange: vi.fn(), ref: vi.fn() };
}

function renderMenu(overrides: Partial<Parameters<typeof RpgCampaignMenu>[0]> = {}) {
  return renderWithProviders(
    <RpgCampaignMenu
      isPending={false}
      liveSessionId=""
      onTurnApplied={vi.fn()}
      renderNewCampaign={() => <div>Full campaign options</div>}
      selectedSessionId=""
      sessionRegistration={registration()}
      sessionSummaries={[]}
      {...overrides}
    />
  );
}

const SAVE_POINTS = {
  ok: true,
  session_id: 'session-live',
  save_points: [{ name: 'Before the gate', revision: 4, created_at: '2026-10-25T08:00:00Z' }],
};

describe('RpgCampaignMenu', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('routes New Campaign into the campaign wizard, and offers no older setup', () => {
    renderMenu();

    fireEvent.click(screen.getByRole('button', { name: 'Campaign Menu' }));
    expect(screen.queryByRole('button', { name: /^New Game/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Settings/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Save points/ })).toBeDisabled(); // no campaign to save
    fireEvent.click(screen.getByRole('button', { name: /^New Campaign/ }));

    expect(screen.getByRole('dialog', { name: 'New Campaign' })).toBeInTheDocument();
    expect(screen.getByText('Full campaign options')).toBeInTheDocument();
  });

  it('names this moment a save point and lists it', async () => {
    vi.spyOn(rpgSessionClient, 'listRpgSavePoints').mockResolvedValue({ ...SAVE_POINTS, save_points: [] });
    const create = vi.spyOn(rpgSessionClient, 'createRpgSavePoint').mockResolvedValue(SAVE_POINTS);
    renderMenu({ liveSessionId: 'session-live' });

    fireEvent.click(screen.getByRole('button', { name: 'Campaign Menu' }));
    fireEvent.click(screen.getByRole('button', { name: /^Save points/ }));
    expect(await screen.findByText('No save points yet.')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', { name: 'Name this moment' }), { target: { value: ' Before the gate ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save here' }));

    const list = await screen.findByRole('list', { name: 'Your save points' });
    expect(create).toHaveBeenCalledWith('session-live', 'Before the gate');
    expect(within(list).getByText('Before the gate')).toBeInTheDocument();
    expect(await screen.findByText('Saved as “Before the gate”.')).toBeInTheDocument();
  });

  it('returns to a save point as a turn, and the play screen refreshes', async () => {
    vi.spyOn(rpgSessionClient, 'listRpgSavePoints').mockResolvedValue(SAVE_POINTS);
    const rewind = vi.spyOn(rpgSessionClient, 'rewindRpgSession').mockResolvedValue({} as never);
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const onTurnApplied = vi.fn();
    renderMenu({ liveSessionId: 'session-live', onTurnApplied });

    fireEvent.click(screen.getByRole('button', { name: 'Campaign Menu' }));
    fireEvent.click(screen.getByRole('button', { name: /^Save points/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Return here' }));

    await vi.waitFor(() => expect(onTurnApplied).toHaveBeenCalledTimes(1));
    expect(rewind).toHaveBeenCalledWith('session-live', 'Before the gate');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('tells the player why a save point was refused', async () => {
    const { ApiError } = await import('../../api/errors');
    vi.spyOn(rpgSessionClient, 'listRpgSavePoints').mockResolvedValue({ ...SAVE_POINTS, save_points: [] });
    vi.spyOn(rpgSessionClient, 'createRpgSavePoint').mockRejectedValue(new ApiError(409, JSON.stringify({
      detail: { ok: false, error: 'save_points_full', message: 'A campaign keeps at most 20 save points.' },
    })));
    renderMenu({ liveSessionId: 'session-live' });

    fireEvent.click(screen.getByRole('button', { name: 'Campaign Menu' }));
    fireEvent.click(screen.getByRole('button', { name: /^Save points/ }));
    fireEvent.change(await screen.findByRole('textbox', { name: 'Name this moment' }), { target: { value: 'One more' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save here' }));

    expect(await screen.findByText('A campaign keeps at most 20 save points.')).toBeInTheDocument();
  });
});
