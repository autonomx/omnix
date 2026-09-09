import { readFileSync } from 'node:fs';
import { MantineProvider } from '@mantine/core';
import { cleanup, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  OmnixAssetCard,
  OmnixAudioControls,
  OmnixDiagnosticsView,
  OmnixProgressLog,
  OmnixTopBar,
  OmnixTranscriptView,
} from './primitives';
import { omnixTheme } from './theme';

const styles = readFileSync('src/styles.css', 'utf8');
const styleElement = document.createElement('style');
document.head.appendChild(styleElement);


function renderWithTheme(ui: React.ReactNode) {
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      {ui}
    </MantineProvider>,
  );
}

describe('design primitives', () => {
  it.each([
    ['dark', '#f4f7ff'],
    ['light', '#172033'],
  ])('keeps the Assistant header label readable in %s mode', (appearance, textColor) => {
    document.documentElement.dataset.omnixAppearance = appearance;
    styleElement.textContent = styles.replaceAll('var(--omnix-text)', textColor);
    renderWithTheme(<OmnixTopBar title="Chatbot" />);

    const assistantLabel = document.querySelector('.omnix-topbar-status span');
    expect(assistantLabel).toHaveTextContent('Assistant');
    expect(assistantLabel).toBeVisible();
    expect(styles).toContain('.omnix-topbar-status span { color: var(--omnix-text);');
    expect(getComputedStyle(assistantLabel as HTMLElement).color).toBe(appearance === 'dark' ? 'rgb(244, 247, 255)' : 'rgb(23, 32, 51)');

    cleanup();
    delete document.documentElement.dataset.omnixAppearance;
  });

  it('renders shared operational primitives', () => {
    renderWithTheme(
      <>
        <OmnixProgressLog value={50} logs={[{ level: 'info', message: 'Halfway' }]} />
        <OmnixTranscriptView messages={[{ role: 'assistant', content: 'Ready.' }]} />
        <OmnixAudioControls label="preview" />
        <OmnixAssetCard title="Image asset" metadata="image/png" />
        <OmnixDiagnosticsView rows={[{ label: 'Gateway', value: 'ready' }]} />
      </>,
    );

    expect(screen.getByLabelText('Progress')).toBeInTheDocument();
    expect(screen.getByText('Halfway')).toBeInTheDocument();
    expect(screen.getByText('Ready.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Play preview' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Image asset' })).toBeInTheDocument();
    expect(screen.getByText('Gateway')).toBeInTheDocument();
    expect(screen.getByText('ready')).toBeInTheDocument();
  });
});
