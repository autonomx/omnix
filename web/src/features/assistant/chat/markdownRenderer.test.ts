import { describe, expect, it } from 'vitest';
import { renderAssistantMessageHtml, renderMarkdownHtml, renderResearchReportHtml } from './markdownRenderer';

describe('assistant Markdown rendering', () => {
  it('renders report-friendly blocks and inline emphasis', () => {
    const html = renderMarkdownHtml(
      '# GameStop outlook\n\n**Recommendation:** Hold for now.\n\n- Avoid leverage\n- Stage entries\n\nSee [the filing](https://example.com/filing) [S1].',
    );

    expect(html).toContain('<h1>GameStop outlook</h1>');
    expect(html).toContain('<strong>Recommendation:</strong> Hold for now.');
    expect(html).toContain('<ul><li>Avoid leverage</li><li>Stage entries</li></ul>');
    expect(html).toContain('href="https://example.com/filing"');
    expect(html).toContain('assistant-research-citation');
  });

  it('escapes HTML and rejects unsafe links', () => {
    const html = renderMarkdownHtml('<script>alert(1)</script> [bad](javascript:alert(1))');

    expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;');
    expect(html).not.toContain('<script>');
    expect(html).not.toContain('href="javascript:');
  });

  it('turns retrieved source citations into safe clickable links', () => {
    const html = renderAssistantMessageHtml(
      'The current conditions are mild. [S1] [S2]',
      {
        context_sources: [
          { source_id: 'web_search', citation: 'S1', title: 'Weather source', url: 'https://example.com/weather' },
          { source_id: 'web_search', citation: 'S2', title: 'Unsafe source', url: 'javascript:alert(1)' },
        ],
      },
      'msg:weather',
    );

    expect(html).toContain('class="assistant-research-citation" href="https://example.com/weather"');
    expect(html).toContain('aria-label="Open source S1"');
    expect(html).toContain('<sup class="assistant-research-citation" title="Source citation">[S2]</sup>');
    expect(html).not.toContain('href="javascript:');
  });

  it('adds research metadata and preserves a five-page budget in the report header', () => {
    const html = renderResearchReportHtml('**Inference:** A volatile setup. [S1] [S2]', {
      research_mode: 'deep',
      research_status: 'partial',
      logical_queries: 1,
      extracted_pages: 0,
      research_budget: { max_sources: 5 },
      research_warnings: ['page_extraction_partial'],
    });

    expect(html).toContain('Deep research');
    expect(html).toContain('2 citations');
    expect(html).toContain('1 search');
    expect(html).toContain('0/5 pages');
    expect(html).toContain('Limited evidence');
    expect(html).toContain('<strong>Inference:</strong>');
    expect(html).toContain('data-omnix-research-report-download');
    expect(html).toContain('data-omnix-research-report-expand');
  });

  it('renders GFM tables with alignment, inline Markdown, escaped pipes and ragged rows', () => {
    const html = renderMarkdownHtml(
      'Prices:\n| Symbol | Close | Note |\n|:--|--:|:-:|\n| **AAPL** | 231 | a \\| b |\n| MSFT | 410 |\n| NVDA | 120 | x | extra |\n\nAfter.',
    );

    expect(html).toContain('<p>Prices:</p>');
    expect(html).toContain('<div class="assistant-markdown-table"><table><thead><tr><th data-align="left">Symbol</th><th data-align="right">Close</th><th data-align="center">Note</th></tr></thead>');
    expect(html).toContain('<td data-align="left"><strong>AAPL</strong></td>');
    expect(html).toContain('<td data-align="center">a | b</td>');
    expect(html).toContain('<tr><td data-align="left">MSFT</td><td data-align="right">410</td><td data-align="center"></td></tr>');
    expect(html).toContain('<tr><td data-align="left">NVDA</td><td data-align="right">120</td><td data-align="center">x</td></tr>');
    expect(html).not.toContain('extra');
    expect(html).toContain('<p>After.</p>');
  });

  it('renders a table inside a quote and keeps non-table pipe lines as text', () => {
    expect(renderMarkdownHtml('> | a | b |\n> |---|---|\n> | 1 | 2 |')).toBe(
      '<blockquote><div class="assistant-markdown-table"><table><thead><tr><th>a</th><th>b</th></tr></thead><tbody><tr><td>1</td><td>2</td></tr></tbody></table></div></blockquote>',
    );
    expect(renderMarkdownHtml('Use a | b for either.\nNot a table.')).toBe('<p>Use a | b for either.<br>Not a table.</p>');
    expect(renderMarkdownHtml('| a | b |\n|---|')).not.toContain('<table>');
  });

  it('renders task lists as read-only checkboxes', () => {
    const html = renderMarkdownHtml('- [x] Done\n- [ ] Todo `code`\n- plain');

    expect(html).toBe(
      '<ul class="contains-task-list"><li class="task-list-item"><input type="checkbox" class="task-list-item-checkbox" disabled checked> Done</li>'
      + '<li class="task-list-item"><input type="checkbox" class="task-list-item-checkbox" disabled> Todo <code>code</code></li><li>plain</li></ul>',
    );
    expect(renderMarkdownHtml('1. [x] ordered')).toBe('<ol><li>[x] ordered</li></ol>');
  });

  it('renders GitHub alerts as toned callouts, including nested lists', () => {
    const html = renderMarkdownHtml('> [!WARNING]\n> Check before trading:\n> - liquidity\n> - spread');

    expect(html).toBe(
      '<div class="assistant-markdown-alert assistant-markdown-alert-warning" role="note"><p class="assistant-markdown-alert-title">Warning</p>'
      + '<p>Check before trading:</p><ul><li>liquidity</li><li>spread</li></ul></div>',
    );
    for (const kind of ['NOTE', 'TIP', 'IMPORTANT', 'CAUTION']) {
      expect(renderMarkdownHtml(`> [!${kind}]\n> text`)).toContain(`assistant-markdown-alert-${kind.toLowerCase()}`);
    }
    expect(renderMarkdownHtml('> [!BOGUS]\n> text')).toContain('<blockquote>');
  });

  it('escapes HTML in tables, task lists and alerts', () => {
    const html = renderMarkdownHtml(
      '| <b>h</b> |\n|---|\n| <img src=x onerror=alert(1)> |\n\n- [ ] <script>x</script>\n\n> [!NOTE]\n> <iframe>',
    );

    expect(html).not.toMatch(/<(?:b|img|script|iframe)[\s>]/);
    expect(html).toContain('&lt;b&gt;h&lt;/b&gt;');
    expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;');
    expect(html).toContain('&lt;script&gt;x&lt;/script&gt;');
    expect(html).toContain('&lt;iframe&gt;');
  });

  it('creates a shared message wrapper for DOM-injected research replies', () => {
    const html = renderAssistantMessageHtml('# Result', { research_mode: 'deep' }, 'msg:1');

    expect(html).toContain('data-omnix-message-content="true"');
    expect(html).toContain('data-raw-content="# Result"');
    expect(html).toContain('assistant-research-report');
  });
});
