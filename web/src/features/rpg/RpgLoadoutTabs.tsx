import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { rpgSessionClient, type RpgLoadoutActionRequest } from './api/rpgSessionClient';
import { buildSelectedItemActions, type RpgItemUiAction } from './rpgItemUiState';
import type { RpgHotbarAbilityPreview, RpgInventoryItemPreview } from './rpgUiTypes';
import './RpgLoadoutTabs.css';
import { AbilitiesPanel, CoveragePanel, EffectsPanel, HotbarPanel, InventoryPanel, SkillsPanel, TraitsPanel } from './RpgLoadoutPanels';
import { buildAbilityOverview } from './rpgAbilityOverview';

type RpgLoadoutTab = 'inventory' | 'abilities' | 'hotbar' | 'skills' | 'traits' | 'effects' | 'coverage';

/** The tabs about the character's ability tree, which show its summary above them. */
const ABILITY_TABS: ReadonlySet<RpgLoadoutTab> = new Set(['abilities', 'skills', 'traits', 'coverage']);

export interface RpgLoadoutTabsProps {
  inventoryItems: RpgInventoryItemPreview[];
  hotbarAbilities: RpgHotbarAbilityPreview[];
  isApplyingLoadoutAction?: boolean;
  onApplyLoadoutAction?: (request: RpgLoadoutActionRequest) => void;
  onSelectCommand: (command: string) => void;
  /** Sends a typed turn, as the composer would (selling from the pack). */
  onSubmitCommand?: (command: string) => void;
  selectedSessionId?: string | null;
}

const tabs: Array<{ id: RpgLoadoutTab; label: string }> = [
  { id: 'inventory', label: 'Inventory' },
  { id: 'abilities', label: 'Abilities' },
  { id: 'hotbar', label: 'Hotbar' },
  { id: 'skills', label: 'Skills' },
  { id: 'traits', label: 'Traits' },
  { id: 'effects', label: 'Effects' },
  { id: 'coverage', label: 'Coverage' },
];

export function RpgLoadoutTabs({ inventoryItems, hotbarAbilities, isApplyingLoadoutAction = false, onApplyLoadoutAction, onSelectCommand, onSubmitCommand, selectedSessionId }: RpgLoadoutTabsProps) {
  const [activeTab, setActiveTab] = useState<RpgLoadoutTab>('inventory');
  const [activeInventoryIndex, setActiveInventoryIndex] = useState(0);
  const [activeAbilityIndex, setActiveAbilityIndex] = useState(0);
  const [activeHotbarSlot, setActiveHotbarSlot] = useState('1');
  const wasApplyingAction = useRef(false);

  const sessionQuery = useQuery({
    enabled: Boolean(selectedSessionId),
    queryKey: ['feature', 'rpg', 'ability-tree-session', selectedSessionId],
    queryFn: () => rpgSessionClient.getRpgSession(selectedSessionId ?? ''),
    staleTime: 0,
  });
  const abilityOverview = useMemo(
    () => buildAbilityOverview(sessionQuery.data, hotbarAbilities, Boolean(selectedSessionId)),
    [hotbarAbilities, selectedSessionId, sessionQuery.data],
  );
  const displayedHotbarAbilities = abilityOverview.hotbarAbilities.length ? abilityOverview.hotbarAbilities : hotbarAbilities;
  const activeItem = inventoryItems[Math.min(activeInventoryIndex, Math.max(inventoryItems.length - 1, 0))];
  const activeAbility = abilityOverview.allAbilities[Math.min(activeAbilityIndex, Math.max(abilityOverview.allAbilities.length - 1, 0))];
  const coveragePercent = Math.round(abilityOverview.coverage.score * 100);

  const panelDisabled = isApplyingLoadoutAction || sessionQuery.isFetching;
  // Each pack action is a turn: the loadout's (use, equip, take off, drop), or a typed one (sell).
  const applyItemAction = (action: RpgItemUiAction) => {
    if (!selectedSessionId) return;
    if (action.mode === 'turn') {
      onSubmitCommand?.(action.command);
      return;
    }
    onApplyLoadoutAction?.(action.payload as unknown as RpgLoadoutActionRequest);
  };

  useEffect(() => {
    if (wasApplyingAction.current && !isApplyingLoadoutAction && selectedSessionId) {
      void sessionQuery.refetch();
    }
    wasApplyingAction.current = isApplyingLoadoutAction;
  }, [isApplyingLoadoutAction, selectedSessionId, sessionQuery]);

  return (
    <section className="rpg-card rpg-inventory-card">
      <div className="rpg-tabs" role="tablist" aria-label="Inventory and ability tabs">
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

      {ABILITY_TABS.has(activeTab) ? (
        <div role="group" className="rpg-ability-summary" aria-label="Ability tree summary" title={abilityOverview.treeId}>
          <strong>{abilityOverview.source === 'live' ? abilityOverview.className : 'Sample loadout'}</strong>
          <span>
            {abilityOverview.source === 'live'
              ? `Level ${abilityOverview.playerLevel} • ${abilityOverview.levelChoices} level's choice${abilityOverview.levelChoices === 1 ? '' : 's'} waiting • ${coveragePercent}% dimension coverage`
              : 'Start or load a campaign to see your character’s own abilities.'}
          </span>
        </div>
      ) : null}

      {activeTab === 'inventory' ? (
        <InventoryPanel
          activeItemIndex={activeInventoryIndex}
          hotbarAbilities={displayedHotbarAbilities}
          inventoryItems={inventoryItems}
          isApplyingLoadoutAction={isApplyingLoadoutAction}
          itemActions={buildSelectedItemActions({ item: activeItem, selectedSessionId })}
          onApplyItemAction={applyItemAction}
          onApplyLoadoutAction={onApplyLoadoutAction}
          onSelectCommand={onSelectCommand}
          onSelectItem={setActiveInventoryIndex}
          selectedSessionId={selectedSessionId}
        />
      ) : null}
      {activeTab === 'abilities' ? (
        <AbilitiesPanel
          abilityOverview={abilityOverview}
          activeAbility={activeAbility}
          activeAbilityIndex={activeAbilityIndex}
          isApplyingLoadoutAction={panelDisabled}
          onApplyLoadoutAction={onApplyLoadoutAction}
          onSelectAbility={setActiveAbilityIndex}
          onSelectCommand={onSelectCommand}
          selectedSessionId={selectedSessionId}
        />
      ) : null}
      {activeTab === 'hotbar' ? (
        <HotbarPanel
          abilityOverview={abilityOverview}
          activeHotbarSlot={activeHotbarSlot}
          isApplyingLoadoutAction={panelDisabled}
          onApplyLoadoutAction={onApplyLoadoutAction}
          onSelectCommand={onSelectCommand}
          onSelectSlot={setActiveHotbarSlot}
          selectedSessionId={selectedSessionId}
        />
      ) : null}
      {activeTab === 'skills' ? <SkillsPanel disabled={panelDisabled} onSelectCommand={onSelectCommand} skills={abilityOverview.skills} /> : null}
      {activeTab === 'traits' ? <TraitsPanel disabled={panelDisabled} onSelectCommand={onSelectCommand} traits={abilityOverview.traits} /> : null}
      {activeTab === 'effects' ? <EffectsPanel disabled={panelDisabled} effects={abilityOverview.activeEffects} onSelectCommand={onSelectCommand} /> : null}
      {activeTab === 'coverage' ? <CoveragePanel coverage={abilityOverview.coverage} disabled={panelDisabled} onRefreshCoverage={() => void sessionQuery.refetch()} onSelectCommand={onSelectCommand} /> : null}
    </section>
  );
}
