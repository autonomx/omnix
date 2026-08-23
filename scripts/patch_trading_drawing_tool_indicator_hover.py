from __future__ import annotations

from pathlib import Path

path = Path("src/apps/web/src/features/trading/TradingChartPanel.tsx")
source = path.read_text(encoding="utf-8")
old = '''  const handleStagePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const targetAdapter = adapterRef.current;
    const target = event.target as Element;
    if (targetAdapter) {
      const bounds = event.currentTarget.getBoundingClientRect();
      const y = event.clientY - bounds.top;
      const hoveredPane = indicatorPaneGeometry.find((pane) => y >= pane.top && y <= pane.top + pane.height);
      const nextHoveredPane = hoveredPane ? hoveredPane.id as CoreIndicatorId : null;
      setHoveredIndicatorPane((current) => current === nextHoveredPane ? current : nextHoveredPane);
    } else {
      setHoveredIndicatorPane(null);
    }
'''
new = '''  const handleStagePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const targetAdapter = adapterRef.current;
    const target = event.target as Element;
    // Drawing and alert tools own the chart pointer. Do not let transient pane
    // hover chrome appear underneath that interaction and intercept placement.
    if (drawingTool !== 'cursor') {
      setHoveredIndicatorPane(null);
    } else if (targetAdapter) {
      const bounds = event.currentTarget.getBoundingClientRect();
      const y = event.clientY - bounds.top;
      const hoveredPane = indicatorPaneGeometry.find((pane) => y >= pane.top && y <= pane.top + pane.height);
      const nextHoveredPane = hoveredPane ? hoveredPane.id as CoreIndicatorId : null;
      setHoveredIndicatorPane((current) => current === nextHoveredPane ? current : nextHoveredPane);
    } else {
      setHoveredIndicatorPane(null);
    }
'''
if old not in source:
    raise SystemExit("expected stage pointer hover block not found; refusing to patch")
path.write_text(source.replace(old, new, 1), encoding="utf-8")
