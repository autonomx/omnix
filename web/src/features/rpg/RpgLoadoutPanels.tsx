import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { RpgLoadoutActionRequest } from './api/rpgSessionClient';
import { fetchRpgAbilityDetails } from './rpgItemApi';
import { RpgItemPanel } from './RpgItemPanel';
import type { RpgItemUiAction } from './rpgItemUiState';
import type { RpgHotbarAbilityPreview } from './rpgUiTypes';
import type { RpgLoadoutTabsProps } from './RpgLoadoutTabs';
import { REQUIRED_DIMENSIONS, abilityDetail, firstNumber, firstString, formatAbilityCost, nextAssignableHotbarSlot, recordValue, titleCase } from './rpgAbilityOverview';
import type { AbilityCoveragePreview, AbilityOverview, AbilityPreview, EffectPreview, SkillProgressionPreview } from './rpgAbilityOverview';
import './RpgLoadoutPanels.css';

interface LoadoutDetailAction {
  label: string;
  command: string;
  apply?: () => void;
}

interface InventoryPanelProps extends Pick<RpgLoadoutTabsProps, 'inventoryItems' | 'isApplyingLoadoutAction' | 'onApplyLoadoutAction' | 'onSelectCommand' | 'selectedSessionId'> {
  activeItemIndex: number;
  hotbarAbilities: RpgHotbarAbilityPreview[];
  itemActions: RpgItemUiAction[];
  onApplyItemAction: (action: RpgItemUiAction) => void;
  onSelectItem: (index: number) => void;
}

export function InventoryPanel({
  activeItemIndex,
  inventoryItems,
  hotbarAbilities,
  isApplyingLoadoutAction,
  itemActions,
  onApplyItemAction,
  onApplyLoadoutAction,
  onSelectCommand,
  onSelectItem,
  selectedSessionId,
}: InventoryPanelProps) {
  return (
    <div aria-labelledby="rpg-inventory-loadout-tab" className="rpg-loadout-layout rpg-item-loadout-layout" id="rpg-inventory-loadout-panel" role="tabpanel">
      <div className="rpg-inventory-column">
        <div role="group" className="rpg-inventory-grid" aria-label="Inventory item slots">
          {inventoryItems.map((item, index) => (
            <button
              aria-label={item.label}
              aria-pressed={activeItemIndex === index}
              className="rpg-item-slot"
              key={`${item.label}-${index}`}
              onClick={() => onSelectItem(index)}
              type="button"
            >
              <span className="rpg-item-slot-icon" aria-hidden="true">{item.icon}</span>
              <span className="rpg-item-slot-name" aria-hidden="true">{item.label}</span>
              <small aria-hidden="true">×{item.count}</small>
            </button>
          ))}
        </div>
        <button
          className="rpg-secondary-button rpg-inventory-search"
          disabled={isApplyingLoadoutAction}
          onClick={() => onSelectCommand('Search the area for useful supplies I can pick up and add to my inventory.')}
          title="Search for useful supplies through the next RPG turn."
          type="button"
          aria-label="Search for inventory supplies"
        >
          + Search for supplies
        </button>
        <section className="rpg-quick-slots" aria-label="Quick slots">
          <h4>Quick slots</h4>
          <div role="group" className="rpg-hotbar" aria-label="Ability hotbar">
            {hotbarAbilities.map((ability) => (
              <InventoryHotbarAbilityButton
                ability={ability}
                disabled={Boolean(isApplyingLoadoutAction)}
                key={ability.key}
                onActivate={() =>
                  selectedSessionId && onApplyLoadoutAction
                    ? onApplyLoadoutAction({ action: 'hotbar', hotbar_slot: ability.key })
                    : onSelectCommand(`Use ${ability.label} from hotbar slot ${ability.key} when it is tactically useful.`)
                }
                selectedSessionId={selectedSessionId}
              />
            ))}
          </div>
        </section>
      </div>

      <RpgItemPanel
        actions={itemActions}
        isPending={isApplyingLoadoutAction}
        item={inventoryItems[Math.min(activeItemIndex, Math.max(inventoryItems.length - 1, 0))]}
        onApplyAction={onApplyItemAction}
      />
    </div>
  );
}

