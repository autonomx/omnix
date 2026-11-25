import { useMutation, useQuery } from '@tanstack/react-query';
import { safeLink } from './aiResearchParts';
import type { FilingEntry, FilingSummaryResult } from './researchTypes';
import { tradingResearchApi } from './tradingResearchApi';
import './TradingAiResearch.css';

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

/** AI filing summaries: a US company's recent SEC reports, each summarized from its own text on request. */
export function TradingFilingsPanel({ instrumentId }: { instrumentId: string }) {
  const isStock = instrumentId.startsWith('equity:');
  const filings = useQuery({
    queryKey: ['trading', 'research', 'filings', instrumentId],
    queryFn: () => tradingResearchApi.filings(instrumentId),
    enabled: isStock,
    staleTime: 15 * 60_000,
    retry: false,
  });
  const summary = useMutation({ mutationFn: (accession: string) => tradingResearchApi.filingSummary(instrumentId, accession) });
  const summarizing = summary.isPending ? summary.variables : null;

  return (
    <section className="trading-ai-filings" aria-label="AI filing summaries">
      <header className="trading-ai-header">
        <div>
          <strong><span aria-hidden="true">✧</span> Filings</strong>
          <small>{filings.data ? `${filings.data.company} · SEC EDGAR` : 'Recent SEC reports, summarized on request'}</small>
        </div>
      </header>
      {!isStock ? <p className="trading-ai-status">Filing summaries are for US stocks.</p> : null}
      {isStock && filings.isPending ? <p className="trading-ai-status" role="status">Loading filings…</p> : null}
      {filings.isError ? <p className="trading-ai-error" role="alert">{errorText(filings.error, 'Filings are unavailable.')}</p> : null}
      {summary.data ? <FilingSummary result={summary.data} onClose={summary.reset} /> : null}
      {summary.isError ? <p className="trading-ai-error" role="alert">{errorText(summary.error, 'The summary failed.')}</p> : null}
      {filings.data && !filings.data.filings.length ? <p className="trading-ai-status">No recent reports on file.</p> : null}
      {filings.data?.filings.length ? (
        <ul className="trading-ai-filing-list">
          {filings.data.filings.map((filing) => (
            <FilingRow
              key={filing.accession}
              filing={filing}
              busy={summarizing === filing.accession}
              disabled={summary.isPending}
              onSummarize={() => summary.mutate(filing.accession)}
            />
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function FilingRow({ filing, busy, disabled, onSummarize }: { filing: FilingEntry; busy: boolean; disabled: boolean; onSummarize: () => void }) {
  const link = safeLink(filing.url);
  return (
    <li>
      <div>
        <strong>{filing.form}</strong>
        <small>{filing.filed}{filing.report_date ? ` · period ${filing.report_date}` : ''}</small>
        {filing.description ? <span>{filing.description}</span> : null}
        {filing.items.length ? <small>Items {filing.items.join(', ')}</small> : null}
      </div>
      <div className="trading-ai-filing-actions">
        <button type="button" disabled={disabled} aria-label={`Summarize ${filing.form} filed ${filing.filed}`} onClick={onSummarize}>
          {busy ? 'Reading…' : 'Summarize'}
        </button>
        {link ? <a href={link} target="_blank" rel="noreferrer noopener">SEC</a> : null}
      </div>
    </li>
  );
}

function FilingSummary({ result, onClose }: { result: FilingSummaryResult; onClose: () => void }) {
  const excerpt = result.characters_read < result.characters_total;
  return (
    <article className="trading-ai-filing-summary" aria-label="Filing summary">
      <header>
        <strong>{result.title}</strong>
        <button type="button" aria-label="Close summary" onClick={onClose}>×</button>
      </header>
      <small>{result.filing.form} · filed {result.filing.filed}</small>
      <p>{result.summary}</p>
      {result.highlights.length ? (
        <section aria-label="Highlights"><strong>Highlights</strong><ul>{result.highlights.map((item) => <li key={item}>{item}</li>)}</ul></section>
      ) : null}
      {result.risks.length ? (
        <section aria-label="Risks"><strong>Risks</strong><ul>{result.risks.map((item) => <li key={item}>{item}</li>)}</ul></section>
      ) : null}
      {result.figures.length ? (
        <dl className="trading-ai-figures">
          {result.figures.map((figure) => (
            <div key={figure.label}><dt>{figure.label}</dt><dd>{figure.value}</dd></div>
          ))}
        </dl>
      ) : null}
      <small className="trading-ai-meta">
        Read {result.documents.map((document) => document.name).join(', ')}
        {excerpt ? ` (an excerpt: ${result.characters_read.toLocaleString()} of ${result.characters_total.toLocaleString()} characters)` : ''}
        {' · '}{result.model}
      </small>
      <small className="trading-ai-disclaimer">{result.disclaimer} Figures are kept only when they appear in the filing's text.</small>
    </article>
  );
}
