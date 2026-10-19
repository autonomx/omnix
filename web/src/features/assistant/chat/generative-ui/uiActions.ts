import type { ChoicesBlock, FormBlock, FormField } from './schema';

/** What the user did with a widget; it rides on the message they send (GUI-5.4). */
export type ChatUiAction = {
  source_message_id: string;
  block_id: string;
  action: 'choose' | 'submit';
  option_index?: number | null;
  values?: Record<string, string | number | boolean> | null;
};

/** A widget's submitted state, rebuilt from the user message that answered it (GUI-5.3). */
export type ChatUiSubmission = { action: ChatUiAction; content: string };

export type FormValues = Record<string, string | number | boolean>;

/** How a reply's widgets reach the composer and the send path; absent when the message is not interactive. */
export type ChatUiInteraction = {
  /** Only the latest assistant reply's widgets are active. */
  active: boolean;
  /** Submissions for this message's blocks, by block id. */
  submissions: Record<string, ChatUiSubmission>;
  /** Send a choice: the label is the message, exactly as shown. */
  choose: (text: string, action: ChatUiAction) => void;
  /** Put a filled form template in the composer; the user reviews and sends it. */
  fillComposer: (text: string, action: ChatUiAction) => void;
};

type UserMessage = { id: string; role: string; content: string; metadata?: Record<string, unknown> | null };

/** The latest user submission per `source_message_id` and block, from the transcript. */
export function chatUiSubmissions(messages: readonly UserMessage[]): Map<string, Record<string, ChatUiSubmission>> {
  const result = new Map<string, Record<string, ChatUiSubmission>>();
  for (const message of messages) {
    if (message.role !== 'user') continue;
    const action = readUiAction(message.metadata?.ui_action);
    if (!action) continue;
    const blocks = result.get(action.source_message_id) ?? {};
    blocks[action.block_id] = { action, content: message.content };
    result.set(action.source_message_id, blocks);
  }
  return result;
}

function readUiAction(value: unknown): ChatUiAction | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  if (typeof record.source_message_id !== 'string' || typeof record.block_id !== 'string') return null;
  if (record.action !== 'choose' && record.action !== 'submit') return null;
  return {
    source_message_id: record.source_message_id,
    block_id: record.block_id,
    action: record.action,
    option_index: typeof record.option_index === 'number' ? record.option_index : null,
    values: record.values && typeof record.values === 'object' && !Array.isArray(record.values) ? record.values as FormValues : null,
  };
}

export function choiceAction(messageId: string, block: ChoicesBlock, optionIndex: number): ChatUiAction {
  return { source_message_id: messageId, block_id: block.id, action: 'choose', option_index: optionIndex };
}

/** A field's starting value: its default, or the first option / minimum / empty / off. */
export function initialFieldValue(field: FormField): string | number | boolean {
  if (field.kind === 'toggle') return typeof field.default === 'boolean' ? field.default : false;
  if (field.kind === 'slider') return typeof field.default === 'number' ? field.default : field.min ?? 0;
  if (field.kind === 'select') return typeof field.default === 'string' ? field.default : field.options?.[0] ?? '';
  return typeof field.default === 'string' ? field.default : '';
}

export function initialFormValues(block: FormBlock): FormValues {
  return Object.fromEntries(block.fields.map((field) => [field.name, initialFieldValue(field)]));
}

/** Display text for a value: toggles read yes/no, numbers drop trailing zeros. */
export function formValueText(field: FormField, value: string | number | boolean | undefined): string {
  if (field.kind === 'toggle') return value ? 'yes' : 'no';
  if (typeof value === 'number') return String(Number(value.toFixed(6)));
  return String(value ?? '').trim();
}

/**
 * The template with `{name}` placeholders replaced by plain-text values, in one pass:
 * braces inside a value are inserted as typed and never substituted again.
 */
export function fillFormTemplate(block: FormBlock, values: FormValues): string {
  const fields = new Map(block.fields.map((field) => [field.name, field]));
  return block.template.replace(/\{([A-Za-z][A-Za-z0-9_]{0,31})\}/g, (placeholder, name: string) => {
    const field = fields.get(name);
    return field ? formValueText(field, values[name]) : placeholder;
  });
}

/** Field names that are required and still empty. */
export function missingRequiredFields(block: FormBlock, values: FormValues): string[] {
  return block.fields
    .filter((field) => field.required && field.kind !== 'toggle' && formValueText(field, values[field.name]) === '')
    .map((field) => field.name);
}

export function formAction(messageId: string, block: FormBlock, values: FormValues): ChatUiAction {
  return { source_message_id: messageId, block_id: block.id, action: 'submit', values: { ...values } };
}