function InventoryHotbarAbilityButton({
  ability,
  disabled,
  onActivate,
  selectedSessionId,
}: {
  ability: RpgHotbarAbilityPreview;
  disabled: boolean;
  onActivate: () => void;
  selectedSessionId?: string | null;
}) {
  const [detailRequested, setDetailRequested] = useState(false);
  const tooltipId = `rpg-hotbar-tooltip-${ability.key}`;
  const detailQuery = useQuery({
    enabled: Boolean(selectedSessionId && detailRequested),
    queryKey: ['feature', 'rpg', 'ability-detail-v1', selectedSessionId, ability.abilityId ?? ability.label],
    queryFn: () =>
      fetchRpgAbilityDetails(selectedSessionId ?? '', {
        abilityName: ability.label,
        abilityId: ability.abilityId,
      }),
    retry: false,
    staleTime: 5 * 60_000,
  });
  const detail = recordValue(detailQuery.data?.ability_detail);
  const description = firstString(detail?.summary, ability.description) ?? 'No ability description is available.';
  const cost = formatAbilityCost(recordValue(detail?.resource_cost));
  const cooldown = firstNumber(detail?.cooldown_turns);
  const isLoading = Boolean(selectedSessionId && detailRequested && detailQuery.isFetching);

  return (
    <button
      aria-describedby={tooltipId}
      aria-label={ability.label}
      disabled={disabled}
      onClick={onActivate}
      onFocus={() => setDetailRequested(true)}
      onMouseEnter={() => setDetailRequested(true)}
      type="button"
    >
      <small>{ability.key}</small>
      <span>{ability.icon}</span>
      <div className="rpg-hotbar-ability-tooltip" id={tooltipId} role="tooltip">
        <strong>{ability.label}</strong>
        <p>{isLoading ? 'Generating an ability description with the configured LLM.' : description}</p>
        {cost || cooldown !== undefined ? (
          <div className="rpg-hotbar-ability-meta">
            {cost ? <span>{cost}</span> : null}
            {cooldown !== undefined ? <span>{cooldown > 0 ? `${cooldown}-turn cooldown` : 'No cooldown'}</span> : null}
          </div>
        ) : null}
      </div>
    </button>
  );
}

interface AbilitiesPanelProps extends Pick<RpgLoadoutTabsProps, 'isApplyingLoadoutAction' | 'onApplyLoadoutAction' | 'onSelectCommand' | 'selectedSessionId'> {
  abilityOverview: AbilityOverview;
  activeAbility: AbilityPreview | undefined;
  activeAbilityIndex: number;
  onSelectAbility: (index: number) => void;
}

