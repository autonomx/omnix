import { useEffect, useMemo, useState } from 'react';
import { OMNIX_THEME_PRESETS, type OmnixThemeId } from '../../../../design/appearanceThemes';
import { ChatUiRenderer } from './ChatUiRenderer';
import { parseChatUi } from './schema';
import type { ChatUiInteraction } from './uiActions';
import '../ChatWorkspaceLayout.css';

type Fixture = { name: string; description?: string; content: string; expected: unknown };

// Dev only: the shared golden fixtures, read straight from the repository.
const fixtureModules = import.meta.glob('../../../../../../resources/chat/generative_ui/fixtures/*.json', { eager: true, import: 'default' });
const fixtures = Object.values(fixtureModules as Record<string, Fixture>).sort((a, b) => a.name.localeCompare(b.name));

const WIDTHS = [375, 1280] as const;

const inertInteraction: ChatUiInteraction = {
  active: true,
  submissions: {},
  choose: (text) => console.info('chat-ui gallery: choose', text),
  fillComposer: (text) => console.info('chat-ui gallery: fill composer', text),
};

/**
 * Visual QA for chat generative UI (GUI-2.5): every golden fixture in the chosen theme preset,
 * appearance and width. Served only by the development server at /dev/chat-ui-fixtures.
 */
export default function ChatUiFixtureGallery() {
  const [theme, setTheme] = useState<OmnixThemeId>('aurora');
  const [appearance, setAppearance] = useState<'dark' | 'light'>('dark');
  const [width, setWidth] = useState<(typeof WIDTHS)[number]>(1280);
  useEffect(() => {
    const root = document.documentElement;
    const previous = [root.getAttribute('data-omnix-theme'), root.getAttribute('data-omnix-appearance')] as const;
    root.setAttribute('data-omnix-theme', theme);
    root.setAttribute('data-omnix-appearance', appearance);
    return () => {
      if (previous[0] === null) root.removeAttribute('data-omnix-theme'); else root.setAttribute('data-omnix-theme', previous[0]);
      if (previous[1] === null) root.removeAttribute('data-omnix-appearance'); else root.setAttribute('data-omnix-appearance', previous[1]);
    };
  }, [theme, appearance]);
  const parsed = useMemo(() => fixtures.map((fixture) => ({ fixture, ui: parseChatUi({ ui: fixture.expected }, fixture.content) })), []);
  return (
    <main className="gui-gallery" style={{ background: 'var(--omnix-body-surface)', color: 'var(--omnix-text)', minHeight: '100vh', padding: '1rem' }}>
      <header style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'center', marginBottom: '1rem' }}>
        <h1 style={{ fontSize: '1.1rem', margin: 0 }}>Chat generative UI fixtures ({fixtures.length})</h1>
        <label>Theme <select value={theme} onChange={(event) => setTheme(event.target.value as OmnixThemeId)}>
          {OMNIX_THEME_PRESETS.map((preset) => <option key={preset.id} value={preset.id}>{preset.label}</option>)}
        </select></label>
        <label>Appearance <select value={appearance} onChange={(event) => setAppearance(event.target.value as 'dark' | 'light')}>
          <option value="dark">Dark</option><option value="light">Light</option>
        </select></label>
        <label>Width <select value={width} onChange={(event) => setWidth(Number(event.target.value) as (typeof WIDTHS)[number])}>
          {WIDTHS.map((value) => <option key={value} value={value}>{value}px</option>)}
        </select></label>
      </header>
      <div style={{ display: 'grid', gap: '1.25rem', maxWidth: `${width}px`, margin: '0 auto' }}>
        {parsed.map(({ fixture, ui }) => (
          <section key={fixture.name} aria-label={fixture.name}>
            <h2 style={{ fontSize: '0.85rem', margin: '0 0 0.35rem' }}>{fixture.name}</h2>
            {fixture.description ? <p style={{ fontSize: '0.75rem', margin: '0 0 0.5rem', color: 'var(--omnix-muted)' }}>{fixture.description}</p> : null}
            <article className="assistant-chat-message assistant">
              <div className="assistant-chat-bubble">
                {ui
                  ? <div className="assistant-message-content assistant-ui-reply"><ChatUiRenderer ui={ui} messageId={`fixture:${fixture.name}`} interaction={inertInteraction} /></div>
                  : <p>Payload did not parse.</p>}
              </div>
            </article>
          </section>
        ))}
      </div>
    </main>
  );
}
