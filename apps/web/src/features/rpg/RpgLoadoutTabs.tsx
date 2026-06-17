import { useState } from 'react';
import type { RpgLoadoutActionRequest } from '../../api/client';
import type { RpgHotbarAbilityPreview, RpgInventoryItemPreview } from './rpgUiState';
import './RpgLoadoutTabs.css';

type RpgLoadoutTab = 'inventory' | 'abilities' | 'hotbar';

interface RpgLoadoutTabsProps {
  inventoryItems: RpgInventoryItemPreview[];
  hotbarAbilities: RpgHotbarAbilityPreview[];
  isApplyingLoadoutAction?: boolean;
  onApplyLoadoutAction?: (request: RpgLoadoutActionRequest) => void;
  onSelectCommand: (command: string) => void;
  selectedSessionId?: string | null;
}

const tabs: Array<{ id: RpgLoadoutTab; label: string }> = [
  { id: 'inventory', label: 'Inventory' },
  { id: 'abilities', label: 'Abilities' },
  { id: 'hotbar', label: 'Hotbar' },
];

export function RpgLoadoutTabs({ inventoryItems, hotbarAbilities, isApplyingLoadoutAction = false, onApplyLoadoutAction, onSelectCommand, selectedSessionId }: RpgLoadoutTabsProps) {
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
          isApplyingLoadoutAction={isApplyingLoadoutAction}
          onApplyLoadoutAction={onApplyLoadoutAction}
          onSelectCommand={onSelectCommand}
          onSelectItem={setActiveInventoryIndex}
          selectedSessionId={selectedSessionId}
        />
      ) : null}
      {activeTab === 'abilities' ? (
        <AbilitiesPanel
          activeAbility={activeAbility}
          activeAbilityIndex={activeAbilityIndex}
          hotbarAbilities={hotbarAbilities}
          isApplyingLoadoutAction={isApplyingLoadoutAction}
          onApplyLoadoutAction={onApplyLoadoutAction}
          onSelectAbility={setActiveAbilityIndex}
          onSelectCommand={onSelectCommand}
          selectedSessionId={selectedSessionId}
        />
      ) : null}
      {activeTab === 'hotbar' ? (
        <HotbarPanel
          hotbarAbilities={hotbarAbilities}
          isApplyingLoadoutAction={isApplyingLoadoutAction}
          onApplyLoadoutAction={onApplyLoadoutAction}
          onSelectCommand={onSelectCommand}
          selectedSessionId={selectedSessionId}
        />
      ) : null}
    </section>
  );
}

interface InventoryPanelProps extends Pick<RpgLoadoutTabsProps, 'inventoryItems' | 'hotbarAbilities' | 'isApplyingLoadoutAction' | 'onApplyLoadoutAction' | 'onSelectCommand' | 'selectedSessionId'> {
  activeItem: RpgInventoryItemPreview | undefined;
  activeItemIndex: number;
  onSelectItem: (index: number) => void;
}

function InventoryPanel({ activeItem, activeItemIndex, inventoryItems, hotbarAbilities, isApplyingLoadoutAction, onApplyLoadoutAction, onSelectCommand, onSelectItem, selectedSessionId }: InventoryPanelProps) {
  const applyItemAction = (action: RpgLoadoutActionRequest['action'], command: string) => {
    if (selectedSessionId && activeItem && onApplyLoadoutAction) {
      onApplyLoadoutAction({ action, item_name: activeItem.label });
      return;
    }
    onSelectCommand(command);
  };

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
              disabled={isApplyingLoadoutAction}
              onClick={() =>
                selectedSessionId && onApplyLoadoutAction
                  ? onApplyLoadoutAction({ action: 'hotbar', hotbar_slot: ability.key })
                  : onSelectCommand(`Use ${ability.label} from hotbar slot ${ability.key} when it is tactically useful.`)
              }
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
        detail={
          activeItem
            ? `${activeItem.count} carried • ${selectedSessionId ? 'click an action to update the session' : 'select a session to apply actions'}`
            : 'Inventory actions appear when an item is indexed.'
        }
        actions={
          activeItem
            ? [
                { label: 'Inspect', command: `Inspect ${activeItem.label} and describe its useful properties.`, apply: () => applyItemAction('inspect', `Inspect ${activeItem.label} and describe its useful properties.`) },
                { label: 'Use', command: `Use ${activeItem.label} if it is helpful and legal in the current situation.`, apply: () => applyItemAction('use', `Use ${activeItem.label} if it is helpful and legal in the current situation.`) },
                { label: 'Equip', command: `Equip ${activeItem.label} if it improves my current loadout.`, apply: () => applyItemAction('equip', `Equip ${activeItem.label} if it improves my current loadout.`) },
                { label: 'Drop', command: `Drop one ${activeItem.label} only if it is safe to discard.`, apply: () => applyItemAction('drop', `Drop one ${activeItem.label} only if it is safe to discard.`) },
              ]
            : []
        }
        disabled={isApplyingLoadoutAction}
        onSelectCommand={onSelectCommand}
      />
    </div>
  );
}

