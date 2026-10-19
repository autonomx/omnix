import { z } from 'zod';

/*
 * Client mirror of the server's block catalog (src/app/platform/chat/generative_ui/catalog.py).
 * The server is authoritative; this re-validates stored `metadata.ui` as defence in depth.
 * Both sides run the shared golden fixtures in resources/chat/generative_ui/fixtures.
 */

const MAX_LABEL = 120;
const MAX_STRING = 2_000;

/**
 * A string of `min`-`max` characters counted as the server counts them: code points, not the
 * UTF-16 units `z.string().max()` counts, so an emoji-laden label the server kept is not refused.
 */
function text(max: number, min = 0) {
  return z.string().refine((value) => {
    const length = Array.from(value).length;
    return length >= min && length <= max;
  }, { message: `expected ${min}-${max} characters` });
}

const label = text(MAX_LABEL, 1);
const optionalLabel = label.optional();
const tone = z.enum(['neutral', 'positive', 'negative', 'warning', 'info']);
const provenance = z.enum(['model', 'bound', 'market_data']);

const binding = z.strictObject({
  path: z.string(),
  ref: z.string(),
  title: z.string(),
  url: z.string().optional(),
});

const blockBase = {
  id: z.string().min(1).max(64),
  v: z.literal(1),
  bindings: z.array(binding).default([]),
};

export const statsBlockSchema = z.strictObject({
  ...blockBase,
  type: z.literal('stats'),
  title: optionalLabel,
  items: z.array(z.strictObject({
    label,
    value: label,
    delta: text(MAX_LABEL).optional(),
    trend: z.enum(['up', 'down', 'flat']).optional(),
    tone: tone.optional(),
    hint: text(MAX_STRING).optional(),
  })).min(1).max(6),
  provenance,
});

export const chartBlockSchema = z.strictObject({
  ...blockBase,
  type: z.literal('chart'),
  kind: z.enum(['line', 'area', 'bar']),
  title: optionalLabel,
  size: z.enum(['sm', 'md', 'lg']).default('md'),
  x: z.strictObject({ type: z.enum(['time', 'category']), label: optionalLabel }),
  y: z.strictObject({ label: optionalLabel, format: z.enum(['number', 'percent', 'currency', 'compact']).default('number') }),
  series: z.array(z.strictObject({
    name: label,
    points: z.array(z.tuple([z.union([z.number().int(), z.string()]), z.number()])).min(1).max(2_000),
  })).min(1).max(6),
  provenance,
});

export const priceChartBlockSchema = z.strictObject({
  ...blockBase,
  type: z.literal('price_chart'),
  symbol: z.string().regex(/^[A-Z0-9^][A-Z0-9.\-:/^=]{0,31}$/),
  instrument_id: z.string().min(3).max(200),
  interval: z.enum(['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w']),
  range: z.enum(['1D', '5D', '1M', '3M', '6M', 'YTD', '1Y', '5Y', 'MAX']),
  title: optionalLabel,
  as_of: z.string().min(10),
  provenance: z.literal('market_data'),
});

export const sourcesBlockSchema = z.strictObject({
  ...blockBase,
  type: z.literal('sources'),
  title: optionalLabel,
  refs: z.array(z.strictObject({
    ref: z.string(),
    citation: z.string().optional(),
    title: text(MAX_STRING, 1),
    url: z.string().optional(),
  })).min(1).max(12),
  provenance: z.literal('bound'),
});

export const choicesBlockSchema = z.strictObject({
  ...blockBase,
  type: z.literal('choices'),
  prompt: text(MAX_STRING).optional(),
  options: z.array(z.strictObject({ label: text(160, 1) })).min(2).max(6),
  provenance: z.literal('model'),
});

const formFieldSchema = z.strictObject({
  name: z.string().regex(/^[A-Za-z][A-Za-z0-9_]{0,31}$/),
  label,
  kind: z.enum(['select', 'slider', 'text', 'toggle']),
  required: z.boolean().default(false),
  options: z.array(z.string()).max(20).optional(),
  min: z.number().optional(),
  max: z.number().optional(),
  step: z.number().optional(),
  unit: text(16).optional(),
  max_length: z.number().int().min(1).max(200).optional(),
  placeholder: optionalLabel,
  default: z.union([z.string(), z.number(), z.boolean()]).nullable().optional(),
});

export const formBlockSchema = z.strictObject({
  ...blockBase,
  type: z.literal('form'),
  title: optionalLabel,
  fields: z.array(formFieldSchema).min(1).max(8),
  template: text(500, 1),
  submit_label: optionalLabel,
  provenance: z.literal('model'),
});

