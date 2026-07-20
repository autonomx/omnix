export type ClauseCommitReason = 'strong-boundary' | 'stable-boundary' | 'deadline' | 'maximum' | 'stream-end';

export type StableClause = {
  text: string;
  reason: ClauseCommitReason;
};

export type ClauseStabilizerOptions = {
  minimumClauseCharacters?: number;
  stableLookaheadCharacters?: number;
  maximumClauseCharacters?: number;
  deadlineMs?: number;
};

const DEFAULT_MINIMUM = 24;
const DEFAULT_LOOKAHEAD = 24;
const DEFAULT_MAXIMUM = 180;
const DEFAULT_DEADLINE_MS = 420;
const STRONG_BOUNDARY = /[.!?][\]})"'’”]*(?=\s|$)/g;
const WEAK_BOUNDARY = /[,;:][\]})"'’”]*(?=\s|$)/g;
const ABBREVIATION = /(?:\b(?:mr|mrs|ms|dr|prof|sr|jr|st|vs|etc|e\.g|i\.e)|\b[A-Z])\.$/i;
const DECIMAL_OR_VERSION = /\d\.\d$/;
const URL_TAIL = /(?:https?:\/\/|www\.)\S*$/i;

export class StableClauseAccumulator {
  private buffer = '';
  private openedAtMs: number | null = null;
  private readonly minimum: number;
  private readonly lookahead: number;
  private readonly maximum: number;
  private readonly deadlineMs: number;

  constructor(options: ClauseStabilizerOptions = {}) {
    this.minimum = positiveInteger(options.minimumClauseCharacters, DEFAULT_MINIMUM);
    this.lookahead = positiveInteger(options.stableLookaheadCharacters, DEFAULT_LOOKAHEAD);
    this.maximum = Math.max(this.minimum, positiveInteger(options.maximumClauseCharacters, DEFAULT_MAXIMUM));
    this.deadlineMs = positiveInteger(options.deadlineMs, DEFAULT_DEADLINE_MS);
  }

  append(fragment: string, nowMs = performance.now()): StableClause[] {
    const normalized = fragment.trim();
    if (!normalized) return [];
    this.buffer = mergeStreamText(this.buffer, normalized);
    if (this.openedAtMs === null) this.openedAtMs = nowMs;
    return this.takeReady(nowMs);
  }

  takeReady(nowMs = performance.now()): StableClause[] {
    const committed: StableClause[] = [];
    while (true) {
      const boundary = this.nextBoundary(nowMs);
      if (!boundary) break;
      const text = this.buffer.slice(0, boundary.end).trim();
      this.buffer = this.buffer.slice(boundary.end).trimStart();
      if (text) committed.push({ text, reason: boundary.reason });
      this.openedAtMs = this.buffer ? nowMs : null;
    }
    return committed;
  }

  flush(): StableClause[] {
    const text = this.buffer.trim();
    this.buffer = '';
    this.openedAtMs = null;
    return text ? [{ text, reason: 'stream-end' }] : [];
  }

  pendingText(): string {
    return this.buffer;
  }

  deadlineRemainingMs(nowMs = performance.now()): number | null {
    if (this.openedAtMs === null || !this.buffer) return null;
    return Math.max(0, this.deadlineMs - (nowMs - this.openedAtMs));
  }

  private nextBoundary(nowMs: number): { end: number; reason: ClauseCommitReason } | null {
    const strong = findSafeBoundary(this.buffer, STRONG_BOUNDARY, this.minimum);
    const weak = findStableWeakBoundary(this.buffer, this.minimum, this.lookahead);
    if (strong !== null || weak !== null) {
      if (weak !== null && (strong === null || weak < strong)) {
        return { end: weak, reason: 'stable-boundary' };
      }
      if (strong !== null) return { end: strong, reason: 'strong-boundary' };
    }

    if (this.buffer.length >= this.maximum) {
      const fallback = safeWhitespaceBoundary(this.buffer, this.maximum, this.minimum);
      if (fallback !== null) return { end: fallback, reason: 'maximum' };
    }

    if (
      this.openedAtMs !== null
      && nowMs - this.openedAtMs >= this.deadlineMs
      && this.buffer.length >= this.minimum
    ) {
      const deadlineBoundary = safeWhitespaceBoundary(
        this.buffer,
        Math.min(this.maximum, this.buffer.length),
        this.minimum,
      );
      if (deadlineBoundary !== null) return { end: deadlineBoundary, reason: 'deadline' };
    }
    return null;
  }
}

export function mergeStreamText(current: string, next: string): string {
  const left = current.trimEnd();
  const right = next.trimStart();
  if (!left) return right;
  if (!right) return left;
  if (/^[,.;:!?%\]})]/.test(right) || /[([{“‘]$/.test(left)) return `${left}${right}`;
  return `${left} ${right}`;
}

function findSafeBoundary(text: string, pattern: RegExp, minimum: number): number | null {
  pattern.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    const end = match.index + match[0].length;
    if (end < minimum) continue;
    const prefix = text.slice(0, end);
    if (isProtectedBoundary(prefix)) continue;
    return end;
  }
  return null;
}

function findStableWeakBoundary(text: string, minimum: number, lookahead: number): number | null {
  WEAK_BOUNDARY.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = WEAK_BOUNDARY.exec(text)) !== null) {
    const end = match.index + match[0].length;
    if (end < minimum || text.length - end < lookahead) continue;
    if (isProtectedBoundary(text.slice(0, end))) continue;
    return end;
  }
  return null;
}

function safeWhitespaceBoundary(text: string, limit: number, minimum: number): number | null {
  const bounded = text.slice(0, Math.max(minimum, limit));
  for (let index = bounded.length - 1; index >= minimum; index -= 1) {
    if (!/\s/.test(bounded[index])) continue;
    const prefix = bounded.slice(0, index);
    if (!isProtectedBoundary(prefix)) return index;
  }
  return null;
}

function isProtectedBoundary(prefix: string): boolean {
  const trimmed = prefix.trimEnd();
  return ABBREVIATION.test(trimmed)
    || DECIMAL_OR_VERSION.test(trimmed)
    || URL_TAIL.test(trimmed)
    || hasUnclosedPair(trimmed, '(', ')')
    || hasUnclosedPair(trimmed, '[', ']')
    || hasUnclosedPair(trimmed, '{', '}')
    || hasUnclosedPair(trimmed, '“', '”')
    || hasUnclosedPair(trimmed, '‘', '’')
    || hasOddUnescapedQuoteCount(trimmed, '"');
}

function hasUnclosedPair(text: string, open: string, close: string): boolean {
  return text.lastIndexOf(open) > text.lastIndexOf(close);
}

function hasOddUnescapedQuoteCount(text: string, quote: string): boolean {
  let count = 0;
  for (let index = 0; index < text.length; index += 1) {
    if (text[index] !== quote) continue;
    let backslashes = 0;
    for (let cursor = index - 1; cursor >= 0 && text[cursor] === '\\'; cursor -= 1) backslashes += 1;
    if (backslashes % 2 === 0) count += 1;
  }
  return count % 2 === 1;
}

function positiveInteger(value: number | undefined, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
    ? Math.round(value)
    : fallback;
}
