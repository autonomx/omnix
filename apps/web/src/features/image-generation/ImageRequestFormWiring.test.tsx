import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { omnixTheme } from '../../design/theme';
import { ImageRequestForm } from './ImageRequestForm';

function renderForm(onSubmit: ReturnType<typeof vi.fn>) {
  return render(
    <MantineProvider theme={omnixTheme} defaultColorScheme="dark">
      <ImageRequestForm
        defaults={{ providerId: 'image:flux', width: 768, height: 768, unloadAfterGeneration: false }}
        providers={[{
          id: 'image:flux',
          label: 'Flux local',
          family: 'image',
          source: 'settings',
          status: 'configured',
          capabilities: ['image'],
        }]}
        pending={false}
        onSubmit={onSubmit}
      />
    </MantineProvider>,
  );
}

describe('ImageRequestForm wiring', () => {
  it('submits the visible provider, aspect ratio, style, quality, and advanced controls', async () => {
    const onSubmit = vi.fn();
    renderForm(onSubmit);

    expect(screen.getByLabelText('Provider')).toHaveValue('image:flux');
    expect(screen.getByLabelText('Style')).toHaveValue('photorealistic');
    expect(screen.getByLabelText('Steps')).toHaveValue(32);

    fireEvent.click(screen.getByRole('button', { name: 'Use 16:9 Widescreen' }));
    expect(screen.getByLabelText('Width')).toHaveValue(1024);
    expect(screen.getByLabelText('Height')).toHaveValue(576);

    fireEvent.click(screen.getByRole('button', { name: 'Set quality to 2 of 5' }));
    expect(screen.getByLabelText('Steps')).toHaveValue(18);
    expect(screen.getByText('18 steps')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Prompt'), { target: { value: 'A real generated scene' } });
    fireEvent.change(screen.getByLabelText('Negative prompt'), { target: { value: 'blurry' } });
    fireEvent.change(screen.getByLabelText('Guidance scale'), { target: { value: '4.5' } });
    fireEvent.click(screen.getByLabelText('Unload model after generation'));
    fireEvent.click(screen.getByLabelText('Ignore cached results'));
    fireEvent.click(screen.getByRole('button', { name: 'Generate image' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      providerId: 'image:flux',
      prompt: 'A real generated scene',
      negativePrompt: 'blurry',
      width: '1024',
      height: '576',
      style: 'photorealistic',
      steps: '18',
      guidanceScale: '4.5',
      unloadAfterGeneration: true,
      noCache: true,
    }));
  });

  it('wires dimension steppers and custom aspect selection', () => {
    const onSubmit = vi.fn();
    renderForm(onSubmit);

    fireEvent.click(screen.getByRole('button', { name: 'Increase width' }));
    expect(screen.getByLabelText('Width')).toHaveValue(832);
    expect(screen.getByRole('button', { name: 'Use custom aspect ratio' })).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(screen.getByRole('button', { name: 'Decrease height' }));
    expect(screen.getByLabelText('Height')).toHaveValue(704);
  });
});