export const chatUiBlockSchema = z.discriminatedUnion('type', [
  statsBlockSchema,
  chartBlockSchema,
  priceChartBlockSchema,
  sourcesBlockSchema,
  choicesBlockSchema,
  formBlockSchema,
]);

const segmentSchema = z.strictObject({
  kind: z.enum(['markdown', 'block', 'text']),
  start: z.number().int().min(0).optional(),
  end: z.number().int().min(0).optional(),
  id: z.string().optional(),
  text: z.string().optional(),
});

const diagnosticSchema = z.strictObject({
  block: z.string().optional(),
  code: z.string(),
  path: z.string().optional(),
  severity: z.enum(['info', 'dropped', 'degraded']),
  detail: z.string().optional(),
});

/** The stored envelope; blocks are validated one by one so one bad block cannot hide the rest. */
const payloadSchema = z.strictObject({
  version: z.literal(1),
  compiler_version: z.string(),
  compiled_at: z.string(),
  segments: z.array(segmentSchema),
  blocks: z.record(z.string(), z.unknown()),
  text: z.string(),
  speech: z.string(),
  diagnostics: z.array(diagnosticSchema).default([]),
});

export type StatsBlock = z.infer<typeof statsBlockSchema>;
export type ChartBlock = z.infer<typeof chartBlockSchema>;
export type PriceChartBlock = z.infer<typeof priceChartBlockSchema>;
export type SourcesBlock = z.infer<typeof sourcesBlockSchema>;
export type ChoicesBlock = z.infer<typeof choicesBlockSchema>;
export type FormBlock = z.infer<typeof formBlockSchema>;
export type FormField = z.infer<typeof formFieldSchema>;
export type ChatUiBlock = z.infer<typeof chatUiBlockSchema>;
export type ChatUiDiagnostic = z.infer<typeof diagnosticSchema>;

export type ChatUiRenderSegment =
  | { kind: 'markdown'; key: string; markdown: string }
  | { kind: 'text'; key: string; text: string }
  | { kind: 'block'; key: string; block: ChatUiBlock; text: string };

export type ParsedChatUi = {
  compiledAt: string;
  segments: ChatUiRenderSegment[];
  blocks: Record<string, ChatUiBlock>;
  text: string;
  speech: string;
  diagnostics: ChatUiDiagnostic[];
};

const BLOCK_NOTICE = '[A block could not be shown.]';

/**
 * The renderable form of a message's `metadata.ui`, or null to render the message as plain Markdown.
 *
 * Markdown spans are sliced from `content` by offset; an offset outside the content means the
 * payload does not belong to it, so the whole message falls back. A block that fails client
 * validation shows its text instead. Interrupted replies never render UI (invariant 9).
 */
export function parseChatUi(metadata: Record<string, unknown> | undefined | null, content: string): ParsedChatUi | null {
  if (!metadata || metadata.ui === undefined || metadata.ui === null) return null;
  if (metadata.delivery_status === 'interrupted') return null;
  const envelope = payloadSchema.safeParse(metadata.ui);
  if (!envelope.success) return null;
  const payload = envelope.data;
  const blocks: Record<string, ChatUiBlock> = {};
  const segments: ChatUiRenderSegment[] = [];
  for (const [index, segment] of payload.segments.entries()) {
    const key = `${index}`;
    if (segment.kind === 'markdown') {
      const { start, end } = segment;
      if (start === undefined || end === undefined || start >= end || end > content.length) return null;
      segments.push({ kind: 'markdown', key, markdown: content.slice(start, end) });
    } else if (segment.kind === 'text') {
      segments.push({ kind: 'text', key, text: segment.text ?? BLOCK_NOTICE });
    } else {
      const fallback = segment.text ?? BLOCK_NOTICE;
      const parsed = segment.id ? chatUiBlockSchema.safeParse(payload.blocks[segment.id]) : null;
      if (parsed?.success && parsed.data.id === segment.id) {
        blocks[parsed.data.id] = parsed.data;
        segments.push({ kind: 'block', key, block: parsed.data, text: fallback });
      } else {
        segments.push({ kind: 'text', key, text: fallback });
      }
    }
  }
  return {
    compiledAt: payload.compiled_at,
    segments,
    blocks,
    text: payload.text,
    speech: payload.speech,
    diagnostics: payload.diagnostics,
  };
}
