import { useEffect, useState } from 'react';
import { formatTradingTime, formatTradingTimezoneOffset, resolveTradingTimezone, TRADING_TIMEZONE_OPTIONS, TRADING_TIMEZONE_CHANGE_EVENT, writeTradingTimezoneId } from './tradingTime';
import { ranges } from './tradingChartPanelModel';
import type { TradingChartPanelModel } from './useTradingChartPanel';

/** The footer: replay controls, visible ranges, timezone, offset and clock. */
export function ChartPanelFooter({ ws }: { ws: TradingChartPanelModel }) {
  const {
    active, allBarsRef, applyCustomRange, chartId, chartQuery, customRangeEnd, customRangeError, customRangeOpen,
    customRangeRef, customRangeStart, drawings, exitReplay, openCustomRange, previousReplayBar, provenance,
    replayCurrentBar, replayCursorIndex, replayHasNextBar, replayMode, replayPlaying, replaySpeed, replayStartIndex,
    resetReplay, selectedRangeLabel, selectedTimezone, selectedTimezoneOption, setCustomRangeEnd, setCustomRangeOpen,
    setCustomRangeStart, setReplayCursorIndex, setReplayPlaying, setReplaySpeed, setTimezoneId, setTimezoneMenuOpen,
    showRange, streamStatus, timezoneId, timezoneMenuOpen, timezoneMenuRef,
  } = ws;
  return (
    <>
      <footer>
        {replayMode && active ? (
          <div className="trading-replay-toolbar" role="group" aria-label="Chart replay controls" onPointerDown={(event) => event.stopPropagation()}>
            <button type="button" onClick={exitReplay} aria-label="Exit replay mode" title="Exit replay mode">×</button>
            <button type="button" onClick={() => setReplayCursorIndex(null)} disabled={replayStartIndex === null} aria-label="Choose replay start" title="Choose replay start">Select bar</button>
            <button type="button" onClick={resetReplay} disabled={replayStartIndex === null} aria-label="Reset replay" title="Reset replay">↤</button>
            <button type="button" onClick={previousReplayBar} disabled={replayCursorIndex === null || replayCursorIndex <= replayStartIndex!} aria-label="Replay previous bar" title="Previous bar">|‹</button>
            <button type="button" className="trading-replay-play" onClick={() => setReplayPlaying((value) => !value)} disabled={replayStartIndex === null || !replayHasNextBar} aria-label={replayPlaying ? 'Pause replay' : 'Play replay'} title={replayPlaying ? 'Pause replay' : 'Play replay'}>{replayPlaying ? 'Ⅱ' : '▶'}</button>
            <button type="button" onClick={() => setReplayCursorIndex((current) => current === null || replayStartIndex === null ? current : Math.min(allBarsRef.current.length - 1, Math.max(replayStartIndex, current + 1)))} disabled={!replayHasNextBar} aria-label="Replay next bar" title="Replay next bar">›|</button>
            <select aria-label="Replay speed" value={replaySpeed} onChange={(event) => setReplaySpeed(event.target.value)}>
              {['0.5', '1', '2', '4', '8'].map((speed) => <option key={speed} value={speed}>{speed}×</option>)}
            </select>
            <span className="trading-replay-progress">{replayCurrentBar ? new Date(replayCurrentBar.end_time).toLocaleDateString() : 'Select a bar'} · {replayCursorIndex === null ? 0 : replayCursorIndex + 1}/{allBarsRef.current.length}</span>
          </div>
        ) : null}
        <nav aria-label={`${chartId} visible range`} onPointerDown={(event) => event.stopPropagation()}>
          {ranges.map((range) => (
            <button
              key={range.label}
              type="button"
              aria-pressed={selectedRangeLabel === range.label}
              aria-label={`${range.label}: ${range.tooltip}`}
              data-tooltip={range.tooltip}
              onClick={() => showRange(range.label, range.days, range.interval)}
            >
              {range.label}
            </button>
          ))}
          <div className="trading-custom-range" ref={customRangeRef}>
            <button
              type="button"
              className="trading-custom-range-trigger"
              aria-label="Select custom date range"
              aria-expanded={customRangeOpen}
              aria-pressed={selectedRangeLabel === 'Custom'}
              title="Custom date range"
              onClick={openCustomRange}
            >
              <svg aria-hidden="true" viewBox="0 0 16 16" focusable="false">
                <rect x="2.5" y="3.5" width="11" height="10" rx="1" />
                <path d="M5 2v3M11 2v3M2.5 6.5h11" />
              </svg>
            </button>
            {customRangeOpen ? (
              <form className="trading-custom-range-popover" onSubmit={(event) => { event.preventDefault(); applyCustomRange(); }}>
                <strong>Custom range</strong>
                <label>From<input type="date" value={customRangeStart} onChange={(event) => setCustomRangeStart(event.target.value)} /></label>
                <label>To<input type="date" value={customRangeEnd} onChange={(event) => setCustomRangeEnd(event.target.value)} /></label>
                {customRangeError ? <small role="alert">{customRangeError}</small> : null}
                <div>
                  <button type="button" onClick={() => setCustomRangeOpen(false)}>Cancel</button>
                  <button type="submit" className="primary">Apply</button>
                </div>
              </form>
            ) : null}
          </div>
        </nav>
        <div className="trading-chart-footer-meta">
          <div className="trading-timezone-control" ref={timezoneMenuRef}>
            <button
              type="button"
              className="trading-timezone-trigger"
              aria-label={`Chart timezone: ${selectedTimezoneOption.label}`}
              aria-haspopup="listbox"
              aria-expanded={timezoneMenuOpen}
              title={`Timezone: ${selectedTimezoneOption.label}`}
              onClick={() => { setTimezoneMenuOpen((current) => !current); setCustomRangeOpen(false); }}
            >
              <TradingClock timezone={selectedTimezone} />
            </button>
            {timezoneMenuOpen ? (
              <div className="trading-timezone-menu" role="listbox" aria-label="Chart timezone">
                {TRADING_TIMEZONE_OPTIONS.map((option) => {
                  const optionTimezone = resolveTradingTimezone(option.id, chartQuery.data?.instrument.exchange_timezone);
                  const offset = formatTradingTimezoneOffset(new Date(), optionTimezone);
                  return (
                    <button
                      key={option.id}
                      type="button"
                      role="option"
                      aria-selected={timezoneId === option.id}
                      onClick={() => {
                        setTimezoneId(option.id);
                        writeTradingTimezoneId(option.id);
                        window.dispatchEvent(new CustomEvent(TRADING_TIMEZONE_CHANGE_EVENT, { detail: option.id }));
                        setTimezoneMenuOpen(false);
                      }}
                    >
                      <span>{option.label}</span>
                      <small>{offset}</small>
                      {timezoneId === option.id ? <b aria-hidden="true">✓</b> : null}
                    </button>
                  );
                })}
              </div>
            ) : null}
          </div>
          <span>{streamStatus === 'live' ? 'live source' : provenance?.cached ? 'cached' : 'live source'}</span>
          <span>{drawings.status}</span>
        </div>
      </footer>
    </>
  );
}

/** The chart footer's clock; it re-renders itself each second, not the chart panel (WP-9.9). */
function TradingClock({ timezone }: { timezone: string }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1_000);
    return () => window.clearInterval(timer);
  }, []);
  return <>{`${formatTradingTime(now, timezone)} ${formatTradingTimezoneOffset(now, timezone)}`}</>;
}
