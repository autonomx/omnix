import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { omnixTheme } from '../design/theme';
import { OmnixApp } from './OmnixApp';

function renderApp() {
  const queryClient = new QueryClient();

  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <QueryClientProvider client={queryClient}>
        <OmnixApp />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

describe('OmnixApp', () => {
  it('renders the shared app shell and all module entrypoints', async () => {
    renderApp();

    expect(await screen.findByRole('heading', { name: 'Omnix' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'RPG' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Chatbot' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Storyteller' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Podcast' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Voice / TTS' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Voice Cloning' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'STT' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Image Generation' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Providers' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Models' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Jobs / Runs' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Assets' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Reports' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Settings' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Diagnostics' })).toBeInTheDocument();
  });
});
