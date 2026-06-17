import { useState } from 'react';
import type { RpgHotbarAbilityPreview, RpgInventoryItemPreview } from './rpgUiState';
import './RpgLoadoutTabs.css';

type RpgLoadoutTab = 'inventory' | 'abilities' | 'hotbar';

interface RpgLoadoutTabsProps {
  inventoryItems: RpgInventoryItemPreview[];
  hotbarAbilities: RpgHotbarAbilityPreview[];
  onSelectCommand: (command: string) => void;
}

const tabs: Array<{ id: RpgLoadoutTab; label: string }> = [
  { id: 'inventory', label: 'Inventory' },
  { id: 'abilities', label: 'Abilities' },
  { id: 'hotbar', label: 'Hotbar' },
];

export function RpgLoadoutTabs({ inventoryItems, hotbarAbilities, onSelectCommand }: RpgLoadoutTabsProps) {
  const [activeTab, setActiveTab] = useState<RpgLoadoutTab>('inventory');
  const [activeInventoryIndex, setActiveInventoryIndex] = useState(0);
  const [activeAbilityIndex, setActiveAbilityIndex] = useState(0);
  const activeItem = inventoryItems[Math.min(activeInventoryIndex, Math.max(inventoryItems.length - 1, 0))];
  const activeAbility = hotbarAbilities[Math.min(activeAbilityIndex, Math.max(hotbarAbilities.length - 1, 0))];

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
      {activeTab === 'inventory' ? (
        <InventoryPanel
          activeItem={activeItem}
          activeItemIndex={activeInventoryIndex}
          hotbarAbilities={hotbarAbilities}
          inventoryItems={inventoryItems}
          onSelectCommand={onSelectCommand}
          onSelectItem={setActiveInventoryIndex}
        />
      ) : null}
      {activeTab === 'abilities' ? (
        <AbilitiesPanel
          activeAbility={activeAbility}
          activeAbilityIndex={activeAbilityIndex}
          hotbarAbilities={hotbarAbilities}
          onSelectAbility={setActiveAbilityIndex}
          onSelectCommand={onSelectCommand}
        />
      ) : null}
      {activeTab === 'hotbar' ? <HotbarPanel hotbarAbilities={hotbarAbilities} onSelectCommand={onSelectCommand} /> : null}
    </section>
  );
}

interface InventoryPanelProps extends Pick<RpgLoadoutTabsProps, 'inventoryItems' | 'hotbarAbilities' | 'onSelectCommand'> {
  activeItem: RpgInventoryItemPreview | undefined;
  activeItemIndex: number;
  onSelectItem: (index: number) => void;
}

function InventoryPanel({ activeItem, activeItemIndex, inventoryItems, hotbarAbilities, onSelectCommand, onSelectItem }: InventoryPanelProps) {
  return (
    <div aria-labelledby="rpg-inventory-loadout-tab" className="rpg-loadout-layout" id="rpg-inventory-loadout-panel" role="tabpanel">
      <div className="rpg-inventory-grid" aria-label="Inventory item slots">
        {inventoryItems.map((item, index) => (
          <button
            aria-label={item.label}
            aria-pressed={activeItemIndex === index}
            className="rpg-item-slot"
            key={item.label}
            onClick={() => onSelectItem(index)}
            type="button"
          >
            <span aria-hidden="true">{item.icon}</span>
            <small>{item.count}</small>
          </button>
        ))}
        <button className="rpg-item-slot rpg-empty-slot" type="button" aria-label="Empty inventory slot">
          +
        </button>
        <div className="rpg-hotbar" aria-label="Ability hotbar preview">
          {hotbarAbilities.map((ability) => (
            <button
              type="button"
              key={ability.key}
              aria-label={ability.label}
              onClick={() => onSelectCommand(`Use ${ability.label} from hotbar slot ${ability.key} when it is tactically useful.`)}
            >
              <small>{ability.key}</small>
              <span>{ability.icon}</span>
            </button>
          ))}
        </div>
      </div>

      <LoadoutDetailCard
        eyebrow="Selected item"
        title={activeItem?.label ?? 'No item selected'}
        detail={activeItem ? `${activeItem.count} carried • command-safe inventory affordances` : 'Inventory actions appear when an item is indexed.'}
        actions={
          activeItem
            ? [
                { label: 'Inspect', command: `Inspect ${activeItem.label} and describe its useful properties.` },
                { label: 'Use', command: `Use ${activeItem.label} if it is helpful and legal in the current situation.` },
                { label: 'Equip', command: `Equip ${activeItem.label} if it improves my current loadout.` },
                { label: 'Drop', command: `Drop one ${activeItem.label} only if it is safe to discard.` },
              ]
            : []
        }
        onSelectCommand={onSelectCommand}
      />
    </div>
  );
}

