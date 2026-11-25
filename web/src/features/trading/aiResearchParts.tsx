import type { RangeHeadline } from './researchTypes';

/** A link Omnix can vouch for: http(s) only; anything else stays text. */
export function safeLink(url: string | null | undefined): string | null {
  return url && /^https?:\/\//i.test(url) ? url : null;
}

export function formatWhen(value: string): string {
  const time = new Date(value);
  return Number.isNaN(time.getTime()) ? value : time.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

/** Headlines as Omnix recorded them (never text a model wrote), linked when their URL is safe. */
export function HeadlineList({ headlines, className }: { headlines: readonly RangeHeadline[]; className: string }) {
  return (
    <ul className={className}>
      {headlines.map((headline) => {
        const link = safeLink(headline.url);
        return (
          <li key={headline.id}>
            {link ? <a href={link} target="_blank" rel="noreferrer noopener">{headline.headline}</a> : <span>{headline.headline}</span>}
            <small>{[headline.source, formatWhen(headline.created_at)].filter(Boolean).join(' · ')}</small>
          </li>
        );
      })}
    </ul>
  );
}
