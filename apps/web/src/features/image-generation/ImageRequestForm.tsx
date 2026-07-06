import { Button } from '@mantine/core';
import type { ProviderFacadePayload } from '../../api/client';
import type { ImageRequestDefaults, ImageRequestFormValues } from './imageRequestModel';

interface ImageRequestFormProps {
  defaults: ImageRequestDefaults;
  providers: ProviderFacadePayload['providers'];
  pending: boolean;
  onSubmit: (values: ImageRequestFormValues) => void;
}

export function ImageRequestForm({ pending }: ImageRequestFormProps) {
  return <Button disabled={pending}>{pending ? 'Queueing image...' : 'Generate image'}</Button>;
}