export function AbilitiesPanel({ abilityOverview, activeAbility, activeAbilityIndex, isApplyingLoadoutAction, onApplyLoadoutAction, onSelectAbility, onSelectCommand, selectedSessionId }: AbilitiesPanelProps) {
  const nextSlot = nextAssignableHotbarSlot(abilityOverview.hotbarSlots, activeAbility?.id);
  const applyAbilityAction = (request: Record<string, unknown>, fallbackCommand: string) => {
    if (selectedSessionId && onApplyLoadoutAction) {
      onApplyLoadoutAction(request as unknown as RpgLoadoutActionRequest);
      return;
    }
    onSelectCommand(fallbackCommand);
  };
  const actions: LoadoutDetailAction[] = activeAbility
    ? [
        { label: 'Inspect', command: `Inspect ${activeAbility.name} and explain when I should use it.`, apply: () => onSelectCommand(`Inspect ${activeAbility.name} and explain when I should use it.`) },
        ...(activeAbility.kind === 'active' && activeAbility.isUnlocked
          ? [
              { label: 'Use', command: `Use ${activeAbility.name} on the most relevant target.`, apply: () => applyAbilityAction({ action: 'use_ability', ability_id: activeAbility.id, ability_name: activeAbility.name, target: 'the most relevant target' }, `Use ${activeAbility.name} on the most relevant target.`) },
              { label: `Assign ${nextSlot}`, command: `Assign ${activeAbility.name} to hotbar slot ${nextSlot}.`, apply: () => applyAbilityAction({ action: 'assign_hotbar', ability_id: activeAbility.id, hotbar_slot: nextSlot }, `Assign ${activeAbility.name} to hotbar slot ${nextSlot}.`) },
            ]
          : []),
        ...(!activeAbility.isUnlocked && activeAbility.isAvailable
          ? [{ label: 'Learn', command: `Learn ${activeAbility.name}.`, apply: () => applyAbilityAction({ action: 'unlock_ability', ability_id: activeAbility.id, ability_name: activeAbility.name }, `Learn ${activeAbility.name}.`) }]
          : []),
      ]
    : [];

  return (
    <div aria-labelledby="rpg-abilities-loadout-tab" className="rpg-loadout-layout rpg-ability-tree-layout" id="rpg-abilities-loadout-panel" role="tabpanel">
      <div role="group" className="rpg-ability-tree" aria-label="Ability tree categories">
        {abilityOverview.categories.map((category) => (
          <section className="rpg-ability-category" key={category.id}>
            <header>
              <strong>{category.name}</strong>
              <span>{titleCase(category.capability)} • {category.dimensions.map(titleCase).join(', ')}</span>
            </header>
            <div className="rpg-ability-node-list">
              {category.abilities.map((ability) => {
                const index = abilityOverview.allAbilities.findIndex((candidate) => candidate.id === ability.id);
                return (
                  <button
                    aria-pressed={activeAbilityIndex === index}
                    className={`rpg-ability-node rpg-ability-node-${ability.status}`}
                    key={ability.id}
                    onClick={() => onSelectAbility(Math.max(0, index))}
                    type="button"
                  >
                    <span className="rpg-icon-tile" aria-hidden="true">{ability.icon}</span>
                    <div>
                      <strong>{ability.name}</strong>
                      <span>{ability.statusLabel}</span>
                      <small>{titleCase(ability.kind)} • {titleCase(ability.purpose)}</small>
                    </div>
                  </button>
                );
              })}
            </div>
          </section>
        ))}
      </div>

      <LoadoutDetailCard
        eyebrow={activeAbility ? `${titleCase(activeAbility.kind)} ability` : 'Selected ability'}
        title={activeAbility?.name ?? 'No ability selected'}
        detail={activeAbility ? abilityDetail(activeAbility) : 'Select a tree node to inspect, learn, assign, or use it.'}
        actions={actions}
        disabled={isApplyingLoadoutAction}
        onSelectCommand={onSelectCommand}
      />
    </div>
  );
}

interface HotbarPanelProps extends Pick<RpgLoadoutTabsProps, 'isApplyingLoadoutAction' | 'onApplyLoadoutAction' | 'onSelectCommand' | 'selectedSessionId'> {
  abilityOverview: AbilityOverview;
  activeHotbarSlot: string;
  onSelectSlot: (slot: string) => void;
}

