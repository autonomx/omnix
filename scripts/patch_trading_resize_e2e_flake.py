from __future__ import annotations

from pathlib import Path

path = Path("src/apps/web/tests/e2e/trading-terminal.spec.ts")
source = path.read_text(encoding="utf-8")
old = '''  const resizeBox = await rsiTopResize.boundingBox();
  expect(resizeBox).not.toBeNull();
  if (resizeBox) {
    await page.mouse.move(resizeBox.x + resizeBox.width / 2, resizeBox.y + resizeBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(resizeBox.x + resizeBox.width / 2, resizeBox.y - 24, { steps: 10 });
    await expect(rsiTopResize).toHaveClass(/is-resizing/);
    await page.mouse.up();
  }
'''
new = '''  // Use Playwright's live locator actionability instead of a previously measured
  // 8px hit target. Indicator geometry can refresh between boundingBox() and a
  // raw mouse down, which made this drag intermittently miss the separator.
  await rsiTopResize.hover();
  await page.mouse.down();
  await expect(rsiTopResize).toHaveClass(/is-resizing/);
  const activeResizeBox = await rsiTopResize.boundingBox();
  expect(activeResizeBox).not.toBeNull();
  if (activeResizeBox) {
    await page.mouse.move(activeResizeBox.x + activeResizeBox.width / 2, activeResizeBox.y - 24, { steps: 10 });
  }
  await page.mouse.up();
'''
if old not in source:
    raise SystemExit("expected resize E2E block not found; refusing to patch")
path.write_text(source.replace(old, new, 1), encoding="utf-8")
