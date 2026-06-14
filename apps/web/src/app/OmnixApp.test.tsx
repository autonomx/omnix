import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { OmnixApp } from './OmnixApp';

function renderApp() {
  const queryClient = new QueryClient();

  return render(
    <QueryClientProvider client={queryClient}>
      <OmnixApp />
    </QueryClientProvider>,
  );
}

describe('OmnixApp', () => {
  it('renders the shared app shell and all module entrypoints', () => {
    renderApp();

    expect(screen.getByRole('heading', { name: 'Omnix' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'RPG' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Chatbot' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Storyteller' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Podcast' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Voice / TTS' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Voice Cloning' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'STT' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Image Generation' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Providers' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Jobs / Runs' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Assets' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Settings' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Diagnostics' })).toBeInTheDocument();
  });
});
