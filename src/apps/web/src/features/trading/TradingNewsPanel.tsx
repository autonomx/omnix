export function TradingNewsPanel({ onOpenResearch }: { onOpenResearch: () => void }) {
  return (
    <section className="trading-news-panel" aria-label="Trading news">
      <header>
        <div>
          <strong>Market news</strong>
          <small>Licensed provider required</small>
        </div>
        <span className="trading-news-status">Not configured</span>
      </header>
      <div className="trading-news-empty">
        <span aria-hidden="true">N</span>
        <div>
          <strong>No licensed news feed is connected.</strong>
          <p>
            Omnix does not synthesize headlines or assume that market-data rights include news redistribution.
          </p>
        </div>
      </div>
      <button type="button" onClick={onOpenResearch}>
        Generate an AI market brief
      </button>
      <small>
        AI research is read-only and displays its provider, model, dataset fingerprint, and as-of time.
      </small>
    </section>
  );
}
