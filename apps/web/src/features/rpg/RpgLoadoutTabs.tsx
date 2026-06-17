import { useState } from 'react';
import type { RpgHotbarAbilityPreview, RpgInventoryItemPreview } from './rpgUiState';

type RpgLoadoutTab = 'inventory' | 'abilities' | 'hotbar';

interface RpgLoadoutTabsProps {
  inventoryItems: RpgInventoryItemPreview[];
  hotbarAbilities: RpgHotbarAbilityPreview[];
}

const tabs: Array<{ id: RpgLoadoutTab; label: string }> = [
  { id: 'inventory', label: 'Inventory' },
  { id: 'abilities', label: 'Abilities' },
  { id: 'hotbar', label: 'Hotbar' },
];

export function RpgLoadoutTabs({ inventoryItems, hotbarAbilities }: RpgLoadoutTabsProps) {
  const [activeTab, setActiveTab] = useState<RpgLoadoutTab>('inventory');

  return (
    <section className="rpg-card rpg-inventory-card">
      <div className="rpg-tabs" role="tablist" aria-label="Inventory tabs">
        {tabs.map((tab) => (
          <button
            aria-controls={`rpg-${tab.id}-loadout-panel`}
            aria-selected={activeTab === tab.id}
            className={activeTab === tab.id ? 'active' : undefined}
            id={`rpg-${tab.id}-loadout-tab`}
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            role="tab"
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>
      {activeTab === 'inventory' ? <InventoryPanel hotbarAbilities={hotbarAbilities} inventoryItems={inventoryItems} /> : null}
      {activeTab === 'abilities' ? <AbilitiesPanel hotbarAbilities={hotbarAbilities} /> : null}
      {activeTab === 'hotbar' ? <HotbarPanel hotbarAbilities={hotbarAbilities} /> : null}
    </section>
  );
}

function InventoryPanel({ inventoryItems, hotbarAbilities }: RpgLoadoutTabsProps) {
  return (
    <div aria-labelledby="rpg-inventory-loadout-tab" className="rpg-inventory-grid" id="rpg-inventory-loadout-panel" role="tabpanel">
      {inventoryItems.map((item) => (
        <button className="rpg-item-slot" key={item.label} type="button" aria-label={item.label}>
          <span aria-hidden="true">{item.icon}</span>
          <small>{item.count}</small>
        </button>
      ))}
      <button className="rpg-item-slot rpg-empty-slot" type="button" aria-label="Empty inventory slot">
        +
      </button>
      <div className="rpg-hotbar" aria-label="Ability hotbar preview">
        {hotbarAbilities.map((ability) => (
          <button type="button" key={ability.key} aria-label={ability.label}>
            <small>{ability.key}</small>
            <span>{ability.icon}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function AbilitiesPanel({ hotbarAbilities }: Pick<RpgLoadoutTabsProps, 'hotbarAbilities'>) {
  return (
    <div aria-labelledby="rpg-abilities-loadout-tab" className="rpg-list-stack" id="rpg-abilities-loadout-panel" role="tabpanel">
      {hotbarAbilities.map((ability) => (
        <article className="rpg-list-row" key={ability.label}>
          <span className="rpg-icon-tile" aria-hidden="true">
            {ability.icon}
          </span>
          <div>
            <strong>{ability.label}</strong>
            <span>Assignable action slot {ability.key}</span>
          </div>
        </article>
      ))}
    </div>
  );
}

function HotbarPanel({ hotbarAbilities }: Pick<RpgLoadoutTabsProps, 'hotbarAbilities'>) {
  return (
    <div aria-labelledby="rpg-hotbar-loadout-tab" className="rpg-list-stack" id="rpg-hotbar-loadout-panel" role="tabpanel">
      <div className="rpg-hotbar" aria-label="Active ability hotbar">
        {hotbarAbilities.map((ability) => (
          <button type="button" key={ability.key} aria-label={`${ability.key}: ${ability.label}`}>
            <small>{ability.key}</small>
            <span>{ability.icon}</span>
          </button>
        ))}
      </div>
      <article className="rpg-list-row">
        <span className="rpg-icon-tile" aria-hidden="true">
          ⇥
        </span>
        <div>
          <strong>Keyboard-ready hotbar</strong>
          <span>Slots stay visible while the player writes a replay-preserving command.</span>
        </div>
      </article>
    </div>
  );
}
