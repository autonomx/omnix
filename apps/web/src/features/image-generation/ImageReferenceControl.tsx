import { Button, Text } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { omnixApiClient, type AssetListResponse } from '../../api/client';
import './ImageReferenceControl.css';
import { imageAssetTitle, imageAssetUrl, type ImageAsset } from './imageWorkspaceModel';

export const IMAGE_REFERENCES_QUERY_KEY = ['image-generation', 'references'] as const;
const MAX_REFERENCE_IMAGES = 2;

interface ImageReferenceUploadResponse {
  ok: boolean;
  asset: ImageAsset;
}

interface ImageReferenceControlProps {
  selectedAssetIds: string[];
  onChange: (assetIds: string[]) => void;
}

async function uploadImageReference(file: File): Promise<ImageReferenceUploadResponse> {
  const response = await fetch(
    `/api/image-generation/references?filename=${encodeURIComponent(file.name || 'reference-image')}`,
    {
      method: 'POST',
      headers: { 'Content-Type': file.type || 'application/octet-stream' },
      body: file,
    },
  );
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Reference upload failed with status ${response.status}`);
  }
  return response.json() as Promise<ImageReferenceUploadResponse>;
}

export function ImageReferenceControl({ selectedAssetIds, onChange }: ImageReferenceControlProps) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [limitMessage, setLimitMessage] = useState('');
  const referenceQuery = useQuery({
    queryKey: IMAGE_REFERENCES_QUERY_KEY,
    queryFn: () => omnixApiClient.get<AssetListResponse>('/api/image-generation/references'),
  });
  const uploadMutation = useMutation({
    mutationFn: uploadImageReference,
    onSuccess: async ({ asset }) => {
      const next = [...selectedAssetIds.filter((id) => id !== asset.id), asset.id].slice(-MAX_REFERENCE_IMAGES);
      onChange(next);
      queryClient.setQueryData<AssetListResponse>(IMAGE_REFERENCES_QUERY_KEY, (current) => ({
        assets: [asset, ...(current?.assets ?? []).filter((item) => item.id !== asset.id)],
      }));
      await queryClient.invalidateQueries({ queryKey: IMAGE_REFERENCES_QUERY_KEY });
      if (fileInputRef.current) fileInputRef.current.value = '';
    },
  });

  const toggleReference = (assetId: string) => {
    setLimitMessage('');
    if (selectedAssetIds.includes(assetId)) {
      onChange(selectedAssetIds.filter((id) => id !== assetId));
      return;
    }
    if (selectedAssetIds.length >= MAX_REFERENCE_IMAGES) {
      setLimitMessage(`Use at most ${MAX_REFERENCE_IMAGES} reference images.`);
      return;
    }
    onChange([...selectedAssetIds, assetId]);
  };

  const chooseUpload = (file: File | undefined) => {
    setLimitMessage('');
    if (!file) return;
    if (selectedAssetIds.length >= MAX_REFERENCE_IMAGES) {
      setLimitMessage(`Remove a reference before uploading another. Maximum: ${MAX_REFERENCE_IMAGES}.`);
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }
    uploadMutation.mutate(file);
  };

  const assets = referenceQuery.data?.assets ?? [];
  const selected = new Set(selectedAssetIds);

  return (
    <fieldset className="image-reference-fieldset">
      <legend>
        Reference images <i title="Condition FLUX on up to two existing or uploaded images">ⓘ</i>
      </legend>
      <div className="image-reference-heading">
        <Text size="xs">
          Optional image-to-image guidance. Select or upload up to {MAX_REFERENCE_IMAGES}; describe what to preserve or change in the prompt.
        </Text>
        <Button
          loading={uploadMutation.isPending}
          onClick={() => fileInputRef.current?.click()}
          size="compact-xs"
          type="button"
          variant="light"
        >
          Upload reference
        </Button>
        <input
          ref={fileInputRef}
          className="visually-hidden"
          type="file"
          accept="image/png,image/jpeg,image/webp"
          aria-label="Upload reference image"
          onChange={(event) => chooseUpload(event.currentTarget.files?.[0])}
        />
      </div>

      {referenceQuery.isLoading ? <Text size="xs">Loading reference images…</Text> : null}
      {referenceQuery.isError ? <Text c="red" size="xs" role="alert">Reference images could not be loaded.</Text> : null}
      {uploadMutation.isError ? <Text c="red" size="xs" role="alert">Reference upload failed.</Text> : null}
      {limitMessage ? <Text c="yellow" size="xs" role="status">{limitMessage}</Text> : null}

      {assets.length ? (
        <div className="image-reference-grid" aria-label="Reference image choices">
          {assets.slice(0, 16).map((asset) => {
            const active = selected.has(asset.id);
            const blocked = !active && selectedAssetIds.length >= MAX_REFERENCE_IMAGES;
            return (
              <button
                aria-label={`${active ? 'Remove' : 'Use'} ${imageAssetTitle(asset)} as reference`}
                aria-pressed={active}
                className={active ? 'active' : ''}
                disabled={blocked}
                key={asset.id}
                onClick={() => toggleReference(asset.id)}
                type="button"
              >
                <img alt="" loading="lazy" src={imageAssetUrl(asset.id)} />
                <span title={imageAssetTitle(asset)}>{imageAssetTitle(asset)}</span>
                {active ? <b aria-hidden="true">✓</b> : null}
              </button>
            );
          })}
        </div>
      ) : !referenceQuery.isLoading ? (
        <Text size="xs">No prior images are available. Upload a PNG, JPEG, or WebP reference.</Text>
      ) : null}
      <Text className="image-reference-count" size="xs">{selectedAssetIds.length} / {MAX_REFERENCE_IMAGES} selected</Text>
    </fieldset>
  );
}
