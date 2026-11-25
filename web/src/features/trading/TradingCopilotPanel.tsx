import { useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { HeadlineList } from './aiResearchParts';
import { applyCopilotAction, type CopilotChartControls } from './copilotActions';
import type { CopilotAction, CopilotMessage, CopilotRequest, CopilotResult } from './researchTypes';
import { tradingResearchApi } from './tradingResearchApi';
import './TradingAiResearch.css';

/** Questions the empty chat offers (TradingView's Copilot starts the same way). */
export const COPILOT_SUGGESTIONS = [
  'Where are support and resistance?',
  'Summarize the trend on this chart.',
  'What moved price recently?',
  'Which indicators would help read this chart?',
] as const;

/** The conversation the server reads: at most 16 messages, the newest last. */
const MAX_SENT = 16;

type Turn = { message: CopilotMessage; result?: CopilotResult };

export type CopilotChart = Omit<CopilotChartControls, 'addDrawing'> & {
  bindingId: string | null;
  interval: string;
  supportedIntervals: readonly string[];
};

export function copilotRequest(chart: CopilotChart, messages: readonly CopilotMessage[]): CopilotRequest {
  return {
    instrument_id: chart.instrumentId,
    binding_id: chart.bindingId,
    interval: chart.interval,
    messages: messages.slice(-MAX_SENT),
    indicators: chart.indicators.filter((indicator) => indicator.enabled).map((indicator) => ({ id: indicator.id, period: indicator.period })),
    supported_intervals: [...chart.supportedIntervals],
  };
}

export function TradingCopilotPanel({ chart, addDrawing }: { chart: CopilotChart; addDrawing: CopilotChartControls['addDrawing'] }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState('');
  const [applied, setApplied] = useState<ReadonlySet<string>>(new Set());
  const copilot = useMutation({ mutationFn: (request: CopilotRequest) => tradingResearchApi.copilot(request) });

  const ask = (text: string) => {
    const content = text.trim();
    if (!content || copilot.isPending) return;
    const asked: Turn[] = [...turns, { message: { role: 'user', content } }];
    setTurns(asked);
    setDraft('');
    copilot.mutate(copilotRequest(chart, asked.map((turn) => turn.message)), {
      onSuccess: (result) => setTurns([...asked, { message: { role: 'assistant', content: result.reply }, result }]),
    });
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    ask(draft);
  };
  const apply = (turnIndex: number, action: CopilotAction, result: CopilotResult) => {
    if (applyCopilotAction(action, { ...chart, addDrawing }, Number(result.facts.close))) {
      setApplied((current) => new Set(current).add(`${turnIndex}:${action.id}`));
    }
  };
  const reset = () => {
    setTurns([]);
    setApplied(new Set());
    copilot.reset();
  };

  return (
    <section className="trading-ai-copilot" aria-label="Chart Copilot">
      <header className="trading-ai-header">
        <div>
          <strong><span aria-hidden="true">✧</span> Copilot</strong>
          <small>Reads this chart and proposes changes you choose to apply. It never trades.</small>
        </div>
        {turns.length ? <button type="button" onClick={reset}>New chat</button> : null}
      </header>
      <ol className="trading-ai-copilot-log" aria-live="polite">
        {turns.length ? null : (
          <li className="trading-ai-copilot-suggestions">
            {COPILOT_SUGGESTIONS.map((suggestion) => (
              <button key={suggestion} type="button" onClick={() => ask(suggestion)}>{suggestion}</button>
            ))}
          </li>
        )}
        {turns.map((turn, index) => (
          <li key={index} className={turn.message.role === 'user' ? 'is-user' : 'is-assistant'}>
            {turn.result ? <CopilotAnswer result={turn.result} isApplied={(action) => applied.has(`${index}:${action.id}`)} onApply={(action) => apply(index, action, turn.result!)} /> : <p>{turn.message.content}</p>}
          </li>
        ))}
      </ol>
      {copilot.isPending ? <p className="trading-ai-status" role="status">Reading the chart…</p> : null}
      {copilot.isError ? <p className="trading-ai-error" role="alert">{copilot.error instanceof Error ? copilot.error.message : 'Copilot failed.'}</p> : null}
      <form className="trading-ai-copilot-form" onSubmit={submit}>
        <input aria-label="Ask Copilot" value={draft} maxLength={2000} placeholder="Ask about this chart" onChange={(event) => setDraft(event.target.value)} />
        <button type="submit" disabled={!draft.trim() || copilot.isPending}>Send</button>
      </form>
      <small className="trading-ai-disclaimer">Research only. Not financial advice. Copilot cannot place orders, set alerts or change positions.</small>
    </section>
  );
}

function CopilotAnswer({ result, isApplied, onApply }: { result: CopilotResult; isApplied: (action: CopilotAction) => boolean; onApply: (action: CopilotAction) => void }) {
  return (
    <article aria-label="Copilot answer">
      <p>{result.reply}</p>
      {result.points.length ? <ul>{result.points.map((point) => <li key={point}>{point}</li>)}</ul> : null}
      {result.actions.length ? (
        <div className="trading-ai-copilot-actions" role="group" aria-label="Proposed chart changes">
          {result.actions.map((action) => {
            const done = isApplied(action);
            return (
              <button key={action.id} type="button" disabled={done} onClick={() => onApply(action)}>
                {done ? '✓ ' : '+ '}{action.label}
              </button>
            );
          })}
        </div>
      ) : null}
      {result.headlines.length ? <HeadlineList headlines={result.headlines} className="trading-ai-sources" /> : null}
      <small className="trading-ai-meta">{result.model}</small>
    </article>
  );
}
