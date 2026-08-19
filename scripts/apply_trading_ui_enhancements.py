from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


root = Path(__file__).resolve().parents[1]
panel = root / "src/apps/web/src/features/trading/TradingStrategiesPanel.tsx"
workspace = root / "src/apps/web/src/features/trading/TradingWorkspace.tsx"

replace_once(
    panel,
    "import { tradingPaperApi } from './tradingPaperApi';\nimport { TRADING_STRATEGY_DEFINITIONS } from './tradingStrategyCatalog';\nimport { tradingStrategyApi } from './tradingStrategyApi';",
    "import { tradingPaperApi } from './tradingPaperApi';\nimport { TradingStrategyBacktest } from './TradingStrategyBacktest';\nimport { TradingStrategyExecutionCredentials } from './TradingStrategyExecutionCredentials';\nimport { TRADING_STRATEGY_DEFINITIONS } from './tradingStrategyCatalog';\nimport { tradingStrategyApi } from './tradingStrategyApi';",
)
replace_once(
    panel,
    "import './TradingStrategiesPanel.css';",
    "import './TradingStrategiesPanel.css';\nimport './TradingStrategyEnhancements.css';",
)
replace_once(
    panel,
    "  const discoverYahoo = async () => {",
    """  const deleteStrategy = async () => {
    if (!draft || !strategies.some((item) => item.strategy_id === draft.strategy_id)) {
      setNotice('Save the strategy before deleting it.');
      return;
    }
    if (!window.confirm(`Delete strategy ${draft.strategy_id}? Strategy events/runs are removed; immutable research universes remain available for audit/backtesting.`)) return;
    setStatus('saving');
    try {
      await tradingStrategyApi.delete(draft);
      setSelectedId('');
      setDraft(null);
      setEvents([]);
      setProtections([]);
      setUniverse(null);
      setNotice(`Deleted strategy ${draft.strategy_id}.`);
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
      setStatus('error');
    }
  };

  const discoverYahoo = async () => {""",
)
replace_once(
    panel,
    """                <button type=\"button\" onClick={() => void refresh()}>Refresh</button>
                <button type=\"button\" className=\"primary\" onClick={() => void save()} disabled={status === 'saving'}>{status === 'saving' ? 'Saving…' : 'Save strategy'}</button>""",
    """                <button type=\"button\" onClick={() => void refresh()}>Refresh</button>
                {strategies.some((item) => item.strategy_id === draft.strategy_id) ? <button type=\"button\" className=\"danger\" onClick={() => void deleteStrategy()} disabled={status === 'saving'}>Delete</button> : null}
                <button type=\"button\" className=\"primary\" onClick={() => void save()} disabled={status === 'saving'}>{status === 'saving' ? 'Saving…' : 'Save strategy'}</button>""",
)
replace_once(
    panel,
    """            {notice ? <div className=\"trading-strategy-notice\" role=\"status\">{notice}</div> : null}

            <section className=\"trading-strategy-overview\">""",
    """            {notice ? <div className=\"trading-strategy-notice\" role=\"status\">{notice}</div> : null}

            <TradingStrategyExecutionCredentials />

            <section className=\"trading-strategy-overview\">""",
)
replace_once(
    panel,
    """            <section className=\"trading-research-workbench\">""",
    """            {selected ? (
              <TradingStrategyBacktest strategy={selected} />
            ) : (
              <section className=\"strategy-range-backtest\"><header><div><strong>Backtest this strategy</strong><small>Save the strategy first so the backtest is pinned to a persisted configuration revision.</small></div></header></section>
            )}

            <section className=\"trading-research-workbench\">""",
)

replace_once(
    workspace,
    "import './TradingTypography.css';",
    "import './TradingTypography.css';\nimport './TradingToolFullscreen.css';",
)
replace_once(
    workspace,
    "  const [toolPanel, setToolPanel] = useState<ToolPanel | null>(null);",
    "  const [toolPanel, setToolPanel] = useState<ToolPanel | null>(null);\n  const [toolPanelFullscreen, setToolPanelFullscreen] = useState(false);",
)
replace_once(
    workspace,
    """  const toggleToolPanel = (panel: ToolPanel) => {
    setToolPanel((current) => current === panel ? null : panel);
  };

  const openPaperTrading = () => {
    setSidePanelTab('paper');
    setPanel('right', true);
    setToolPanel(null);
  };

  const createWorkspace = () => {""",
    """  const toggleToolPanel = (panel: ToolPanel) => {
    setToolPanelFullscreen(false);
    setToolPanel((current) => current === panel ? null : panel);
  };

  const openPaperTrading = () => {
    setSidePanelTab('paper');
    setPanel('right', true);
    setToolPanelFullscreen(false);
    setToolPanel(null);
  };

  useEffect(() => {
    if (!toolPanelFullscreen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setToolPanelFullscreen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [toolPanelFullscreen]);

  const createWorkspace = () => {""",
)
replace_once(
    workspace,
    """        <section className=\"trading-tool-drawer\" aria-label=\"Trading analysis tool\">
          <header>
            <strong>{toolPanel === 'scanner'
              ? 'Market scanner'
              : toolPanel === 'replay'
                ? 'Replay & backtest'
                : toolPanel === 'strategies'
                  ? 'Automated strategies'
                  : 'AI market research'}</strong>
            <button type=\"button\" onClick={() => setToolPanel(null)} aria-label=\"Close analysis tool\">×</button>
          </header>""",
    """        <section className={`trading-tool-drawer${toolPanelFullscreen ? ' is-fullscreen' : ''}`} aria-label=\"Trading analysis tool\">
          <header>
            <strong>{toolPanel === 'scanner'
              ? 'Market scanner'
              : toolPanel === 'replay'
                ? 'Replay & backtest'
                : toolPanel === 'strategies'
                  ? 'Automated strategies'
                  : 'AI market research'}</strong>
            <div className=\"trading-tool-drawer-actions\">
              <button type=\"button\" onClick={() => setToolPanelFullscreen((value) => !value)} aria-pressed={toolPanelFullscreen} aria-label={toolPanelFullscreen ? 'Restore analysis tool' : 'Fullscreen analysis tool'}>{toolPanelFullscreen ? 'Restore' : 'Fullscreen'}</button>
              <button type=\"button\" onClick={() => { setToolPanelFullscreen(false); setToolPanel(null); }} aria-label=\"Close analysis tool\">×</button>
            </div>
          </header>""",
)

print("Trading UI enhancements applied")
