import { render, screen, waitFor } from '@testing-library/react';
import { useForm } from 'react-hook-form';
import { describe, expect, it, vi } from 'vitest';
import './live-voice-form-sync';

type FormValues = { content: string };

function ComposerHarness({ onSubmit }: { onSubmit: (values: FormValues) => void }) {
  const { register, handleSubmit } = useForm<FormValues>({ defaultValues: { content: '' } });

  return (
    <form className="assistant-composer" onSubmit={handleSubmit(onSubmit)}>
      <label className="assistant-message-input">
        <span>Message</span>
        <textarea aria-label="Message" {...register('content', { required: true })} />
      </label>
      <button type="submit">Send</button>
    </form>
  );
}

describe('live voice form sync', () => {
  it('submits a transcript written immediately before requestSubmit', async () => {
    const onSubmit = vi.fn();
    render(<ComposerHarness onSubmit={onSubmit} />);

    const textarea = screen.getByLabelText('Message') as HTMLTextAreaElement;
    const form = textarea.form;
    expect(form).not.toBeNull();

    textarea.value = "How's it going?";
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    form?.requestSubmit();

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(
        { content: "How's it going?" },
        expect.anything(),
      );
    });
  });
});
