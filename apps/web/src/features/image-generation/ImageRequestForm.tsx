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
  onSubmit: (values: ImageRequestFormValues) => void;
}

export function ImageRequestForm({ defaults, providers, pending, onSubmit }: ImageRequestFormProps) {
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
          Style
          <input placeholder="cinematic, watercolor, concept art" {...register('style')} />
        </label>
        <Button className="feature-form-action" type="submit" disabled={pending} loading={pending}>
          {pending ? 'Queueing image...' : 'Generate image'}
        </Button>
      </form>
      <FeatureValidationMessage show={Boolean(errors.prompt)} message="Enter a prompt before generating an image." />
      <FeatureValidationMessage show={Boolean(errors.width || errors.height)} message="Use dimensions from 128 to 4096 in multiples of 64." />
    </>
  );
}
