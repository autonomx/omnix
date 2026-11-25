import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { HeadlineList } from './aiResearchParts';
import type { NewsDigestRequest } from './researchTypes';
import { tradingResearchApi } from './tradingResearchApi';
import './TradingAiResearch.css';

type DigestWindow = NonNullable<NewsDigestRequest['window']>;

const WINDOWS: Array<{ id: DigestWindow; label: string }> = [
  { id: '24h', label: 'Last 24 hours' },
  { id: '3d', label: 'Last 3 days' },
  { id: '7d', label: 'Last 7 days' },
];

/** AI news digest: the symbol's recent headlines, grouped into themes, on request. */
export function TradingNewsDigest({ instrumentId }: { instrumentId: string }) {
  const [span, setSpan] = useState<DigestWindow>('3d');
  const digest = useMutation({ mutationFn: (request: NewsDigestRequest) => tradingResearchApi.newsDigest(request) });
  const result = digest.data;

  return (
    <section className="trading-ai-digest" aria-label="AI news digest">
      <header className="trading-ai-header">
        <div>
          <strong><span aria-hidden="true">✧</span> News digest</strong>
          <small>Recent headlines for this symbol, summarized by theme</small>
        </div>
      </header>
      <div className="trading-ai-digest-controls">
        <select aria-label="Digest window" value={span} onChange={(event) => setSpan(event.target.value as DigestWindow)}>
          {WINDOWS.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
        </select>
        <button type="button" disabled={digest.isPending} onClick={() => digest.mutate({ instrument_id: instrumentId, window: span })}>
          {digest.isPending ? 'Summarizing…' : 'Summarize headlines'}
        </button>
      </div>
      {digest.isError ? <p className="trading-ai-error" role="alert">{digest.error instanceof Error ? digest.error.message : 'The digest failed.'}</p> : null}
      {result && result.news_status !== 'ok' ? (
        <p className="trading-ai-status">{result.news_status === 'unavailable' ? 'News is unavailable right now.' : result.summary}</p>
      ) : null}
      {result && result.news_status === 'ok' ? (
        <article aria-label="Digest">
          <header>
            <strong>{result.title}</strong>
            {result.tone ? <span className="trading-ai-tone" data-tone={result.tone}>{result.tone}</span> : null}
          </header>
          <p>{result.summary}</p>
          {result.themes.map((theme) => (
            <section key={theme.title} className="trading-ai-theme" aria-label={theme.title}>
              <strong>{theme.title}</strong>
              <p>{theme.summary}</p>
              {theme.headlines.length ? <HeadlineList headlines={theme.headlines} className="trading-ai-sources" /> : null}
            </section>
          ))}
          <small className="trading-ai-meta">{result.headlines_considered} headlines · {result.model}</small>
          <small className="trading-ai-disclaimer">{result.disclaimer} Tone describes the headlines, not a forecast.</small>
        </article>
      ) : null}
    </section>
  );
}
