import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RpgStoryScene } from './RpgStoryScene';
import { previewHeroSummary, previewRecentEvents, previewSessionSummary } from './rpgUiPreview';
import { renderWithProviders } from '../../test/renderWithProviders';


describe('RpgStoryScene', () => {
  it('renders the place, the time, the story and its controls, with nothing else around them', () => {
    renderWithProviders(
      <RpgStoryScene
        heroSummary={previewHeroSummary}
        recentEvents={previewRecentEvents}
        selectedSessionSummary={previewSessionSummary}
        timeLabel="Day 1 • 09:00"
      >
        <button type="button">Submit RPG turn</button>
      </RpgStoryScene>
    );

    expect(screen.getByRole('region', { name: /Glimmerdeep Pass/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Glimmerdeep Pass' })).toBeInTheDocument();
    expect(screen.getByText('Day 1 • 09:00')).toBeInTheDocument();
    expect(screen.getByLabelText('Glimmerdeep Pass scene preview')).toBeInTheDocument();
    expect(screen.getByText('Alyndra (You)')).toBeInTheDocument();
    expect(screen.getByText('Omnix (Narrator)')).toBeInTheDocument();
    expect(screen.getByLabelText('Conversation')).toHaveClass('rpg-dialogue-stack');
    expect(screen.getByRole('button', { name: 'Submit RPG turn' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Recent events' })).not.toBeInTheDocument(); // the Journal's history
    expect(screen.queryByText('Turn 12')).not.toBeInTheDocument();
  });

  it('gives a fight the stage above the story', () => {
    renderWithProviders(
      <RpgStoryScene
        heroSummary={previewHeroSummary}
        recentEvents={[]}
        selectedSessionSummary={previewSessionSummary}
        stage={<div>The board</div>}
      >
        <button type="button">Submit RPG turn</button>
      </RpgStoryScene>
    );
    const board = screen.getByText('The board');
    expect(board.compareDocumentPosition(screen.getByLabelText('Conversation')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('renders the bounded durable transcript without dropping messages after the oldest ten', () => {
    const storyMessages = Array.from({ length: 12 }, (_, index) => ({
      id: `message:${index + 1}`,
      interactionId: `interaction:${index + 1}`,
      avatar: 'A',
      speaker: 'Alyndra (You)',
      text: `Durable message ${index + 1}`,
      tone: 'player' as const,
    }));

    renderWithProviders(
      <RpgStoryScene
        heroSummary={previewHeroSummary}
        recentEvents={[]}
        selectedSessionSummary={{ ...previewSessionSummary, id: 'live-session', source: 'live' }}
        storyMessages={storyMessages}
      >
        <button type="button">Submit RPG turn</button>
      </RpgStoryScene>
    );

    expect(screen.getByText('Durable message 1')).toBeInTheDocument();
    expect(screen.getByText('Durable message 12')).toBeInTheDocument();
    expect(screen.getByLabelText('Conversation').querySelectorAll('article')).toHaveLength(12);
  });

  it("shows a turn's outcome card as one chip per fact, gains and losses apart", () => {
    const storyMessages = [{
      id: 'interaction:1:outcome', interactionId: 'interaction:1', avatar: '✦', speaker: 'What changed',
      text: '-3 silver · +Healing Potion', tone: 'narrator' as const, messageKind: 'outcome',
      facts: [{ kind: 'coin', text: '-3 silver', tone: 'loss' as const },
              { kind: 'item', text: '+Healing Potion', tone: 'gain' as const }],
    }];
    renderWithProviders(
      <RpgStoryScene
        heroSummary={previewHeroSummary}
        recentEvents={[]}
        selectedSessionSummary={{ ...previewSessionSummary, id: 'live-card', source: 'live' }}
        storyMessages={storyMessages}
      >
        <button type="button">Submit RPG turn</button>
      </RpgStoryScene>
    );

    const card = screen.getByRole('list', { name: 'What changed' });
    expect(card.querySelectorAll('li')).toHaveLength(2);
    expect(screen.getByText('-3 silver')).toHaveClass('rpg-outcome-fact-loss');
    expect(screen.getByText('+Healing Potion')).toHaveClass('rpg-outcome-fact-gain');
  });

  describe('following the story', () => {
    const say = (count: number) => Array.from({ length: count }, (_, index) => ({
      id: `message:${index}`, interactionId: `interaction:${index}`, avatar: 'O', speaker: 'Omnix (Narrator)',
      text: `Line ${index}`, tone: 'narrator' as const,
    }));
    const scene = (count: number) => (
      <RpgStoryScene
        heroSummary={previewHeroSummary}
        recentEvents={[]}
        selectedSessionSummary={{ ...previewSessionSummary, id: `live-follow-${expect.getState().currentTestName}`, source: 'live' }}
        storyMessages={say(count)}
      >
        <button type="button">Submit RPG turn</button>
      </RpgStoryScene>
    );
    /** jsdom has no layout: the story is 100px tall and each message 50px. */
    const lay = (log: HTMLElement) => {
      Object.defineProperty(log, 'clientHeight', { configurable: true, value: 100 });
      Object.defineProperty(log, 'scrollHeight', { configurable: true, get: () => log.querySelectorAll('article').length * 50 });
    };

    it('shows the newest words when they arrive', () => {
      const { rerender } = renderWithProviders(scene(4));
      const log = screen.getByLabelText('Conversation');
      lay(log);
      rerender(scene(5));
      log.scrollTop = 150; // at the end: 150 + 100 is what was 250 tall
      rerender(scene(6));
      expect(log.scrollTop).toBe(300);
    });

    it('leaves a player who has scrolled back where they are', () => {
      const { rerender } = renderWithProviders(scene(4));
      const log = screen.getByLabelText('Conversation');
      lay(log);
      rerender(scene(5));
      log.scrollTop = 20;
      rerender(scene(6));
      expect(log.scrollTop).toBe(20);
    });
  });
});
