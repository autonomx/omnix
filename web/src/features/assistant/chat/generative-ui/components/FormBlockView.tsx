import { useId, useState, type FormEvent } from 'react';
import type { FormBlock, FormField } from '../schema';
import {
  fillFormTemplate,
  formAction,
  formValueText,
  initialFormValues,
  missingRequiredFields,
  type ChatUiInteraction,
  type FormValues,
} from '../uiActions';

/**
 * A parameter form that fills the composer: submitting puts the filled template in the
 * message box for the user to review and send. Nothing is sent from here.
 */
export function FormBlockView({ block, messageId, interaction }: { block: FormBlock; messageId: string; interaction?: ChatUiInteraction }) {
  const submitted = interaction?.submissions[block.id];
  const [values, setValues] = useState<FormValues>(() => ({ ...initialFormValues(block), ...(submitted?.action.values ?? {}) }));
  const [missing, setMissing] = useState<string[]>([]);
  const formId = useId();
  const active = Boolean(interaction?.active) && !submitted;
  const shown = submitted?.action.values ? { ...values, ...submitted.action.values } : values;
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!active || !interaction) return;
    const required = missingRequiredFields(block, values);
    setMissing(required);
    if (required.length) return;
    interaction.fillComposer(fillFormTemplate(block, values), formAction(messageId, block, values));
  };
  return (
    <section className="gui-block gui-form" aria-label={block.title ?? 'Form'}>
      {block.title ? <header className="gui-block-header"><h4>{block.title}</h4></header> : null}
      <form onSubmit={submit} noValidate>
        <fieldset disabled={!active}>
          <legend className="gui-visually-hidden">{block.title ?? 'Form'}</legend>
          {block.fields.map((field) => (
            <FormFieldControl
              key={field.name}
              id={`${formId}-${field.name}`}
              field={field}
              value={shown[field.name]}
              invalid={missing.includes(field.name)}
              onChange={(value) => setValues((current) => ({ ...current, [field.name]: value }))}
            />
          ))}
          {missing.length ? <div className="gui-form-error" role="alert">Fill in the required fields.</div> : null}
          <div className="gui-form-actions">
            <button type="submit" className="gui-form-submit">{submitted ? 'Sent' : block.submit_label ?? 'Fill message'}</button>
            {active ? <span className="gui-form-hint">Puts the message in the composer; you send it.</span> : null}
          </div>
        </fieldset>
      </form>
    </section>
  );
}

function FormFieldControl({ id, field, value, invalid, onChange }: {
  id: string;
  field: FormField;
  value: string | number | boolean | undefined;
  invalid: boolean;
  onChange: (value: string | number | boolean) => void;
}) {
  const label = <label htmlFor={id}>{field.label}{field.required ? <span aria-hidden="true"> *</span> : null}</label>;
  if (field.kind === 'toggle') {
    return (
      <div className="gui-form-field gui-form-toggle">
        <input id={id} type="checkbox" role="switch" checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)} />
        {label}
      </div>
    );
  }
  if (field.kind === 'select') {
    return (
      <div className="gui-form-field">
        {label}
        <select id={id} value={String(value ?? '')} required={field.required} aria-invalid={invalid || undefined} onChange={(event) => onChange(event.target.value)}>
          {(field.options ?? []).map((option) => <option key={option} value={option}>{option}</option>)}
        </select>
      </div>
    );
  }
  if (field.kind === 'slider') {
    const number = typeof value === 'number' ? value : Number(value ?? field.min ?? 0);
    return (
      <div className="gui-form-field">
        {label}
        <div className="gui-form-slider">
          <input
            id={id}
            type="range"
            min={field.min}
            max={field.max}
            step={field.step ?? 1}
            value={number}
            aria-valuetext={`${formValueText(field, number)}${field.unit ? ` ${field.unit}` : ''}`}
            onChange={(event) => onChange(Number(event.target.value))}
          />
          <output htmlFor={id}>{formValueText(field, number)}{field.unit ? ` ${field.unit}` : ''}</output>
        </div>
      </div>
    );
  }
  return (
    <div className="gui-form-field">
      {label}
      <input
        id={id}
        type="text"
        value={String(value ?? '')}
        maxLength={field.max_length ?? 200}
        placeholder={field.placeholder}
        required={field.required}
        aria-invalid={invalid || undefined}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}
