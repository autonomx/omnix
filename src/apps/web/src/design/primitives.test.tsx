import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  OmnixAssetCard,
  OmnixAudioControls,
  OmnixDiagnosticsView,
  OmnixProgressLog,
  OmnixTranscriptView,
} from './primitives';
import { omnixTheme } from './theme';

function renderWithTheme(ui: React.ReactNode) {
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      {ui}
    </MantineProvider>,
  );
}

describe('design primitives', () => {
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
