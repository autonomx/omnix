import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { RpgNarrativeTabs } from './RpgNarrativeTabs';
import type { RpgJournalDetailPreview, RpgJournalEntryPreview } from './rpgUiTypes';
import { renderWithProviders } from '../../test/renderWithProviders';

const journalDetail: RpgJournalDetailPreview = { title: 'Journal', detail: 'Daily accounts', bullets: [], tags: [] };
const days = (count: number): RpgJournalEntryPreview[] =>
  Array.from({ length: count }, (_, index) => ({ time: `Day ${count - index}`, title: `Entry ${count - index}`, detail: `Account of day ${count - index}` }));

beforeEach(() => {
  // jsdom has no layout: the journal list is 384px tall and every entry 48px.
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockImplementation(function (this: HTMLElement) {
    return this.classList.contains('rpg-journal-list') ? 384 : 48;
  });
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(400);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('RpgNarrativeTabs journal', () => {
  it('renders a bounded window of a thousand-day journal and still selects an entry', async () => {
    renderWithProviders(<RpgNarrativeTabs journalDetail={journalDetail} journalEntries={days(1_000)} logEntries={[]} recentEvents={[]} />);
    const panel = screen.getByRole('tabpanel');

    await waitFor(() => expect(within(panel).getAllByRole('button').length).toBeGreaterThan(0));
    expect(within(panel).getAllByRole('button').length).toBeLessThan(60);
    expect(within(panel).getByRole('heading', { name: 'Entry 1000' })).toBeInTheDocument();

    fireEvent.click(within(panel).getByRole('button', { name: /Day 999/ }));
    expect(within(panel).getByRole('heading', { name: 'Entry 999' })).toBeInTheDocument();
    expect(within(panel).getByRole('button', { name: /Day 999/ })).toHaveAttribute('aria-pressed', 'true');
  });

  it('renders every entry of a short journal', () => {
    renderWithProviders(<RpgNarrativeTabs journalDetail={journalDetail} journalEntries={days(12)} logEntries={[]} recentEvents={[]} />);
    expect(within(screen.getByRole('tabpanel')).getAllByRole('button')).toHaveLength(12);
  });
});

describe('RpgNarrativeTabs what has changed', () => {
  it('shows the lines of what the hero changed and each group standing in words', () => {
    renderWithProviders(
      <RpgNarrativeTabs
        journalDetail={journalDetail}
        journalEntries={days(2)}
        logEntries={[]}
        recentEvents={[]}
        worldChanges={{
          lines: ['The royal engine in Valecourt runs again, the crown keeps it.'],
          standing: [{ groupId: 'faction:meridian-crown', name: 'The Meridian Crown', band: 'respected' }],
          word: ['They say the warden has gone north.'],
        }}
      />,
    );
    fireEvent.click(screen.getByRole('tab', { name: 'What has changed' }));
    const panel = screen.getByRole('tabpanel');
    expect(within(panel).getByText('The royal engine in Valecourt runs again, the crown keeps it.')).toBeInTheDocument();
    expect(within(panel).getByText('The Meridian Crown')).toBeInTheDocument();
    expect(panel).toHaveTextContent('The Meridian Crown: respected');
    expect(within(panel).getByText('They say the warden has gone north.')).toBeInTheDocument();
  });

  it('says so when nothing has changed yet', () => {
    renderWithProviders(<RpgNarrativeTabs journalDetail={journalDetail} journalEntries={days(1)} logEntries={[]} recentEvents={[]} />);
    fireEvent.click(screen.getByRole('tab', { name: 'What has changed' }));
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Nothing you have done has changed the world yet.');
  });
});

describe('RpgNarrativeTabs quests and history', () => {
  it('lists every quest with how it stands, and can open on them', () => {
    renderWithProviders(
      <RpgNarrativeTabs
        initialTab="quests"
        journalDetail={journalDetail}
        journalEntries={days(1)}
        logEntries={[]}
        quests={[{ icon: '*', title: 'Black Rain Rising', detail: 'Prevent a flood.', status: 'active' }]}
        recentEvents={[]}
      />,
    );
    const panel = screen.getByRole('tabpanel', { name: 'Quests' });
    expect(within(panel).getByRole('heading', { name: 'Black Rain Rising' })).toBeInTheDocument();
    expect(panel).toHaveTextContent('active');
    expect(panel).toHaveTextContent('Prevent a flood.');
  });

  it('keeps one history in place of three logs, and filters it', () => {
    const logEntries = [
      { time: 'Turn 2', title: 'Completed turn', detail: 'Command: look around' },
      { time: 'Turn 1', title: 'Helix', detail: 'Helix says: all is well.' },
    ];
    renderWithProviders(
      <RpgNarrativeTabs journalDetail={journalDetail} journalEntries={days(1)} logEntries={logEntries} recentEvents={['A bell rings.']} />,
    );
    expect(screen.queryByRole('tab', { name: 'Dialogue log' })).not.toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'What you did' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'History' }));
    const panel = screen.getByRole('tabpanel', { name: 'History' });
    expect(panel).toHaveTextContent('Command: look around');
    expect(panel).toHaveTextContent('Helix says: all is well.');
    expect(panel).toHaveTextContent('A bell rings.');

    fireEvent.click(within(panel).getByRole('button', { name: 'What was said' }));
    expect(panel).toHaveTextContent('Helix says: all is well.');
    expect(panel).not.toHaveTextContent('A bell rings.');

    fireEvent.click(within(panel).getByRole('button', { name: 'What you did' }));
    expect(panel).toHaveTextContent('Command: look around');
    expect(panel).not.toHaveTextContent('Helix says');
  });
});
