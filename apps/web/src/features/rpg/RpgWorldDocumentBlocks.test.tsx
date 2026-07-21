import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { RpgAuthoringDocumentBlock } from '../../api/rpgWorldAuthoringClient';
import { RpgWorldDocumentBlock } from './RpgWorldDocumentBlocks';

const factBlock: RpgAuthoringDocumentBlock = {
  kind: 'facts',
  title: 'Canon facts',
  items: [
    {
      fact_id: 'fact:001a-01',
      authority: 'doc:realmoverview:001a',
      statement: 'Aethelgard is comprised of several distinct geographical and cultural sectors.',
      visibility: 'public',
      entity_refs: [
        { id: 'ent:aethelgard', role: 'is_composed_of' },
      ],
    },
  ],
};

describe('RpgWorldDocumentBlock', () => {
  it('renders provider-shaped facts as readable canon records instead of JSON', () => {
    render(<RpgWorldDocumentBlock block={factBlock} />);

    const section = screen.getByRole('heading', { name: 'Canon facts' }).closest('section');
    expect(section).not.toBeNull();
    expect(within(section as HTMLElement).getByText(
      'Aethelgard is comprised of several distinct geographical and cultural sectors.',
    )).toBeInTheDocument();
    expect(within(section as HTMLElement).getByText('Public')).toBeInTheDocument();
    expect(within(section as HTMLElement).getByText(/Aethelgard · Is Composed Of/)).toBeInTheDocument();
    expect(within(section as HTMLElement).queryByText(/"fact_id"/)).not.toBeInTheDocument();
  });

  it('renders prose sections as article text', () => {
    render(<RpgWorldDocumentBlock block={{
      kind: 'section',
      title: 'Overview',
      body: 'Magic is part of public life and civic duty.',
    }} />);

    expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument();
    expect(screen.getByText('Magic is part of public life and civic duty.')).toBeInTheDocument();
  });
});