export function HotbarPanel({ abilityOverview, activeHotbarSlot, isApplyingLoadoutAction, onApplyLoadoutAction, onSelectCommand, onSelectSlot, selectedSessionId }: HotbarPanelProps) {
  const selectedSlot = abilityOverview.hotbarSlots.find((slot) => slot.slot === activeHotbarSlot);
  const selectedAbility = selectedSlot?.ability;
  const applyHotbarAction = (request: Record<string, unknown>, fallbackCommand: string) => {
    if (selectedSessionId && onApplyLoadoutAction) {
      onApplyLoadoutAction(request as unknown as RpgLoadoutActionRequest);
      return;
    }
    onSelectCommand(fallbackCommand);
  };

  return (
    <div aria-labelledby="rpg-hotbar-loadout-tab" className="rpg-loadout-layout" id="rpg-hotbar-loadout-panel" role="tabpanel">
      <div role="group" className="rpg-hotbar-slot-list" aria-label="Active ability hotbar">
        {abilityOverview.hotbarSlots.map((slot) => (
          <article className="rpg-hotbar-slot-row" key={slot.slot}>
            <button
              type="button"
              aria-pressed={activeHotbarSlot === slot.slot}
              disabled={isApplyingLoadoutAction || !slot.ability}
              onClick={() => {
                onSelectSlot(slot.slot);
                if (slot.ability) {
                  applyHotbarAction({ action: 'hotbar', hotbar_slot: slot.slot }, `Use ${slot.ability.name} from hotbar slot ${slot.slot} on the best available target.`);
                }
              }}
            >
              <small>{slot.slot}</small>
              <span>{slot.ability?.icon ?? '+'}</span>
              <strong>{slot.ability?.name ?? 'Empty slot'}</strong>
            </button>
            <button
              className="rpg-mini-button"
              disabled={isApplyingLoadoutAction || !slot.ability}
              onClick={() => applyHotbarAction({ action: 'remove_hotbar', hotbar_slot: slot.slot }, `Remove hotbar slot ${slot.slot}.`)}
              type="button"
            >
              Remove
            </button>
          </article>
        ))}
      </div>
      <LoadoutDetailCard
        eyebrow="Selected hotbar slot"
        title={selectedAbility ? `${selectedSlot?.slot}: ${selectedAbility.name}` : `Slot ${activeHotbarSlot}`}
        detail={selectedAbility ? abilityDetail(selectedAbility) : 'Assign an unlocked active ability from the Abilities tab.'}
        actions={
          selectedAbility
            ? [
                { label: 'Use slot', command: `Use ${selectedAbility.name} from hotbar slot ${selectedSlot?.slot}.`, apply: () => applyHotbarAction({ action: 'hotbar', hotbar_slot: selectedSlot?.slot }, `Use ${selectedAbility.name} from hotbar slot ${selectedSlot?.slot}.`) },
                { label: 'Remove', command: `Remove hotbar slot ${selectedSlot?.slot}.`, apply: () => applyHotbarAction({ action: 'remove_hotbar', hotbar_slot: selectedSlot?.slot }, `Remove hotbar slot ${selectedSlot?.slot}.`) },
              ]
            : []
        }
        disabled={isApplyingLoadoutAction}
        onSelectCommand={onSelectCommand}
      />
    </div>
  );
}

export function SkillsPanel({ disabled, onSelectCommand, skills }: { disabled: boolean; onSelectCommand: (command: string) => void; skills: SkillProgressionPreview[] }) {
  const practice = (label: string) => onSelectCommand(`Practice ${label} with a careful training drill and record any skill progress.`);
  return (
    <div aria-labelledby="rpg-skills-loadout-tab" className="rpg-skill-panel" id="rpg-skills-loadout-panel" role="tabpanel">
      {skills.length ? (
        <ul className="rpg-skill-list">
          {skills.map((skill) => {
            const threshold = skill.threshold;
            const percent = Math.min(100, Math.round((skill.xp / threshold) * 100));
            return (
              <li className="rpg-skill-row" key={skill.id}>
                <span className="rpg-skill-rank" aria-label={`Rank ${skill.rank}`}>{skill.rank}</span>
                <div className="rpg-skill-copy">
                  <strong>{skill.label}</strong>
                  <div className="rpg-skill-progress" role="progressbar" aria-label={`${skill.label} progress to rank ${skill.rank + 1}`}
                    aria-valuemin={0} aria-valuemax={threshold} aria-valuenow={skill.xp}>
                    <span style={{ width: `${percent}%` }} />
                  </div>
                  <small>{skill.xp} / {threshold} XP to rank {skill.rank + 1}{skill.source ? ` · last from ${skill.source.replaceAll('_', ' ')}` : ''}</small>
                </div>
                <button className="rpg-mini-button" disabled={disabled} onClick={() => practice(skill.label)} type="button" aria-label={`Practice ${skill.label}`}>
                  Practice
                </button>
              </li>
            );
          })}
        </ul>
      ) : (
        <div className="rpg-skill-empty">
          <strong>No skill progress yet</strong>
          <span>Using abilities earns skill XP for the capability they train; each rank needs more practice than the last.</span>
          <button className="rpg-mini-button" disabled={disabled} onClick={() => practice('Swordsmanship')} type="button">Practice Swordsmanship</button>
        </div>
      )}
      <button className="rpg-secondary-button rpg-skill-review" disabled={disabled} type="button"
        onClick={() => onSelectCommand('Check my skill ranks, XP, and recent training progress.')}>
        Review my skills
      </button>
    </div>
  );
}

