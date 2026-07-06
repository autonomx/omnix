import { Button } from '@mantine/core';
import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import type { ProviderFacadePayload } from '../../api/client';
import { FeatureValidationMessage } from '../shared/FeatureSubmitFeedback';
import {
  IMAGE_SIZE_PRESETS,
  imagePresetById,
  imageRequestDefaultValues,
  type ImageRequestDefaults,
  type ImageRequestFormValues,
  validateImageDimension,
} from './imageRequestModel';

interface ImageRequestFormProps {
  defaults: ImageRequestDefaults;
  providers: ProviderFacadePayload['providers'];
  pending: boolean;
  disabled?: boolean;
  disabledReason?: string;
  onSubmit: (values: ImageRequestFormValues) => void;
}

export function ImageRequestForm({ defaults, providers, pending, disabled, disabledReason, onSubmit }: ImageRequestFormProps) {
  const {
    register,
    handleSubmit,
    reset,
    setValue,
    formState: { errors, isDirty },
  } = useForm<ImageRequestFormValues>({ defaultValues: imageRequestDefaultValues(defaults) });

  useEffect(() => {
    if (!isDirty) reset(imageRequestDefaultValues(defaults));
  }, [defaults, isDirty, reset]);

  const presetRegistration = register('preset');

  return (
    <>
      <form className="feature-form" onSubmit={handleSubmit(onSubmit)}>
        <label>
          Provider
          <select {...register('providerId')}>
            <option value="">Default image provider</option>
            {providers.map((provider) => <option key={provider.id} value={provider.id}>{provider.label}</option>)}
          </select>
        </label>
        <label>
          Size preset
          <select
            {...presetRegistration}
            onChange={(event) => {
              void presetRegistration.onChange(event);
              const preset = imagePresetById(event.currentTarget.value);
              if (!preset) return;
              setValue('width', String(preset.width), { shouldDirty: true, shouldValidate: true });
              setValue('height', String(preset.height), { shouldDirty: true, shouldValidate: true });
            }}
          >
            <option value="custom">Custom</option>
            {IMAGE_SIZE_PRESETS.map((preset) => <option key={preset.id} value={preset.id}>{preset.label}</option>)}
          </select>
        </label>
        <label>
          Width
          <input type="number" min="128" max="4096" step="64" aria-invalid={Boolean(errors.width)} {...register('width', { validate: validateImageDimension })} />
        </label>
        <label>
          Height
          <input type="number" min="128" max="4096" step="64" aria-invalid={Boolean(errors.height)} {...register('height', { validate: validateImageDimension })} />
        </label>
        <label className="feature-form-wide">
          Prompt
          <textarea rows={5} aria-invalid={Boolean(errors.prompt)} {...register('prompt', { required: true })} />
        </label>
        <label className="feature-form-wide">
          Negative prompt
          <textarea rows={3} placeholder="Elements to avoid" {...register('negativePrompt')} />
        </label>
        <label className="feature-form-wide">
          Style
          <input placeholder="cinematic, watercolor, concept art" {...register('style')} />
        </label>
        <details className="feature-form-wide">
          <summary>Advanced controls</summary>
          <div className="feature-form" style={{ marginTop: '0.75rem' }}>
            <label>Seed<input type="number" min="0" {...register('seed', { min: 0 })} /></label>
            <label>Steps<input type="number" min="1" max="200" {...register('steps', { min: 1, max: 200 })} /></label>
            <label>Guidance scale<input type="number" min="0" max="100" step="0.1" {...register('guidanceScale', { min: 0, max: 100 })} /></label>
            <label><input type="checkbox" {...register('unloadAfterGeneration')} /> Unload model after generation</label>
            <label><input type="checkbox" {...register('noCache')} /> Ignore cached results</label>
          </div>
        </details>
        <Button className="feature-form-action" type="submit" disabled={pending || disabled} loading={pending} title={disabledReason}>
          {pending ? 'Queueing image...' : 'Generate image'}
        </Button>
      </form>
      <FeatureValidationMessage show={Boolean(errors.prompt)} message="Enter a prompt before generating an image." />
      <FeatureValidationMessage show={Boolean(errors.width || errors.height)} message="Use dimensions from 128 to 4096 in multiples of 64." />
      {disabledReason ? <div className="platform-empty" role="status">{disabledReason}</div> : null}
    </>
  );
}
