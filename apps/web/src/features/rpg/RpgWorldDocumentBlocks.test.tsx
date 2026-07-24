import { fireEvent, render, screen, within } from '@testing-library/react';
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
      expanded_description: 'Its river basins and mountain passes developed distinct local identities while remaining tied together by old trade routes.\n\nThat tension between regional custom and shared infrastructure remains central to present political disputes.\n\nThis third paragraph should not be shown in the compact expansion.',
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
    const expansion = within(section as HTMLElement).getByText('Read more').closest('details');
    expect(expansion).not.toBeNull();
    expect(expansion).not.toHaveAttribute('open');
    fireEvent.click(within(expansion as HTMLElement).getByText('Read more'));
    expect(expansion).toHaveAttribute('open');
    expect(within(expansion as HTMLElement).getByText(/river basins and mountain passes/)).toBeInTheDocument();
    expect(within(expansion as HTMLElement).getByText(/regional custom and shared infrastructure/)).toBeInTheDocument();
    expect(within(expansion as HTMLElement).queryByText(/third paragraph/)).not.toBeInTheDocument();
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
