import { useEffect, useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { HeadlineList, safeLink } from './aiResearchParts';
import type { TradingChartAdapter } from './chart/chartAdapter';
import type { TradingDrawing } from './drawings/drawingCommands';
import { formatSpan, formatVolume } from './drawings/tools/definitions/ranges';
import type { RangeResearchAction, RangeResearchRequest, RangeResearchResult } from './researchTypes';
import { tradingResearchApi } from './tradingResearchApi';
import './TradingAiRangePanel.css';

/** The presets TradingView's AI Range menu offers, then a free question. */
export const AI_RANGE_PRESETS: readonly { action: Exclude<RangeResearchAction, 'ask'>; label: string }[] = [
  { action: 'explain', label: 'Explain this price move' },
  { action: 'events', label: 'Find events behind this move' },
  { action: 'technicals', label: 'Analyze technicals in this area' },
];

const PANEL_WIDTH = 320;
const MARGIN = 8;
const MIN_HISTORY = 30;
const MAX_HISTORY = 5_000;
const MAX_QUESTION = 600;

export type AiRangeChart = {
  instrumentId: string;
  interval: string;
  /** The chart's bars request, repeated so the span is measured on the bars the person sees. */
  bindingId: string | null;
  historyLimit: number;
  extendedHours: boolean;
  symbol: string;
};

/** The span's two times, earliest first. */
export function aiRangeSpan(drawing: Pick<TradingDrawing, 'points'>): { start: string; end: string } | null {
  const [first, second] = drawing.points;
  if (!first || !second) return null;
  return Date.parse(first.time) <= Date.parse(second.time) ? { start: first.time, end: second.time } : { start: second.time, end: first.time };
}

export function aiRangeRequest(chart: AiRangeChart, span: { start: string; end: string }, action: RangeResearchAction, question?: string): RangeResearchRequest {
  return {
    instrument_id: chart.instrumentId,
    binding_id: chart.bindingId,
    interval: chart.interval,
    start: span.start,
    end: span.end,
    action,
    ...(action === 'ask' ? { question: question?.trim() ?? '' } : {}),
    history_limit: Math.min(MAX_HISTORY, Math.max(MIN_HISTORY, Math.round(chart.historyLimit))),
    alignment: 'clock',
    extended_hours: chart.extendedHours,
  };
}

/** Only web links open; anything else stays text. */
function formatNumber(value: string | null | undefined): string {
  const number = Number(value);
  if (value === null || value === undefined || !Number.isFinite(number)) return '–';
  const size = Math.abs(number);
  return number.toLocaleString('en-US', { maximumFractionDigits: size >= 100 ? 2 : size >= 1 ? 4 : 6 });
}

function formatPercent(value: string | null | undefined): string {
  const number = Number(value);
  if (value === null || value === undefined || !Number.isFinite(number)) return '–';
  return `${number > 0 ? '+' : ''}${number.toFixed(2)}%`;
}

const NEWS_NOTES: Partial<Record<RangeResearchResult['news_status'], string>> = {
  none: 'No headlines were found for this span.',
  unavailable: 'News was unavailable, so this answer uses price data only.',
};

function placement(adapter: TradingChartAdapter | null, drawing: TradingDrawing): { left: number; top: number } | null {
  if (!adapter) return null;
  const xs = drawing.points.slice(0, 2).map((point) => adapter.timeToCoordinate(point.time)).filter((x): x is number => x !== null);
  if (xs.length === 0) return null;
  const width = adapter.indicatorPlotWidth();
  const right = Math.max(...xs);
  const left = Math.min(...xs);
  const beside = right + MARGIN + PANEL_WIDTH <= width ? right + MARGIN : left - MARGIN - PANEL_WIDTH;
  return { left: Math.max(MARGIN, Math.min(beside, width - PANEL_WIDTH - MARGIN)), top: 36 };
}

/** The AI Range panel beside a selected AI range: presets, a question box, then the answer (research only). */
export function TradingAiRangePanel({ adapter, drawing, chart, onClose }: {
  adapter: TradingChartAdapter | null;
  drawing: TradingDrawing;
  chart: AiRangeChart;
  onClose: () => void;
}) {
  const [position, setPosition] = useState(() => placement(adapter, drawing));
  const [question, setQuestion] = useState('');
  const research = useMutation({ mutationFn: tradingResearchApi.range });
  const span = aiRangeSpan(drawing);
  const spanKey = span ? `${span.start}|${span.end}|${chart.instrumentId}|${chart.interval}` : '';
  const asked = research.variables;
  // An answer belongs to the span it was asked about; moving the range clears it.
  const answerFits = asked !== undefined && `${asked.start}|${asked.end}|${asked.instrument_id}|${asked.interval}` === spanKey;
  const result = answerFits ? research.data : undefined;
  const error = answerFits && research.error ? research.error.message : null;
  const pending = answerFits && research.isPending;

  useEffect(() => {
    if (!adapter) return undefined;
    const update = () => setPosition(placement(adapter, drawing));
    const frame = window.requestAnimationFrame(update);
    const unsubscribe = adapter.onViewportChange(update);
    return () => {
      window.cancelAnimationFrame(frame);
      unsubscribe();
    };
  }, [adapter, drawing]);

  if (!span) return null;
  const ask = (action: RangeResearchAction, text?: string) => research.mutate(aiRangeRequest(chart, span, action, text));
  const submitQuestion = (event: FormEvent) => {
    event.preventDefault();
    if (question.trim()) ask('ask', question);
  };

  return (
    <section
      className="trading-ai-range-panel"
      role="dialog"
      aria-label="AI range"
      style={position ? { left: position.left, top: position.top, width: PANEL_WIDTH } : { right: MARGIN, top: 36, width: PANEL_WIDTH }}
      onPointerDown={(event) => event.stopPropagation()}
      onWheel={(event) => event.stopPropagation()}
    >
      <header>
        <strong><span aria-hidden="true">✧</span> AI range</strong>
        <span className="trading-ai-range-span">{chart.symbol} · {formatSpan(Date.parse(span.end) - Date.parse(span.start))}</span>
        <button type="button" aria-label="Close AI range" title="Close" onClick={onClose}>×</button>
      </header>
      <div className="trading-ai-range-actions" role="group" aria-label="AI range questions">
        {AI_RANGE_PRESETS.map((preset) => (
          <button key={preset.action} type="button" disabled={pending} aria-pressed={asked?.action === preset.action && answerFits} onClick={() => ask(preset.action)}>
            {preset.label}
          </button>
        ))}
        <form onSubmit={submitQuestion}>
          <input
            aria-label="Ask about this range"
            placeholder="Ask about this range"
            value={question}
            maxLength={MAX_QUESTION}
            disabled={pending}
            onChange={(event) => setQuestion(event.target.value)}
          />
          <button type="submit" aria-label="Send question" disabled={pending || !question.trim()}>↑</button>
        </form>
      </div>
      {pending ? <p className="trading-ai-range-status" role="status">Researching this range…</p> : null}
      {error ? <p className="trading-ai-range-error" role="alert">{error}</p> : null}
      {result ? <AiRangeAnswer result={result} /> : null}
    </section>
  );
}

function AiRangeAnswer({ result }: { result: RangeResearchResult }) {
  const { facts } = result;
  const note = NEWS_NOTES[result.news_status];
  return (
    <article className="trading-ai-range-answer" aria-label="AI range answer">
      <h3>{result.title}</h3>
      <p>{result.summary}</p>
      {result.points.length ? <ul>{result.points.map((point) => <li key={point}>{point}</li>)}</ul> : null}
      {result.headlines.length ? (
        <section aria-label="Cited headlines">
          <h4>Headlines</h4>
          <HeadlineList headlines={result.headlines} className="trading-ai-range-sources" />
        </section>
      ) : null}
      {result.events.length ? (
        <section aria-label="Company events">
          <h4>Events</h4>
          <ul className="trading-ai-range-sources">
            {result.events.map((item) => {
              const link = safeLink(item.link);
              const label = [item.kind.replaceAll('_', ' '), item.fiscal_period].filter(Boolean).join(' ');
              return (
                <li key={`${item.kind}-${item.date}`}>
                  {link ? <a href={link} target="_blank" rel="noreferrer noopener">{label}</a> : <span>{label}</span>}
                  <small>{[item.date, item.timing].filter(Boolean).join(' · ')}</small>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
      {note ? <p className="trading-ai-range-note">{note}</p> : null}
      <dl className="trading-ai-range-facts" aria-label="Measured by Omnix">
        <div><dt>Change</dt><dd>{formatPercent(facts.change_percent)}</dd></div>
        <div><dt>High</dt><dd>{formatNumber(facts.high)}</dd></div>
        <div><dt>Low</dt><dd>{formatNumber(facts.low)}</dd></div>
        <div><dt>Bars</dt><dd>{facts.bars.toLocaleString('en-US')}</dd></div>
        <div><dt>Volume</dt><dd>{formatVolume(Number(facts.volume))}{facts.volume_vs_prior ? ` (${formatNumber(facts.volume_vs_prior)}× prior)` : ''}</dd></div>
        {facts.rsi_14_end ? <div><dt>RSI 14</dt><dd>{formatNumber(facts.rsi_14_end)}</dd></div> : null}
      </dl>
      <small className="trading-ai-range-disclaimer">{result.disclaimer} · {result.model}</small>
    </article>
  );
}