export function TraitsPanel({ disabled, onSelectCommand, traits }: { disabled: boolean; onSelectCommand: (command: string) => void; traits: AbilityPreview[] }) {
  return (
    <div aria-labelledby="rpg-traits-loadout-tab" className="rpg-list-stack rpg-compact-panel" id="rpg-traits-loadout-panel" role="tabpanel">
      {traits.length ? (
        traits.map((trait) => (
          <article className="rpg-list-row" key={trait.id}>
            <span className="rpg-icon-tile" aria-hidden="true">{trait.icon}</span>
            <div>
              <strong>{trait.name}</strong>
              <span>{trait.statusLabel} • {trait.influenceTags.length ? trait.influenceTags.map(titleCase).join(', ') : 'No influence tags indexed'}</span>
              <div role="group" className="rpg-loadout-actions" aria-label={`${trait.name} trait actions`}>
                <button className="rpg-mini-button" disabled={disabled} onClick={() => onSelectCommand(`Inspect the ${trait.name} trait and explain how it affects the current situation.`)} type="button">
                  Inspect trait
                </button>
                <button className="rpg-mini-button" disabled={disabled} onClick={() => onSelectCommand(`Lean on the ${trait.name} trait to influence my next action.`)} type="button">
                  Use trait
                </button>
              </div>
            </div>
          </article>
        ))
      ) : (
        <article className="rpg-list-row">
          <span className="rpg-icon-tile">*</span>
          <div>
            <strong>No narrative traits indexed</strong>
            <span>Traits appear here once the selected session has a saved ability tree.</span>
            <div role="group" className="rpg-loadout-actions" aria-label="Trait actions">
              <button className="rpg-mini-button" disabled={disabled} onClick={() => onSelectCommand('Inspect my current traits and personality hooks for this scene.')} type="button">
                Inspect traits
              </button>
            </div>
          </div>
        </article>
      )}
    </div>
  );
}

export function EffectsPanel({ disabled, effects, onSelectCommand }: { disabled: boolean; effects: EffectPreview[]; onSelectCommand: (command: string) => void }) {
  return (
    <div aria-labelledby="rpg-effects-loadout-tab" className="rpg-list-stack rpg-compact-panel" id="rpg-effects-loadout-panel" role="tabpanel">
      {effects.length ? (
        effects.map((effect) => (
          <article className="rpg-list-row" key={effect.id}>
            <span className="rpg-icon-tile" aria-hidden="true">✦</span>
            <div>
              <strong>{effect.name}</strong>
              <span>{effect.detail}{effect.remaining !== undefined ? ` • ${effect.remaining} turn(s) remaining` : ''}</span>
              <div role="group" className="rpg-loadout-actions" aria-label={`${effect.name} effect actions`}>
                <button className="rpg-mini-button" disabled={disabled} onClick={() => onSelectCommand(`Inspect the active effect ${effect.name} and summarize its current modifier.`)} type="button">
                  Inspect effect
                </button>
                <button className="rpg-mini-button" disabled={disabled} onClick={() => onSelectCommand(`Act while taking advantage of the active effect ${effect.name}.`)} type="button">
                  Use effect
                </button>
              </div>
            </div>
          </article>
        ))
      ) : (
        <article className="rpg-list-row">
          <span className="rpg-icon-tile">✦</span>
          <div>
            <strong>No active effects</strong>
            <span>Temporary ability effects and runtime modifiers appear here after ability use.</span>
            <div role="group" className="rpg-loadout-actions" aria-label="Effect actions">
              <button className="rpg-mini-button" disabled={disabled} onClick={() => onSelectCommand('Inspect current active effects and temporary modifiers.')} type="button">
                Inspect effects
              </button>
            </div>
          </div>
        </article>
      )}
    </div>
  );
}