interface AbilitiesPanelProps extends Pick<RpgLoadoutTabsProps, 'hotbarAbilities' | 'isApplyingLoadoutAction' | 'onApplyLoadoutAction' | 'onSelectCommand' | 'selectedSessionId'> {
  activeAbility: RpgHotbarAbilityPreview | undefined;
  activeAbilityIndex: number;
  onSelectAbility: (index: number) => void;
}

function AbilitiesPanel({ activeAbility, activeAbilityIndex, hotbarAbilities, isApplyingLoadoutAction, onApplyLoadoutAction, onSelectAbility, onSelectCommand, selectedSessionId }: AbilitiesPanelProps) {
  const applyAbilityAction = (command: string, target?: string) => {
    if (selectedSessionId && activeAbility && onApplyLoadoutAction) {
      onApplyLoadoutAction({ action: 'use_ability', ability_name: activeAbility.label, target });
      return;
    }
    onSelectCommand(command);
  };

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
            ? `Slot ${activeAbility.key} • ${selectedSessionId ? 'uses stamina/mana and writes a deterministic event' : 'select a session to apply ability effects'}.`
            : 'Ability commands appear when an ability is indexed.'
        }
        actions={
          activeAbility
            ? [
                { label: 'Use', command: `Use ${activeAbility.label} on the most relevant target.`, apply: () => applyAbilityAction(`Use ${activeAbility.label} on the most relevant target.`, 'the most relevant target') },
                { label: 'Target enemy', command: `Use ${activeAbility.label} on the most dangerous visible enemy.`, apply: () => applyAbilityAction(`Use ${activeAbility.label} on the most dangerous visible enemy.`, 'the most dangerous visible enemy') },
                { label: 'Support ally', command: `Use ${activeAbility.label} to support the ally who needs it most.`, apply: () => applyAbilityAction(`Use ${activeAbility.label} to support the ally who needs it most.`, 'the ally who needs it most') },
                { label: 'Describe', command: `Inspect ${activeAbility.label} and explain when I should use it.`, apply: () => onSelectCommand(`Inspect ${activeAbility.label} and explain when I should use it.`) },
              ]
            : []
        }
        disabled={isApplyingLoadoutAction}
        onSelectCommand={onSelectCommand}
      />
    </div>
  );
}

function HotbarPanel({ hotbarAbilities, isApplyingLoadoutAction, onApplyLoadoutAction, onSelectCommand, selectedSessionId }: Pick<RpgLoadoutTabsProps, 'hotbarAbilities' | 'isApplyingLoadoutAction' | 'onApplyLoadoutAction' | 'onSelectCommand' | 'selectedSessionId'>) {
  return (
    <div aria-labelledby="rpg-hotbar-loadout-tab" className="rpg-list-stack" id="rpg-hotbar-loadout-panel" role="tabpanel">
      <div className="rpg-hotbar rpg-hotbar-command-grid" aria-label="Active ability hotbar">
        {hotbarAbilities.map((ability) => (
          <button
            type="button"
            key={ability.key}
            aria-label={`${ability.key}: ${ability.label}`}
            disabled={isApplyingLoadoutAction}
            onClick={() =>
              selectedSessionId && onApplyLoadoutAction
                ? onApplyLoadoutAction({ action: 'hotbar', hotbar_slot: ability.key })
                : onSelectCommand(`Use ${ability.label} from hotbar slot ${ability.key} on the best available target.`)
            }
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
          <span>{selectedSessionId ? 'Selecting a slot applies the ability to the selected session immediately.' : 'Select a session to apply hotbar effects directly.'}</span>
        </div>
      </article>
    </div>
  );
}

interface LoadoutDetailAction {
  label: string;
  command: string;
  apply?: () => void;
}

interface LoadoutDetailCardProps {
  eyebrow: string;
  title: string;
  detail: string;
  actions: LoadoutDetailAction[];
  disabled?: boolean;
  onSelectCommand: (command: string) => void;
}

function LoadoutDetailCard({ actions, detail, disabled, eyebrow, onSelectCommand, title }: LoadoutDetailCardProps) {
  return (
    <aside className="rpg-loadout-detail" aria-label={`${eyebrow}: ${title}`}>
      <p className="eyebrow">{eyebrow}</p>
      <strong>{title}</strong>
      <span>{detail}</span>
      <div className="rpg-loadout-actions" aria-label={`${title} actions`}>
        {actions.map((action) => (
          <button className="rpg-mini-button" disabled={disabled} key={action.label} onClick={() => (action.apply ? action.apply() : onSelectCommand(action.command))} type="button">
            {action.label}
          </button>
        ))}
      </div>
    </aside>
  );
}
