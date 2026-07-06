import { Button, Group, Text, Title } from '@mantine/core';
import { OmnixStatusPill } from '../../design/primitives';
import {
  formatCreatedAt,
  imageAssetMetadata,
  imageAssetTitle,
  imageAssetUrl,
  type ImageAsset,
} from './imageWorkspaceModel';

export function ImageLatestResult({ asset }: { asset?: ImageAsset }) {
  const title = asset ? imageAssetTitle(asset) : '';

  return (
    <section
      className="feature-panel feature-panel-wide"
      aria-atomic="true"
      aria-labelledby="latest-image-result-title"
      aria-live="polite"
    >
      <Group justify="space-between" align="start">
        <div>
          <Title id="latest-image-result-title" order={4}>Latest result</Title>
          <Text size="sm">Your most recently generated or selected image appears here.</Text>
        </div>
        {asset ? <OmnixStatusPill>completed</OmnixStatusPill> : null}
      </Group>
      {asset ? (
        <div style={{ display: 'grid', gap: '1rem', gridTemplateColumns: 'minmax(220px, 420px) 1fr', marginTop: '1rem' }}>
          <img
            src={imageAssetUrl(asset.id)}
            alt={title}
            decoding="async"
            style={{ aspectRatio: '1 / 1', borderRadius: '0.75rem', objectFit: 'cover', width: '100%' }}
          />
          <div>
            <Title order={5}>{title}</Title>
            <Text size="sm" mt="xs">{imageAssetMetadata(asset)}</Text>
            <Text size="sm" mt="xs">Generated {formatCreatedAt(asset.created_at)}</Text>
            <Group mt="md">
              <Button
                aria-label={`Open ${title} in a new tab`}
                component="a"
                href={imageAssetUrl(asset.id)}
                target="_blank"
                rel="noreferrer"
                variant="light"
              >
                Open image
              </Button>
              <Button
                aria-label={`Download ${title}`}
                component="a"
                href={imageAssetUrl(asset.id, true)}
                download
                variant="default"
              >
                Download
              </Button>
            </Group>
          </div>
        </div>
      ) : (
        <div className="platform-empty" role="status" style={{ marginTop: '1rem' }}>
          Generate an image to see the latest result here.
        </div>
      )}
    </section>
  );
}
