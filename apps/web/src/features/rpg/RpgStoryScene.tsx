import { useState, type ReactNode } from 'react';
import type { RpgHeroSummaryPreview, RpgSessionSummaryPreview, RpgStoryMessagePreview } from './rpgUiState';
import './RpgVisualAssets.css';

const SCENE_ART_SRC = '/rpg/glimmerdeep-pass-scene.svg';

interface RpgStorySceneProps {
  children: ReactNode;
  heroSummary: RpgHeroSummaryPreview;
  recentEvents: string[];
  selectedSessionSummary: RpgSessionSummaryPreview;
  storyMessages?: RpgStoryMessagePreview[];
}

export function RpgStoryScene({ children, heroSummary, recentEvents, selectedSessionSummary, storyMessages = [] }: RpgStorySceneProps) {
  const isPreview = selectedSessionSummary.source === 'preview';
  const [recentEventsExpanded, setRecentEventsExpanded] = useState(false);

  return (
    <section className="rpg-card rpg-story-card" aria-labelledby="rpg-story-scene-title">
      <div className="rpg-story-heading">
        <div>
          <p className="eyebrow">Story / scene</p>
          <h3 id="rpg-story-scene-title">📍 {selectedSessionSummary.location}</h3>
          <div className="rpg-chip-row">
            <span>{selectedSessionSummary.title}</span>
            <span>{selectedSessionSummary.turnLabel}</span>
            <span>{selectedSessionSummary.updatedAt}</span>
          </div>
        </div>
        <div
          className={isPreview ? 'rpg-scene-art rpg-scene-art-has-image' : 'rpg-scene-art'}
          aria-label={isPreview ? `${selectedSessionSummary.location} scene preview` : `${selectedSessionSummary.location} scene`}
        >
          {isPreview ? <img src={SCENE_ART_SRC} alt="" aria-hidden="true" /> : <span className="rpg-live-visual-label">Live scene</span>}
        </div>
      </div>
      <p className="rpg-scene-copy">{selectedSessionSummary.summary}</p>
      <div className="rpg-dialogue-stack" aria-label="Conversation">
        {isPreview ? (
          <>
            <article>
              <span className="rpg-avatar rpg-avatar-small">{heroSummary.avatar}</span>
              <div>
                <strong>{heroSummary.name} (You)</strong>
                <p>“I scan the current scene for useful details before committing to the next deterministic turn.”</p>
              </div>
            </article>
            <article>
              <span className="rpg-avatar rpg-avatar-small rpg-avatar-omnix">O</span>
              <div>
                <strong>Omnix (Narrator)</strong>
                <p>The preview session is ready for a replay-preserving command.</p>
              </div>
            </article>
          </>
        ) : storyMessages.length ? (
          storyMessages.slice(0, 10).map((message, index) => (
            <article key={`${message.speaker}:${message.text}:${index}`}>
              <span className={`rpg-avatar rpg-avatar-small${message.tone === 'narrator' ? ' rpg-avatar-omnix' : ''}`}>
                {message.avatar}
              </span>
              <div>
                <strong>{message.speaker}</strong>
                <p>{message.text}</p>
              </div>
            </article>
          ))
        ) : (
          recentEvents.slice(0, 2).map((event, index) => (
            <article key={`${event}:${index}`}>
              <span className="rpg-avatar rpg-avatar-small rpg-avatar-omnix">{index + 1}</span>
              <div>
                <strong>Live session event</strong>
                <p>{event}</p>
              </div>
            </article>
          ))
        )}
      </div>
      {children}
      <div className={`rpg-event-strip${recentEventsExpanded ? ' is-expanded' : ' is-collapsed'}`}>
        <button
          aria-controls="rpg-recent-events-list"
          aria-expanded={recentEventsExpanded}
          className="rpg-event-strip-summary"
          onClick={() => setRecentEventsExpanded((expanded) => !expanded)}
          title={recentEventsExpanded ? 'Collapse recent events' : 'Expand recent events'}
          type="button"
        >
          <strong>Recent events</strong>
          <span aria-hidden="true" className="rpg-event-strip-toggle" />
        </button>
        <ul id="rpg-recent-events-list">
          {recentEvents.map((event, index) => (
            <li key={`${event}:${index}`}>{event}</li>
          ))}
        </ul>
      </div>
    </section>
  );
}