interface AbilitiesPanelProps extends Pick<RpgLoadoutTabsProps, 'hotbarAbilities' | 'onSelectCommand'> {
  activeAbility: RpgHotbarAbilityPreview | undefined;
  activeAbilityIndex: number;
  onSelectAbility: (index: number) => void;
}

function AbilitiesPanel({ activeAbility, activeAbilityIndex, hotbarAbilities, onSelectAbility, onSelectCommand }: AbilitiesPanelProps) {
  return (
    <div aria-labelledby="rpg-abilities-loadout-tab" className="rpg-loadout-layout" id="rpg-abilities-loadout-panel" role="tabpanel">
      <div className="rpg-list-stack">
        {hotbarAbilities.map((ability, index) => (
          <button
            aria-pressed={activeAbilityIndex === index}
            className="rpg-loadout-row-button"
            key={ability.label}
            onClick={() => onSelectAbility(index)}
            type="button"
          >
            <span className="rpg-icon-tile" aria-hidden="true">
              {ability.icon}
            </span>
            <div>
              <strong>{ability.label}</strong>
              <span>Assignable action slot {ability.key}</span>
            </div>
          </button>
        ))}
      </div>

      <LoadoutDetailCard
        eyebrow="Selected ability"
        title={activeAbility?.label ?? 'No ability selected'}
        detail={
          activeAbility
            ? `Slot ${activeAbility.key} • target and use commands stay replay-preserving until submitted.`
            : 'Ability commands appear when an ability is indexed.'
        }
        actions={
          activeAbility
            ? [
                { label: 'Use', command: `Use ${activeAbility.label} on the most relevant target.` },
                { label: 'Target enemy', command: `Use ${activeAbility.label} on the most dangerous visible enemy.` },
                { label: 'Support ally', command: `Use ${activeAbility.label} to support the ally who needs it most.` },
                { label: 'Describe', command: `Inspect ${activeAbility.label} and explain when I should use it.` },
              ]
            : []
        }
        onSelectCommand={onSelectCommand}
      />
    </div>
  );
}

function HotbarPanel({ hotbarAbilities, onSelectCommand }: Pick<RpgLoadoutTabsProps, 'hotbarAbilities' | 'onSelectCommand'>) {
  return (
    <div aria-labelledby="rpg-hotbar-loadout-tab" className="rpg-list-stack" id="rpg-hotbar-loadout-panel" role="tabpanel">
      <div className="rpg-hotbar rpg-hotbar-command-grid" aria-label="Active ability hotbar">
        {hotbarAbilities.map((ability) => (
          <button
            type="button"
            key={ability.key}
            aria-label={`${ability.key}: ${ability.label}`}
            onClick={() => onSelectCommand(`Use ${ability.label} from hotbar slot ${ability.key} on the best available target.`)}
          >
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
          <strong>Command-ready hotbar</strong>
          <span>Selecting a slot drafts a replay-preserving RPG command before you queue the turn.</span>
        </div>
      </article>
    </div>
  );
}

interface LoadoutDetailAction {
  label: string;
  command: string;
}

interface LoadoutDetailCardProps {
  eyebrow: string;
  title: string;
  detail: string;
  actions: LoadoutDetailAction[];
  onSelectCommand: (command: string) => void;
}

function LoadoutDetailCard({ actions, detail, eyebrow, onSelectCommand, title }: LoadoutDetailCardProps) {
  return (
    <aside className="rpg-loadout-detail" aria-label={`${eyebrow}: ${title}`}>
      <p className="eyebrow">{eyebrow}</p>
      <strong>{title}</strong>
      <span>{detail}</span>
      <div className="rpg-loadout-actions" aria-label={`${title} actions`}>
        {actions.map((action) => (
          <button className="rpg-mini-button" key={action.label} onClick={() => onSelectCommand(action.command)} type="button">
            {action.label}
          </button>
        ))}
      </div>
    </aside>
  );
}
