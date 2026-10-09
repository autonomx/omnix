import { useEffect, useState } from 'react';
import { CHART_LINK_GROUP_LABELS, CHART_LINK_GROUPS, type ChartLinkGroup } from './chartLinkGroups';
import { useTradingStore } from './tradingStore';
import './ChartLinkGroupButton.css';

/** The chart's colour link group (TVP-4.1): charts in a group share their symbol, across tabs. */
export function ChartLinkGroupButton({ chartId, group }: { chartId: string; group: ChartLinkGroup | undefined }) {
  const setChartLinkGroup = useTradingStore((state) => state.setChartLinkGroup);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    window.addEventListener('pointerdown', close);
    return () => window.removeEventListener('pointerdown', close);
  }, [open]);
  const choose = (next: ChartLinkGroup | null) => {
    setChartLinkGroup(chartId, next);
    setOpen(false);
  };
  const label = group ? `${CHART_LINK_GROUP_LABELS[group]} link group` : 'No link group';
  return (
    <span className="chart-link-group" onPointerDown={(event) => event.stopPropagation()}>
      <button
        type="button"
        className={`chart-link-group-button${group ? ` is-${group}` : ''}`}
        aria-label={`${label}: change`}
        aria-haspopup="menu"
        aria-expanded={open}
        title={group ? `${label}: charts in it share their symbol` : 'Link this chart to a colour group'}
        onClick={() => setOpen((value) => !value)}
      />
      {open ? (
        <span className="chart-link-group-menu" role="menu" aria-label="Link group">
          {CHART_LINK_GROUPS.map((item) => (
            <button key={item} type="button" role="menuitemradio" aria-checked={group === item} className={`is-${item}`} onClick={() => choose(item)}>
              <i aria-hidden="true" />{CHART_LINK_GROUP_LABELS[item]}
            </button>
          ))}
          <button type="button" role="menuitemradio" aria-checked={!group} onClick={() => choose(null)}>No link group</button>
        </span>
      ) : null}
    </span>
  );
}