export function CoveragePanel({ coverage, disabled, onRefreshCoverage, onSelectCommand }: { coverage: AbilityCoveragePreview; disabled: boolean; onRefreshCoverage: () => void; onSelectCommand: (command: string) => void }) {
  const percent = Math.round(coverage.score * 100);
  const dimensionRows = REQUIRED_DIMENSIONS.map((dimension) => ({
    dimension,
    count: coverage.dimensionCounts[dimension] ?? 0,
    covered: coverage.coveredDimensions.includes(dimension),
  }));
  const sourceRows = Object.entries(coverage.sourceCounts).sort(([, left], [, right]) => right - left).slice(0, 6);
  const firstMissingDimension = coverage.missingDimensions[0] ?? REQUIRED_DIMENSIONS.find((dimension) => !coverage.coveredDimensions.includes(dimension)) ?? 'resources';

  return (
    <div aria-labelledby="rpg-coverage-loadout-tab" className="rpg-coverage-panel" id="rpg-coverage-loadout-panel" role="tabpanel">
      <section className="rpg-coverage-summary-card" aria-label="Ability coverage score">
        <div className="rpg-coverage-score">
          <strong>{percent}%</strong>
          <span>{coverage.ok ? 'All required dimensions covered' : `${coverage.missingDimensions.length} dimension${coverage.missingDimensions.length === 1 ? '' : 's'} still missing`}</span>
        </div>
        <div role="img" className="rpg-coverage-meter" aria-label={`Ability dimension coverage ${percent}%`}>
          <span style={{ width: `${Math.max(0, Math.min(100, percent))}%` }} />
        </div>
        <small>{coverage.totalObservations} deterministic observation{coverage.totalObservations === 1 ? '' : 's'} indexed from ability traces, world effects, passives, traits, and timeline events.</small>
        <div role="group" className="rpg-loadout-actions" aria-label="Coverage actions">
          <button className="rpg-mini-button" disabled={disabled} onClick={onRefreshCoverage} type="button">
            Refresh coverage
          </button>
          <button className="rpg-mini-button" disabled={disabled} onClick={() => onSelectCommand(`Practice or use an ability that covers the ${titleCase(firstMissingDimension)} dimension.`)} type="button">
            Practice missing dimension
          </button>
        </div>
      </section>

      <div role="group" className="rpg-coverage-grid" aria-label="Ability dimension coverage">
        {dimensionRows.map((row) => (
          <article className={row.covered ? 'rpg-coverage-dimension covered' : 'rpg-coverage-dimension missing'} key={row.dimension}>
            <strong>{titleCase(row.dimension)}</strong>
            <span>{row.covered ? `${row.count} observation${row.count === 1 ? '' : 's'}` : 'Missing'}</span>
          </article>
        ))}
      </div>

      <div className="rpg-loadout-layout">
        <section className="rpg-list-stack rpg-compact-panel" aria-label="Coverage sources">
          {sourceRows.length ? (
            sourceRows.map(([source, count]) => (
              <article className="rpg-list-row" key={source}>
                <span className="rpg-icon-tile" aria-hidden="true">◎</span>
                <div>
                  <strong>{titleCase(source)}</strong>
                  <span>{count} observation{count === 1 ? '' : 's'}</span>
                </div>
              </article>
            ))
          ) : (
            <article className="rpg-list-row"><span className="rpg-icon-tile">◎</span><div><strong>No coverage sources yet</strong><span>Use abilities, passives, traits, or world effects to populate coverage.</span></div></article>
          )}
        </section>
        <section className="rpg-list-stack rpg-compact-panel" aria-label="Coverage warnings">
          {coverage.warnings.length ? (
            coverage.warnings.slice(0, 6).map((warning) => (
              <article className="rpg-list-row" key={warning}>
                <span className="rpg-icon-tile" aria-hidden="true">!</span>
                <div>
                  <strong>Coverage warning</strong>
                  <span>{warning}</span>
                </div>
              </article>
            ))
          ) : (
            <article className="rpg-list-row"><span className="rpg-icon-tile">✓</span><div><strong>No coverage warnings</strong><span>All indexed dimensions are supported by the deterministic ability system.</span></div></article>
          )}
        </section>
      </div>
    </div>
  );
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
      <div role="group" className="rpg-loadout-actions" aria-label={`${title} actions`}>
        {actions.map((action) => (
          <button className="rpg-mini-button" disabled={disabled} key={action.label} onClick={() => (action.apply ? action.apply() : onSelectCommand(action.command))} type="button">
            {action.label}
          </button>
        ))}
      </div>
    </aside>
  );
}
