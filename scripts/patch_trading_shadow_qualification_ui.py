from __future__ import annotations

"""One-shot guarded cleanup for Trading shadow qualification UI/E2E expectations."""

from pathlib import Path


E2E = Path("src/apps/web/tests/e2e/trading-terminal.spec.ts")
PANEL = Path("src/apps/web/src/features/trading/TradingStrategiesPanel.tsx")


E2E_DIALOG_OLD = """  await page.getByRole('button', { name: 'Place price alert' }).click();\n  await overlay.click({ position: { x: 180, y: 100 } });\n  await expect(page.getByRole('dialog', { name: /Create alert on BTCUSDT/ })).toBeVisible();\n  await expect(page.getByRole('combobox', { name: 'Alert trigger' })).toHaveValue('every_time');\n  await expect(page.getByRole('checkbox', { name: 'App' })).toBeChecked();\n  await page.getByRole('textbox', { name: 'Alert message' }).fill('BTC alert');\n  await page.getByRole('dialog', { name: /Create alert on BTCUSDT/ }).getByRole('button', { name: 'Create alert' }).click();\n"""
E2E_DIALOG_NEW = """  // Changing Chart 2 to ETH makes Chart 2 active by design. Exercise the\n  // alert tool against that actual active-chart contract instead of assuming\n  // the workspace silently switches back to BTC.\n  await page.getByRole('button', { name: 'Place price alert' }).click();\n  await overlay.click({ position: { x: 180, y: 100 } });\n  await expect(page.getByRole('dialog', { name: /Create alert on ETHUSDT/ })).toBeVisible();\n  await expect(page.getByRole('combobox', { name: 'Alert trigger' })).toHaveValue('every_time');\n  await expect(page.getByRole('checkbox', { name: 'App' })).toBeChecked();\n  await page.getByRole('textbox', { name: 'Alert message' }).fill('ETH alert');\n  await page.getByRole('dialog', { name: /Create alert on ETHUSDT/ }).getByRole('button', { name: 'Create alert' }).click();\n"""

E2E_MESSAGE_OLD = """  expect((state.alerts[0].parameters as Record<string, unknown>).message).toBe('BTC alert');\n  await expect(page.locator('.trading-alert-price-label')).toHaveCount(3);\n  await expect(page.locator('.trading-chart-panel').filter({ has: page.locator('.trading-alert-price-label') })).toHaveCount(3);\n"""
E2E_MESSAGE_NEW = """  expect((state.alerts[0].parameters as Record<string, unknown>).message).toBe('ETH alert');\n  // Only Chart 2 is ETH, so the ETH alert belongs on exactly one chart.\n  await expect(page.locator('.trading-alert-price-label')).toHaveCount(1);\n  await expect(page.locator('.trading-chart-panel').filter({ has: page.locator('.trading-alert-price-label') })).toHaveCount(1);\n"""

E2E_CONTEXT_OLD = """  await expect(chartMenu.getByRole('menuitem', { name: /Add alert on BTCUSDT/ })).toBeVisible();\n"""
E2E_CONTEXT_NEW = """  await expect(chartMenu.getByRole('menuitem', { name: /Add alert on ETHUSDT/ })).toBeVisible();\n"""

LOAD_OLD = """    setDraft({\n      ...draft,\n      strategy_version: '2.0.0',\n      mode: 'shadow',\n      config,\n      risk: { ...draft.risk, entry_start_et: '09:35:00', last_entry_et: '11:30:00' },\n    });\n"""
LOAD_NEW = """    setDraft({\n      ...draft,\n      strategy_version: '2.0.0',\n      mode: 'shadow',\n      active_universe_id: null,\n      config,\n      risk: { ...draft.risk, entry_start_et: '09:35:00', last_entry_et: '11:30:00' },\n    });\n"""

NOTICE_OLD = """    setNotice('Loaded the frozen V11 / strategy 2.0 profile in SHADOW mode: 1m L1→B1→higher-L2 structure, base ≥4m, L2 resolution ≤8m, 1.5R target, +0.75R→+0.25R causal protection, 60m max hold. Historical evidence is reconstructed and the external block had only two signals, so prospective shadow evidence remains required.');\n"""
NOTICE_NEW = """    setNotice('Loaded the frozen V11 / strategy 2.0 profile in SHADOW mode and cleared any selected universe so qualification uses the strategy-owned raw morning archive. Structure: 1m L1→B1→higher-L2, base ≥4m, L2 resolution ≤8m, 1.5R target, +0.75R→+0.25R causal protection, 60m max hold. Evidence is mixed: the 58-session revealed sample was positive, the April/May frozen block produced only two positive trades, and the older March/April stress block produced 5 trades at -0.546R expectancy. Keep 2.0 in prospective SHADOW until captured live evidence is reviewed; do not promote from historical reconstruction alone.');\n"""


def replace_exact(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    e2e = E2E.read_text(encoding="utf-8")
    e2e = replace_exact(e2e, E2E_DIALOG_OLD, E2E_DIALOG_NEW, "active ETH alert dialog")
    e2e = replace_exact(e2e, E2E_MESSAGE_OLD, E2E_MESSAGE_NEW, "ETH alert overlay expectation")
    e2e = replace_exact(e2e, E2E_CONTEXT_OLD, E2E_CONTEXT_NEW, "active ETH context menu")
    E2E.write_text(e2e, encoding="utf-8")

    panel = PANEL.read_text(encoding="utf-8")
    panel = replace_exact(panel, LOAD_OLD, LOAD_NEW, "V2 raw archive preset")
    panel = replace_exact(panel, NOTICE_OLD, NOTICE_NEW, "V2 shadow notice")
    PANEL.write_text(panel, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
