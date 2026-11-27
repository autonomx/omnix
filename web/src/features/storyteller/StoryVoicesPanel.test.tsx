import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { storyApiClient, type StoryProject, type StoryVoiceCast } from './api/storyClient';
import { StoryVoicesPanel } from './StoryVoicesPanel';

const project = { id: 'story-1', characters: [{ id: 'mara', name: 'Mara' }] } as unknown as StoryProject;

function castWith(maraVoice: string, chosenBy: string): StoryVoiceCast {
  return {
    project_id: 'story-1',
    cast: [
      { speaker_id: 'narrator', name: 'The narrator', voice_id: 'default', voice_revision: 'service', chosen_by: 'auto' },
      { speaker_id: 'mara', name: 'Mara', voice_id: maraVoice, voice_revision: 'r1', chosen_by: chosenBy },
    ],
    voices: [
      { voice_id: 'default', name: "The narrator's voice", description: 'a clear storyteller', castable: true },
      { voice_id: 'asian-male', name: 'Asian male', description: 'a calm man', castable: true },
      { voice_id: 'rudeous', name: 'rudeous', description: '', castable: false },
    ],
  };
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><StoryVoicesPanel project={project} /></QueryClientProvider>);
}

afterEach(() => vi.restoreAllMocks());

describe('StoryVoicesPanel', () => {
  it('offers the whole library, the castable voices apart, and keeps a library voice the writer picks', async () => {
    vi.spyOn(storyApiClient, 'voiceCast').mockResolvedValue(castWith('asian-male', 'auto'));
    const choose = vi.spyOn(storyApiClient, 'chooseVoice').mockResolvedValue(castWith('rudeous', 'writer'));
    renderPanel();

    const select = await screen.findByLabelText("Mara's voice");
    const groups = within(select).getAllByRole('group');
    expect(groups.map((group) => group.getAttribute('label'))).toEqual(['Cast automatically', 'Your library']);
    expect(within(groups[1]).getByRole('option', { name: 'rudeous' })).toBeInTheDocument();
    expect(screen.getAllByText('Matched to the part')).toHaveLength(2);
    expect(screen.getByText('a calm man')).toBeInTheDocument();

    fireEvent.change(select, { target: { value: 'rudeous' } });
    await waitFor(() => expect(choose).toHaveBeenCalledWith('story-1', 'mara', 'rudeous'));
    expect(await screen.findByText('Your choice')).toBeInTheDocument();
    expect(screen.getByLabelText("Mara's voice")).toHaveValue('rudeous');
  });

  it('shows a part no castable voice suits as not cast, so the first library voice can still be picked', async () => {
    vi.spyOn(storyApiClient, 'voiceCast').mockResolvedValue(castWith('', ''));
    const choose = vi.spyOn(storyApiClient, 'chooseVoice').mockResolvedValue(castWith('default', 'writer'));
    renderPanel();

    const select = await screen.findByLabelText("Mara's voice");
    expect(select).toHaveValue('');
    expect(within(select).getByRole('option', { name: 'The default voice (not cast)' })).toBeDisabled();
    expect(screen.getByText('Not cast')).toBeInTheDocument();

    fireEvent.change(select, { target: { value: 'default' } });
    await waitFor(() => expect(choose).toHaveBeenCalledWith('story-1', 'mara', 'default'));
  });
});
