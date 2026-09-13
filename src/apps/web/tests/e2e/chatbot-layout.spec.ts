import { expect, test, type Page } from '@playwright/test';

async function installChatbotMocks(page: Page): Promise<void> {
  await page.route('**/api/providers', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        providers: [{
          id: 'openai',
          label: 'OpenAI compatible',
          family: 'llm',
          source: 'settings',
          status: 'configured',
          capabilities: ['chat'],
        }],
        models: [{
          id: 'gpt-mini',
          label: 'GPT mini',
          provider_id: 'openai',
          location: 'remote',
          capabilities: ['chat'],
        }],
      }),
    });
  });
  await page.route('**/api/assets', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ assets: [] }),
    });
  });
  await page.route('**/api/chat/sessions', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ sessions: [] }),
    });
  });
}

async function minimizeBothPanels(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Minimize side panel' }).click();
  await page.getByRole('button', { name: 'Minimize assistant sidebar' }).click();
}

async function readRenderedLayout(page: Page): Promise<{
  columns: string;
  sideColumn: string;
  sideJustifySelf: string;
  sideWidth: string;
}> {
  return page.locator('.assistant-chat-layout').evaluate((layout) => {
    const sidePanel = layout.querySelector<HTMLElement>('.assistant-chat-side');

    if (!sidePanel) {
      throw new Error('Live side panel is missing');
    }

    const layoutStyle = getComputedStyle(layout);
    const sidePanelStyle = getComputedStyle(sidePanel);

    return {
      columns: layoutStyle.gridTemplateColumns,
      sideColumn: sidePanelStyle.gridColumn,
      sideJustifySelf: sidePanelStyle.justifySelf,
      sideWidth: sidePanelStyle.width,
    };
  });
}

test('preserves panel sizes across expanded, single-minimized, and both-minimized states', async ({ page }) => {
  await installChatbotMocks(page);

  for (const viewport of [
    { width: 1600, height: 900 },
    { width: 1500, height: 900 },
    { width: 1280, height: 900 },
    { width: 1180, height: 900 },
    { width: 1024, height: 900 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto('/chatbot');
    await page.evaluate(() => window.localStorage.clear());
    await page.reload();

    const layout = page.locator('.assistant-chat-layout');
    const leftSidebar = page.locator('.assistant-chat-sidebar');
    const sidePanel = page.locator('.assistant-chat-side');
    const expanded = await readRenderedLayout(page);
    const expandedTracks = expanded.columns.split(/\s+/);

    expect(leftSidebar).not.toHaveClass(/assistant-chat-sidebar-minimized/);
    expect(sidePanel).not.toHaveClass(/assistant-chat-side-minimized/);
    expect(expandedTracks[0], `expanded left track at ${viewport.width}px`).not.toBe('60px');
    expect(expandedTracks).toHaveLength(viewport.width > 1500 ? 3 : viewport.width > 1180 ? 2 : 1);

    await page.getByRole('button', { name: 'Minimize assistant sidebar' }).click();
    const leftOnly = await readRenderedLayout(page);
    const leftOnlyTracks = leftOnly.columns.split(/\s+/);

    expect(layout).toHaveClass(/assistant-chat-layout-sidebar-minimized/);
    expect(leftSidebar).toHaveClass(/assistant-chat-sidebar-minimized/);
    expect(leftOnlyTracks[0], `left-only minimized track at ${viewport.width}px`).toBe('60px');

    await page.getByRole('button', { name: 'Expand assistant sidebar' }).click();
    await page.getByRole('button', { name: 'Minimize side panel' }).click();
    const rightOnly = await readRenderedLayout(page);
    const rightOnlyTracks = rightOnly.columns.split(/\s+/);

    expect(layout).toHaveClass(/assistant-chat-layout-side-minimized/);
    expect(sidePanel).toHaveClass(/assistant-chat-side-minimized/);
    if (viewport.width > 1180) {
      expect(rightOnlyTracks.at(-1), `right-only minimized track at ${viewport.width}px`).toBe('60px');
    } else {
      expect(rightOnly.sideWidth, `right-only panel width at ${viewport.width}px`).toBe('60px');
    }

    await page.getByRole('button', { name: 'Minimize assistant sidebar' }).click();
    const bothMinimized = await readRenderedLayout(page);
    const bothMinimizedTracks = bothMinimized.columns.split(/\s+/);

    expect(layout).toHaveClass(/assistant-chat-layout-sidebar-minimized/);
    expect(layout).toHaveClass(/assistant-chat-layout-side-minimized/);
    expect(leftSidebar).toHaveClass(/assistant-chat-sidebar-minimized/);
    expect(sidePanel).toHaveClass(/assistant-chat-side-minimized/);
    expect(bothMinimizedTracks[0], `both-minimized left track at ${viewport.width}px`).toBe(leftOnlyTracks[0]);
    expect(bothMinimizedTracks[0], `both-minimized collapsed track at ${viewport.width}px`).toBe('60px');

    if (viewport.width <= 1180) {
      expect(bothMinimizedTracks).toHaveLength(2);
      expect(bothMinimized.sideColumn).toBe('1 / -1');
      expect(bothMinimized.sideJustifySelf).toBe('end');
      expect(bothMinimized.sideWidth).toBe('60px');
    } else {
      expect(bothMinimizedTracks.at(-1), `both-minimized right track at ${viewport.width}px`).toBe('60px');
      expect(bothMinimized.columns).toMatch(/^60px\s+.+\s+60px$/);
    }

    await page.getByRole('button', { name: 'Expand side panel' }).click();
    await page.getByRole('button', { name: 'Expand assistant sidebar' }).click();
    const finalClasses = await layout.evaluate((element) => Array.from(element.classList));
    expect(finalClasses).not.toContain('assistant-chat-layout-sidebar-minimized');
    expect(finalClasses).not.toContain('assistant-chat-layout-side-minimized');
  }
});
