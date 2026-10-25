import type { RpgInventoryItemPreview } from './rpgUiState';

export type RpgItemUiActionKind = 'use' | 'equip' | 'unequip' | 'drop' | 'sell';

/** A pack action taken from the item panel: a loadout turn (use, equip, take off, drop), or a typed turn (sell). */
export type RpgItemUiActionMode = 'loadout' | 'turn';

export interface RpgItemUiAction {
  id: string;
  kind: RpgItemUiActionKind;
  label: string;
  detail: string;
  mode: RpgItemUiActionMode;
  command: string;
  payload: Record<string, unknown>;
  disabled?: boolean;
}

export interface RpgItemDetailPreview {
  itemName: string;
  icon: string;
  countLabel: string;
  summary: string;
  status: string;
  category?: string;
}

interface BuildSelectedItemActionsInput {
  item?: RpgInventoryItemPreview;
  selectedSessionId?: string | null;
}

const ACTIONS: Record<RpgItemUiActionKind, { label: string; detail: (name: string) => string }> = {
  use: { label: 'Use', detail: (name) => `Use the ${name}.` },
  equip: { label: 'Equip', detail: (name) => `Wear or wield the ${name}.` },
  unequip: { label: 'Unequip', detail: (name) => `Put the ${name} away; it stays in your pack.` },
  drop: { label: 'Drop', detail: (name) => `Put the ${name} down here.` },
  sell: { label: 'Sell', detail: (name) => `Offer the ${name} to someone here who buys.` },
};

// A preview item, with no game to ask: what any carried thing may offer.
const PREVIEW_ACTIONS: RpgItemUiActionKind[] = ['use', 'equip', 'drop', 'sell'];

function isActionKind(value: string): value is RpgItemUiActionKind {
  return value in ACTIONS;
}

/** The actions the game offers for the selected item, in its order; each is a turn. */
export function buildSelectedItemActions({ item, selectedSessionId }: BuildSelectedItemActionsInput): RpgItemUiAction[] {
  if (!item) {
    return [];
  }
  const name = item.label;
  const kinds = item.actions ? item.actions.filter(isActionKind) : PREVIEW_ACTIONS;
  return kinds.map((kind) => ({
    id: `${kind}:${name}`,
    kind,
    label: ACTIONS[kind].label,
    detail: ACTIONS[kind].detail(name),
    mode: kind === 'sell' ? 'turn' : 'loadout',
    command: kind === 'sell' ? `I sell the ${name}.` : `${ACTIONS[kind].label} ${name}`,
    payload: kind === 'sell' ? {} : { action: kind, item_name: name },
    disabled: !selectedSessionId,
  }));
}

/** What the world says of the selected item: its description, its kind, and whether it is worn. */
export function buildItemDetailPreview(item: RpgInventoryItemPreview | undefined): RpgItemDetailPreview | undefined {
  if (!item) {
    return undefined;
  }
  return {
    itemName: item.label,
    icon: item.icon,
    countLabel: `${item.count || '1'} carried`,
    summary: item.description ? `${item.description[0].toUpperCase()}${item.description.slice(1)}.`.replace(/\.\.$/, '.') : 'Nothing more is known of it.',
    status: item.worn ? 'Worn' : 'Carried',
    category: item.category,
  };
}
