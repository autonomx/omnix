import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { RpgAuthoringEntityCard } from '../../api/rpgWorldAuthoringClient';
import { RpgWorldEntityDetail } from './RpgWorldEntityDetail';

const characterClass: RpgAuthoringEntityCard = {
  id: 'class:ward_runner',
  title: 'Ward Runner',
  summary: 'A mobile defender trained to cross unstable wards.',
  kind: 'class',
  card_type: 'classes',
  presentation: {
    variant: 'classes',
    eyebrow: 'Class / Discipline',
    badges: ['public'],
    highlights: [{ label: 'Primary role', value: 'mobile_defender' }],
    groups: [
      {
        label: 'Capabilities',
        items: ['Cross active wards', 'Redirect one spell'],
        style: 'list',
      },
      {
        label: 'Progression',
        items: ['Initiate', 'Runner', 'Pathfinder'],
        style: 'chips',
      },
    ],
  },
  metadata: {
    id: 'class:ward_runner',
    name: 'Ward Runner',
    kind: 'class',
    description: 'A mobile defender trained to cross unstable wards.',
    visibility: 'public',
    primary_role: 'mobile_defender',
    capabilities: ['Cross active wards', 'Redirect one spell'],
    progression: ['Initiate', 'Runner', 'Pathfinder'],
    equipment: ['Ward key', 'Travel cloak'],
    institution_ids: ['institution:wayfinders'],
  },
};

describe('RpgWorldEntityDetail', () => {
  it('shows the complete class dossier after a card is opened', () => {
    const onClose = vi.fn();
    render(
      <RpgWorldEntityDetail
        entity={characterClass}
        onClose={onClose}
        worldId="world:aurelia"
      />,
    );

    expect(screen.getByRole('dialog', { name: 'Ward Runner details' })).toBeInTheDocument();
    expect(screen.getByText('Cross active wards')).toBeInTheDocument();
    expect(screen.getByText('Pathfinder')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Additional details' })).toBeInTheDocument();
    expect(screen.getByText('Ward key')).toBeInTheDocument();
    expect(screen.getByText('Wayfinders')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Close Ward Runner details' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
