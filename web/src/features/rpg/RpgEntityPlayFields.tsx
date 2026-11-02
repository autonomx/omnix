/**
 * How an entity plays, as the world editor's form writes it (evolution roadmap EV-6): an item's gear (the slot it is
 * worn in, the numbers it fights with, its material) and a character's home, aliases and group. The form edits the
 * entity's structured draft; "Save Canonical Entity" saves it, as an edit of the JSON would.
 */
import { useState } from 'react';

type Entity = Record<string, unknown>;

const SLOTS: Array<[string, string]> = [
  ['', 'Not worn'], ['main_hand', 'Weapon'], ['off_hand', 'Shield'], ['body', 'Armor'], ['head', 'Helmet'],
  ['cloak', 'Cloak'], ['ring', 'Ring'], ['tool', 'Tool'],
];
const STATS: Array<[string, string]> = [
  ['damage_min', 'Damage from'], ['damage_max', 'Damage to'], ['accuracy_bonus', 'Accuracy'], ['armor', 'Armor'],
  ['defense_bonus', 'Defense bonus'],
];
const ITEM_KINDS = new Set(['item', 'equipment', 'weapon', 'armor', 'gear']);
const CHARACTER_KINDS = new Set(['npc', 'character', 'person', 'actor']);

function record(value: unknown): Entity {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Entity : {};
}

export function entityPlayKind(entity: Entity): 'item' | 'character' | '' {
  const kind = String(entity.kind ?? '').toLowerCase();
  if (ITEM_KINDS.has(kind) || entity.equipment) return 'item';
  if (CHARACTER_KINDS.has(kind)) return 'character';
  return '';
}

export function RpgEntityPlayFields({ entity, title, onChange }: { entity: Entity; title: string; onChange: (next: Entity) => void }) {
  const kind = entityPlayKind(entity);
  if (!kind) return null;
  if (kind === 'item') {
    const equipment = record(entity.equipment);
    const stats = record(equipment.stats);
    const setEquipment = (next: Entity) => {
      const rest = { ...entity };
      delete rest.equipment;
      onChange(next.slot ? { ...rest, equipment: next } : rest);
    };
    return (
      <fieldset className="rpg-entity-play-fields" aria-label={`How ${title} plays`}>
        <legend>Gear</legend>
        <label>
          <span>Worn as</span>
          <select value={String(equipment.slot ?? '')} onChange={(event) => setEquipment({ ...equipment, slot: event.currentTarget.value })}>
            {SLOTS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        {equipment.slot ? (
          <>
            {STATS.map(([key, label]) => (
              <label key={key}>
                <span>{label}</span>
                <input min={0} max={200} type="number" value={stats[key] === undefined ? '' : Number(stats[key])}
                  onChange={(event) => {
                    const raw = event.currentTarget.value;
                    const next = { ...stats };
                    if (raw === '') delete next[key];
                    else next[key] = Number(raw);
                    setEquipment({ ...equipment, stats: next });
                  }} />
              </label>
            ))}
            <label>
              <span>Material</span>
              <input value={String(equipment.material ?? '')} onChange={(event) => setEquipment({ ...equipment, material: event.currentTarget.value })} />
            </label>
          </>
        ) : null}
      </fieldset>
    );
  }
  return <CharacterFields entity={entity} title={title} onChange={onChange} />;
}

function CharacterFields({ entity, title, onChange }: { entity: Entity; title: string; onChange: (next: Entity) => void }) {
  const aliases = Array.isArray(entity.aliases) ? entity.aliases.map(String) : [];
  const [typed, setTyped] = useState(aliases.join(', '));  // as typed; read into a list when the field is left
  return (
    <fieldset className="rpg-entity-play-fields" aria-label={`How ${title} plays`}>
      <legend>Character</legend>
      <label>
        <span>Home (a place id)</span>
        <input value={String(entity.location_id ?? '')} onChange={(event) => onChange({ ...entity, location_id: event.currentTarget.value })} />
      </label>
      <label>
        <span>Aliases (comma separated)</span>
        <input value={typed} onChange={(event) => setTyped(event.currentTarget.value)} onBlur={() => onChange({
          ...entity, aliases: typed.split(',').map((part) => part.trim()).filter(Boolean),
        })} />
      </label>
      <label>
        <span>Group (a group id)</span>
        <input value={String(entity.group_id ?? entity.faction_id ?? '')} onChange={(event) => onChange({ ...entity, group_id: event.currentTarget.value })} />
      </label>
    </fieldset>
  );
}
