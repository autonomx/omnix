import type { RpgPlaySectionsReferences } from './api/rpgWorldPlaySectionsClient';
import type { NameOf, PlayField, PlayRow, PlayRows, RefKind } from './rpgPlaySectionFields';

/** A play section's rows as a form (RQ-4.1): each row a collapsible card of its fields; lists within lists. */

interface FormContext {
  refs: RpgPlaySectionsReferences;
  name: NameOf;
}

const REF_LABELS: Record<RefKind, string> = {
  people: 'People', places: 'Places', items: 'Items', creatures: 'Creatures', regions: 'Regions', quests: 'Quests',
};

function numberOr(value: string, nullable: boolean | undefined): number | null {
  if (value.trim() === '') return nullable ? null : 0;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function RefSelect({ field, value, onChange, context }: {
  field: Extract<PlayField, { kind: 'ref' }>;
  value: unknown;
  onChange: (next: string) => void;
  context: FormContext;
}) {
  const current = typeof value === 'string' ? value : '';
  const known = field.refs.some((kind) => context.refs[kind].some((row) => row.id === current));
  return (
    <select value={current} onChange={(event) => onChange(event.currentTarget.value)}>
      <option value="">{field.optional ?? 'Choose…'}</option>
      {current && !known ? <option value={current}>{current} (not in this world)</option> : null}
      {field.refs.map((kind) => (
        <optgroup key={kind} label={REF_LABELS[kind]}>
          {context.refs[kind].map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
        </optgroup>
      ))}
    </select>
  );
}

function LeverInput({ value, onChange, context }: { value: unknown; onChange: (next: string) => void; context: FormContext }) {
  const [kind, subject = ''] = String(value ?? 'defeat:').split(/:(.*)/s);
  const refs = kind === 'quest' ? context.refs.quests : context.refs.creatures;
  return (
    <span className="rpg-play-lever">
      <select aria-label="Pulled by" value={kind} onChange={(event) => onChange(`${event.currentTarget.value}:`)}>
        <option value="defeat">Defeating a creature</option>
        <option value="quest">Finishing a quest</option>
      </select>
      <select aria-label={kind === 'quest' ? 'Quest' : 'Creature'} value={subject} onChange={(event) => onChange(`${kind}:${event.currentTarget.value}`)}>
        <option value="">Choose…</option>
        {subject && !refs.some((row) => row.id === subject) ? <option value={subject}>{subject} (not in this world)</option> : null}
        {refs.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
      </select>
    </span>
  );
}

function PriceInput({ value, onChange, nullable }: { value: unknown; onChange: (next: PlayRow | null) => void; nullable?: boolean }) {
  if (value === null || value === undefined) {
    return nullable
      ? <button className="rpg-secondary-button" type="button" onClick={() => onChange({ gold: 0, silver: 1, copper: 0 })}>Set a price</button>
      : null;
  }
  const price = value as PlayRow;
  return (
    <span className="rpg-play-price">
      {(['gold', 'silver', 'copper'] as const).map((coin) => (
        <label key={coin}>
          <input min={0} type="number" value={Number(price[coin] ?? 0)} onChange={(event) => onChange({ ...price, [coin]: numberOr(event.currentTarget.value, false) })} />
          <span>{coin}</span>
        </label>
      ))}
      {nullable ? <button className="rpg-secondary-button" type="button" onClick={() => onChange(null)}>No price</button> : null}
    </span>
  );
}

function GroupInput({ field, value, onChange, context }: {
  field: Extract<PlayField, { kind: 'group' }>;
  value: unknown;
  onChange: (next: PlayRow | null) => void;
  context: FormContext;
}) {
  if (value === null || value === undefined) {
    return <button className="rpg-secondary-button" type="button" onClick={() => onChange(field.blank())}>Set {field.label.toLowerCase()}</button>;
  }
  const row = value as PlayRow;
  return (
    <div className="rpg-play-group">
      <FieldGrid fields={field.fields} row={row} onChange={onChange} context={context} />
      <button className="rpg-secondary-button" type="button" onClick={() => onChange(null)}>Take {field.label.toLowerCase()} from the lore</button>
    </div>
  );
}

function FieldInput({ field, value, onChange, context }: {
  field: PlayField;
  value: unknown;
  onChange: (next: unknown) => void;
  context: FormContext;
}) {
  switch (field.kind) {
    case 'text':
      return <input value={String(value ?? '')} onChange={(event) => onChange(event.currentTarget.value)} />;
    case 'textarea':
      return <textarea rows={2} value={String(value ?? '')} onChange={(event) => onChange(event.currentTarget.value)} />;
    case 'number':
      return <input max={field.max} min={field.min} step={field.step ?? 1} type="number" value={value === null || value === undefined ? '' : Number(value)} onChange={(event) => onChange(numberOr(event.currentTarget.value, field.nullable))} />;
    case 'select':
      return (
        <select value={value === null || value === undefined ? '' : String(value)} onChange={(event) => onChange(event.currentTarget.value || (field.nullable ? null : ''))}>
          {field.nullable ? <option value="">{field.nullable}</option> : null}
          {field.options.map(([option, label]) => <option key={option} value={option}>{label}</option>)}
        </select>
      );
    case 'ref':
      return <RefSelect field={field} value={value} onChange={onChange} context={context} />;
    case 'tags':
      return <input value={Array.isArray(value) ? value.join(', ') : ''} onChange={(event) => onChange(event.currentTarget.value.split(',').map((part) => part.trim()).filter(Boolean))} />;
    case 'price':
      return <PriceInput nullable={field.nullable} value={value} onChange={onChange} />;
    case 'lever':
      return <LeverInput value={value} onChange={onChange} context={context} />;
    case 'group':
      return <GroupInput field={field} value={value} onChange={onChange} context={context} />;
    case 'list':
      return <PlaySectionRows rows={Array.isArray(value) ? value as PlayRow[] : []} spec={field.rows} onChange={onChange} context={context} />;
  }
}

function FieldGrid({ fields, row, onChange, context }: {
  fields: PlayField[];
  row: PlayRow;
  onChange: (next: PlayRow) => void;
  context: FormContext;
}) {
  return (
    <div className="rpg-play-fields">
      {fields.map((field) => {
        const wide = field.kind === 'list' || field.kind === 'group' || field.kind === 'textarea';
        const control = <FieldInput field={field} value={row[field.key]} onChange={(next) => onChange({ ...row, [field.key]: next })} context={context} />;
        return wide || field.kind === 'price' || field.kind === 'lever'
          ? <div className={wide ? 'rpg-play-field is-wide' : 'rpg-play-field'} key={field.key} role="group" aria-label={field.label}><span>{field.label}</span>{control}</div>
          : <label className="rpg-play-field" key={field.key}><span>{field.label}</span>{control}</label>;
      })}
    </div>
  );
}

export function PlaySectionRows({ rows, spec, onChange, context }: {
  rows: PlayRow[];
  spec: PlayRows;
  onChange: (next: PlayRow[]) => void;
  context: FormContext;
}) {
  return (
    <div className="rpg-play-rows">
      {rows.map((row, index) => (
        <details className="rpg-play-row" key={index} open={rows.length <= 3}>
          <summary><strong>{spec.title(row, context.name)}</strong></summary>
          <FieldGrid fields={spec.fields} row={row} onChange={(next) => onChange(rows.map((other, at) => (at === index ? next : other)))} context={context} />
          <button aria-label={`Remove ${spec.title(row, context.name)}`} className="rpg-secondary-button rpg-play-remove" type="button" onClick={() => onChange(rows.filter((_, other) => other !== index))}>Remove</button>
        </details>
      ))}
      <button className="rpg-secondary-button rpg-play-add" type="button" onClick={() => onChange([...rows, spec.blank(rows)])}>{spec.add}</button>
    </div>
  );
}
