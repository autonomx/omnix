import { useState, type ReactNode } from 'react';
import { RpgLorePanel } from './RpgLorePanel';
import type { RpgNpcRelationshipPreview, RpgPartyMemberPreview, RpgWorldStateRowPreview } from './rpgUiTypes';
import './RpgWorldRail.css'; // the relationship and condition rows
import './RpgWorldPanel.css';

const RPG_PARTY_CAPACITY = 4;

type RpgWorldTab = 'here' | 'lore' | 'people' | 'conditions';

interface RpgWorldPanelProps {
  /** The map and who is here, on a screen too narrow to keep them beside the story. */
  here?: ReactNode;
  npcRelationships: RpgNpcRelationshipPreview[];
  onSelectCommand: (command: string) => void;
  partyMembers: RpgPartyMemberPreview[];
  worldStateRows: RpgWorldStateRowPreview[];
}

/** What the hero knows of the world beyond this scene: its lore, its people and how things stand. */
export function RpgWorldPanel({ here, npcRelationships, onSelectCommand, partyMembers, worldStateRows }: RpgWorldPanelProps) {
  const tabs: Array<{ id: RpgWorldTab; label: string }> = [
    ...(here ? [{ id: 'here' as const, label: 'Here' }] : []),
    { id: 'lore', label: 'Lore' },
    { id: 'people', label: 'People' },
    { id: 'conditions', label: 'Conditions' },
  ];
  const [activeTab, setActiveTab] = useState<RpgWorldTab>(here ? 'here' : 'lore');

  return (
    <div className="rpg-world-panel">
      <div className="rpg-tabs" role="tablist" aria-label="World">
        {tabs.map((tab) => (
          <button
            aria-controls={`rpg-world-${tab.id}-panel`}
            aria-selected={activeTab === tab.id}
            className={activeTab === tab.id ? 'active' : undefined}
            id={`rpg-world-${tab.id}-tab`}
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            role="tab"
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>
      {activeTab === 'here' && here ? (
        <div aria-labelledby="rpg-world-here-tab" id="rpg-world-here-panel" role="tabpanel">{here}</div>
      ) : null}
      {activeTab === 'lore' ? <RpgLorePanel labelledById="rpg-world-lore-tab" panelId="rpg-world-lore-panel" /> : null}
      {activeTab === 'people' ? (
        <div aria-labelledby="rpg-world-people-tab" className="rpg-world-people" id="rpg-world-people-panel" role="tabpanel">
          <section aria-label="Party members" className="rpg-world-panel-section">
            <div className="rpg-section-heading">
              <h3>Party</h3>
              <span>{partyMembers.length} / {RPG_PARTY_CAPACITY}</span>
            </div>
            <div className="rpg-list-stack">
              {partyMembers.map((member) => (
                <article className="rpg-list-row" key={member.name}>
                  <span className="rpg-icon-tile" aria-hidden="true">{member.avatar}</span>
                  <div>
                    <strong>{member.name}</strong>
                    <span>{member.role} · {member.hp}</span>
                  </div>
                </article>
              ))}
            </div>
            <button
              className="rpg-secondary-button"
              disabled={partyMembers.length >= RPG_PARTY_CAPACITY}
              onClick={() => onSelectCommand('Ask a trusted companion to join the party.')}
              type="button"
            >
              + Add companion
            </button>
          </section>
          <section aria-label="People you know" className="rpg-world-panel-section">
            <h3>People you know</h3>
            <div className="rpg-list-stack">
              {npcRelationships.length ? (
                npcRelationships.map((npc) => (
                  <article className="rpg-relationship-row" key={npc.name}>
                    <span className="rpg-avatar rpg-avatar-small" aria-hidden="true">{npc.name[0]}</span>
                    <strong>{npc.name}</strong>
                    <small>{npc.stance}</small>
                    <span className="rpg-party-health"><span style={{ width: `${npc.score}%` }} /></span>
                    <small>{npc.score}</small>
                  </article>
                ))
              ) : (
                <p className="rpg-empty-state">No one here knows you well yet.</p>
              )}
            </div>
          </section>
        </div>
      ) : null}
      {activeTab === 'conditions' ? (
        <div aria-labelledby="rpg-world-conditions-tab" className="rpg-world-state" id="rpg-world-conditions-panel" role="tabpanel">
          {worldStateRows.length ? worldStateRows.map((row) => (
            <div className="rpg-world-state-row" key={row.label}>
              <span aria-hidden="true">{row.icon}</span>
              <span>{row.label}</span>
              <strong>{row.value}</strong>
            </div>
          )) : <p className="rpg-empty-state">Nothing is known of the conditions here yet.</p>}
        </div>
      ) : null}
    </div>
  );
}
