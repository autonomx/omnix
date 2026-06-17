import type { ReactNode } from 'react';
import type { RpgHeroSummaryPreview, RpgSessionSummaryPreview } from './rpgUiState';
import './RpgVisualAssets.css';

const SCENE_ART_SRC = '/rpg/glimmerdeep-pass-scene.svg';

interface RpgStorySceneProps {
  children: ReactNode;
  heroSummary: RpgHeroSummaryPreview;
  recentEvents: string[];
  selectedSessionSummary: RpgSessionSummaryPreview;
}

export function RpgStoryScene({ children, heroSummary, recentEvents, selectedSessionSummary }: RpgStorySceneProps) {
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
        <div className="rpg-scene-art rpg-scene-art-has-image" aria-label={`${selectedSessionSummary.location} scene preview`}>
          <img src={SCENE_ART_SRC} alt="" aria-hidden="true" />
        </div>
      </div>
      <p className="rpg-scene-copy">{selectedSessionSummary.summary}</p>
      <div className="rpg-dialogue-stack">
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
            <p>
              The selected RPG session is ready. Queue a replay-preserving command to advance the simulation and update the
              scene from the authoritative turn result.
            </p>
          </div>
        </article>
      </div>
      <div className="rpg-event-strip">
        <strong>Recent events</strong>
        <ul>
          {recentEvents.map((event, index) => (
            <li key={`${event}:${index}`}>{event}</li>
          ))}
        </ul>
      </div>
      {children}
    </section>
  );
}
