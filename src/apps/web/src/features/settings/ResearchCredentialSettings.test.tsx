import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { omnixApiClient } from '../../api/client';
import { ResearchCredentialSettings } from './ResearchCredentialSettings';

const credentialStatus = {
  providers: [
    {
      provider: 'brave' as const,
      configured: false,
      source: 'missing' as const,
      editable: true,
      key_suffix: null,
    },
    {
      provider: 'tavily' as const,
      configured: false,
      source: 'missing' as const,
      editable: true,
      key_suffix: null,
    },
  ],
  legacy_environment_key: false,
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe('ResearchCredentialSettings', () => {
  it('captures the API key before React clears the event currentTarget', async () => {
    vi.spyOn(omnixApiClient, 'get').mockResolvedValue(credentialStatus);
    const post = vi.spyOn(omnixApiClient, 'post').mockResolvedValue(credentialStatus);

    render(<ResearchCredentialSettings />);

    const [input] = await screen.findAllByPlaceholderText('Enter API key');
    fireEvent.change(input, { target: { value: 'brave-test-key' } });

    expect(input).toHaveValue('brave-test-key');
    fireEvent.click(screen.getAllByRole('button', { name: 'Save key' })[0]);

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith('/api/assistant/research/credentials', {
        provider: 'brave',
        api_key: 'brave-test-key',
      });
    });
  });
});
