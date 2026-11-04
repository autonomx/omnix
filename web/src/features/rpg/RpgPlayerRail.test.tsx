import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { currentGoal, RpgPlayerRail } from './RpgPlayerRail';
import { activeQuests, heroStats as previewHeroStats, partyMembers, previewHeroSummary, previewSurvival } from './rpgUiPreview';
import { renderWithProviders } from '../../test/renderWithProviders';


const baseRailProps = {
  activeQuests,
  heroStats: previewHeroStats,
  heroSummary: previewHeroSummary,
  partyMembers,
  survival: previewSurvival,
};

const pressing = {
  ...previewSurvival,
  status: 'Warning' as const,
  warnings: ['Hunger High'],
};

describe('RpgPlayerRail', () => {
  it('shows the hero at a glance and leaves the rest to the play bar', () => {
    renderWithProviders(<RpgPlayerRail {...baseRailProps} />);

    expect(screen.getByRole('complementary', { name: 'Player, party, and quests' })).toBeInTheDocument();
    expect(screen.getByText('Alyndra')).toBeInTheDocument();
    expect(screen.getByLabelText('HP 86 / 110')).toBeInTheDocument();
    expect(screen.getByLabelText('XP 7,450 / 12,000')).toBeInTheDocument();
    expect(screen.getByText('Thorin Ironfist')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /The Frostbound Relic/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Add companion/ })).not.toBeInTheDocument();
    expect(screen.queryByText('Longbow of the Boreal Wind')).not.toBeInTheDocument();
  });

  it('shows survival only when the needs press', () => {
    const onSelectCommand = vi.fn();
    const { rerender } = renderWithProviders(<RpgPlayerRail {...baseRailProps} onSelectCommand={onSelectCommand} />);
    expect(screen.queryByRole('region', { name: 'Survival status' })).not.toBeInTheDocument();

    rerender(<RpgPlayerRail {...baseRailProps} onSelectCommand={onSelectCommand} survival={pressing} />);
    expect(screen.getByRole('region', { name: 'Survival status' })).toHaveTextContent('Hunger24 / 100');
    fireEvent.click(screen.getByRole('button', { name: 'Rest' }));
    expect(onSelectCommand).toHaveBeenCalledWith('I rest');
  });

  it('opens the quests from the goal, and has no party card without a party', () => {
    const onOpenQuests = vi.fn();
    renderWithProviders(<RpgPlayerRail {...baseRailProps} onOpenQuests={onOpenQuests} partyMembers={[]} />);
    fireEvent.click(screen.getByRole('button', { name: /The Frostbound Relic/ }));
    expect(onOpenQuests).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('region', { name: 'Party members' })).not.toBeInTheDocument();
  });

  it('names the quest under way as the goal, never a finished one', () => {
    const quest = (title: string, status: string) => ({ icon: '*', title, detail: '', status });
    expect(currentGoal([quest('Done', 'completed'), quest('Later', 'available'), quest('Now', 'active')])?.title).toBe('Now');
    expect(currentGoal([quest('Done', 'completed'), quest('Later', 'available')])?.title).toBe('Later');
    expect(currentGoal([quest('Done', 'completed')])).toBeUndefined();
  });
});
