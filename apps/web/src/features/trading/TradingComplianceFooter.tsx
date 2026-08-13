import type { ProviderBinding, ProviderDescriptor } from './tradingTypes';
import './TradingCompliance.css';

function safeExternalReference(reference: string): string | null {
  try {
    const url = new URL(reference);
    return url.protocol === 'https:' ? url.toString() : null;
  } catch {
    return null;
  }
}

export function TradingComplianceFooter({
  provider,
  binding,
}: {
  provider: ProviderDescriptor | null;
  binding: ProviderBinding | null;
}) {
  const terms = provider ? safeExternalReference(provider.policy.terms_reference) : null;
  return (
    <footer className="trading-compliance-footer" aria-label="Trading attribution and data policy">
      <div>
        <strong>Research and paper simulation only</strong>
        <span>No live brokerage execution. Market-data rights remain provider-specific.</span>
      </div>
      <dl>
        <div><dt>Active feed</dt><dd>{binding ? `${binding.provider} · ${binding.feed_type}` : 'No feed selected'}</dd></div>
        <div><dt>Usage scope</dt><dd>{provider?.policy.usage_scope ?? binding?.usage_scope ?? 'not reported'}</dd></div>
        <div><dt>Redistribution</dt><dd>{provider ? (provider.policy.redistribution_allowed ? 'provider permits' : 'not permitted') : 'not reported'}</dd></div>
        <div><dt>Official API</dt><dd>{binding ? (binding.is_official_api ? 'yes' : 'no') : 'not reported'}</dd></div>
      </dl>
      <nav aria-label="Trading legal references">
        {terms ? <a href={terms} target="_blank" rel="noreferrer">Provider terms</a> : <span>Provider terms: {provider?.policy.terms_reference ?? 'not reported'}</span>}
        <a href="https://www.tradingview.com/lightweight-charts/" target="_blank" rel="noreferrer">
          Charts powered by TradingView Lightweight Charts™
        </a>
      </nav>
    </footer>
  );
}
