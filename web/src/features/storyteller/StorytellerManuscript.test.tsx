import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { storyImportMarkerKey } from './storyImport';
import { now, renderStoryteller, page, character, project, storyServer, type Block } from '../../test/storytellerServer';

beforeEach(() => {
  window.localStorage.setItem(storyImportMarkerKey, now);
});

afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('Storyteller manuscript editing (ST-6)', () => {
  it('edits a page in place and keeps each spoken line\'s speaker tag', async () => {
    const server = storyServer({
      projects: [project('project-1', {
        characters: [character('mira', 'Mira'), character('tomas', 'Tomas')],
        pages: [page('p1', '', {
          blocks: [
            { kind: 'narration', text: 'The gate creaked open.', speaker_id: null, attribution: null },
            { kind: 'dialogue', text: 'Who goes there?', speaker_id: 'mira', attribution: 'tagged' },
            { kind: 'dialogue', text: 'Only the wind.', speaker_id: 'stranger', attribution: 'unverified' },
          ],
        })],
      })],
    });
    renderStoryteller();
    const manuscript = await screen.findByRole('region', { name: 'Story manuscript' });
    fireEvent.click(await within(manuscript).findByRole('button', { name: 'Edit page 1' }));
    const editor = screen.getByRole('form', { name: 'Edit page 1' });
    expect(within(editor).getByRole('combobox', { name: 'Paragraph 2 speaker' })).toHaveValue('mira');
    expect(within(editor).getByRole('option', { name: 'stranger (not in cast)' })).toBeInTheDocument();
    fireEvent.change(within(editor).getByRole('textbox', { name: 'Paragraph 2' }), { target: { value: 'Who walks there?' } });
    fireEvent.change(within(editor).getByRole('combobox', { name: 'Paragraph 3 speaker' }), { target: { value: 'tomas' } });
    fireEvent.click(within(editor).getByRole('button', { name: 'Add a paragraph after paragraph 3' }));
    fireEvent.change(within(editor).getByRole('textbox', { name: 'Paragraph 4' }), { target: { value: '  The lantern swung.  ' } });
    fireEvent.click(within(editor).getByRole('button', { name: 'Save page' }));

    expect(await screen.findByText('Saved page 1.')).toBeInTheDocument();
    const patch = server.calls('PATCH', /^\/api\/story\/projects\/project-1\/pages\/p1$/);
    expect(patch).toHaveLength(1);
    expect(JSON.parse(String(patch[0][1]?.body))).toEqual({
      blocks: [
        { kind: 'narration', text: 'The gate creaked open.', speaker_id: null, attribution: null },
        { kind: 'dialogue', text: 'Who walks there?', speaker_id: 'mira', attribution: 'tagged' },
        { kind: 'dialogue', text: 'Only the wind.', speaker_id: 'tomas', attribution: null },
        { kind: 'narration', text: 'The lantern swung.', speaker_id: null, attribution: null },
      ],
      base_blocks: [
        { kind: 'narration', text: 'The gate creaked open.', speaker_id: null, attribution: null },
        { kind: 'dialogue', text: 'Who goes there?', speaker_id: 'mira', attribution: 'tagged' },
        { kind: 'dialogue', text: 'Only the wind.', speaker_id: 'stranger', attribution: 'unverified' },
      ],
    });
    expect(screen.queryByRole('form', { name: 'Edit page 1' })).not.toBeInTheDocument();
    const edited = (await within(manuscript).findByText('Who walks there?')).closest('p');
    expect(within(edited as HTMLElement).getByText('Mira')).toBeInTheDocument();
    expect(within(manuscript).getByText('Only the wind.').closest('p')).not.toHaveClass('storyteller-line-unverified');
  });

  it('will not save a page with every paragraph emptied, and cancels without a call', async () => {
    const server = storyServer();
    renderStoryteller();
    const manuscript = await screen.findByRole('region', { name: 'Story manuscript' });
    fireEvent.click(await within(manuscript).findByRole('button', { name: 'Edit page 1' }));
    const editor = screen.getByRole('form', { name: 'Edit page 1' });
    fireEvent.change(within(editor).getByRole('textbox', { name: 'Paragraph 1' }), { target: { value: ' ' } });
    fireEvent.change(within(editor).getByRole('textbox', { name: 'Paragraph 2' }), { target: { value: '' } });
    fireEvent.click(within(editor).getByRole('button', { name: 'Save page' }));
    expect(await within(editor).findByText('A page needs at least one paragraph.')).toBeInTheDocument();
    fireEvent.click(within(editor).getByRole('button', { name: 'Cancel' }));
    expect(await within(manuscript).findByText('Each branch remembered a name.')).toBeInTheDocument();
    expect(server.calls('PATCH', /\/pages\//)).toHaveLength(0);
  });

  it('does not save over a page that changed while it was being edited', async () => {
    const server = storyServer();
    renderStoryteller();
    const manuscript = await screen.findByRole('region', { name: 'Story manuscript' });
    fireEvent.click(await within(manuscript).findByRole('button', { name: 'Edit page 1' }));
    const editor = screen.getByRole('form', { name: 'Edit page 1' });
    const stored = server.store.get('project-1')?.pages[0];
    if (!stored) throw new Error('No page');
    // Another tab, or an accepted proposal, changed the page after the editor opened.
    stored.blocks = [{ kind: 'narration', text: 'Accepted elsewhere.', speaker_id: null, attribution: null }];
    fireEvent.change(within(editor).getByRole('textbox', { name: 'Paragraph 1' }), { target: { value: 'Mine.' } });
    fireEvent.click(within(editor).getByRole('button', { name: 'Save page' }));
    expect(await within(editor).findByText(/The page changed while you were editing it/)).toBeInTheDocument();
    expect(stored.blocks.map((block) => block.text)).toEqual(['Accepted elsewhere.']);
  });

  it('rewrites only the selected paragraphs as a proposal, and rejecting it leaves the page as it was', async () => {
    const server = storyServer({
      projects: [project('project-1', {
        pages: [page('p1', 'The orchard rang like crystal at sunset.\n\nEach branch remembered a name.\n\nMira listened.')],
      })],
    });
    renderStoryteller();
    const manuscript = await screen.findByRole('region', { name: 'Story manuscript' });
    const second = await within(manuscript).findByText('Each branch remembered a name.');
    const third = within(manuscript).getByText('Mira listened.');
    const range = document.createRange();
    range.setStart(second.firstChild as Node, 2);
    range.setEnd(third.firstChild as Node, 4);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);
    fireEvent.mouseUp(second);
    const toolbar = await screen.findByRole('toolbar', { name: 'Selection' });
    expect(within(toolbar).getByText('2 paragraphs of page 1 selected')).toBeInTheDocument();
    fireEvent.click(within(toolbar).getByRole('button', { name: 'Rewrite selection' }));

    expect(await screen.findByText('The proposed change is ready: accept or reject it above the manuscript.')).toBeInTheDocument();
    expect(server.jobPayload()?.input_payload).toMatchObject({ action: 'rewrite', project_id: 'project-1', selection: { page_id: 'p1', start: 1, end: 3, texts: ['Each branch remembered a name.', 'Mira listened.'] } });
    const proposal = await screen.findByRole('region', { name: 'Proposed rewrite of page 1' });
    const changes = within(proposal).getByRole('list', { name: 'Proposed rewrite of page 1: changes' });
    expect(within(changes).getByText('Each branch remembered a name.').closest('li')).toHaveClass('storyteller-diff-removed');
    expect(within(changes).getByText('Mira listened.').closest('li')).toHaveClass('storyteller-diff-removed');
    expect(within(changes).getByText(/Written by job-1/).closest('li')).toHaveClass('storyteller-diff-added');
    expect(within(changes).queryByText('The orchard rang like crystal at sunset.')).not.toBeInTheDocument();

    fireEvent.click(within(proposal).getByRole('button', { name: 'Reject change' }));
    expect(await screen.findByText('Rejected the proposed change; the page is as it was.')).toBeInTheDocument();
    expect(server.calls('POST', /^\/api\/story\/projects\/project-1\/versions\/project-1-v1\/reject$/)).toHaveLength(1);
    expect(screen.queryByRole('region', { name: 'Proposed rewrite of page 1' })).not.toBeInTheDocument();
    expect(within(manuscript).getByText('Each branch remembered a name.')).toBeInTheDocument();
    expect(within(manuscript).queryByText(/Written by job-1/)).not.toBeInTheDocument();
    expect(server.store.get('project-1')?.pages[0].blocks.map((block) => block.text)).toEqual([
      'The orchard rang like crystal at sunset.', 'Each branch remembered a name.', 'Mira listened.',
    ]);
  });

  it('does not count the paragraph a selection ends at the start of, as a triple-click does', async () => {
    storyServer({
      projects: [project('project-1', { pages: [page('p1', 'The orchard rang.\n\nEach branch remembered a name.\n\nMira listened.')] })],
    });
    renderStoryteller();
    const manuscript = await screen.findByRole('region', { name: 'Story manuscript' });
    const second = await within(manuscript).findByText('Each branch remembered a name.');
    const range = document.createRange();
    range.setStart(second.firstChild as Node, 0);
    range.setEnd(within(manuscript).getByText('Mira listened.').firstChild as Node, 0);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);
    fireEvent.mouseUp(second);
    const toolbar = await screen.findByRole('toolbar', { name: 'Selection' });
    expect(within(toolbar).getByText('1 paragraph of page 1 selected')).toBeInTheDocument();
  });

  it('accepts a proposed change into only its paragraphs, keeping the page before it as a version', async () => {
    const original = page('p1', 'The orchard rang like crystal at sunset.\n\nEach branch remembered a name.\n\nMira listened.');
    const item = project('project-1', { pages: [original] });
    const proposed: Block[] = [{ kind: 'dialogue', text: 'Tell me yours.', speaker_id: 'mira', attribution: null }];
    item.characters = [character('mira', 'Mira')];
    item.versions = [{
      id: 'project-1-v1', kind: 'dialogue', title: '', version_number: 1, source_job_id: 'job-9', created_at: now, pages: [],
      selection: { page_id: 'p1', start: 1, end: 2, original: original.blocks.slice(1, 2), proposed, status: 'pending' },
    }];
    const server = storyServer({ projects: [item] });
    renderStoryteller();
    const proposal = await screen.findByRole('region', { name: 'Proposed dialogue polish of page 1' });
    expect(within(proposal).getByText('Mira')).toBeInTheDocument();
    fireEvent.click(within(proposal).getByRole('button', { name: 'Accept change' }));

    expect(await screen.findByText('Accepted the change to page 1; the story before it is kept in Versions.')).toBeInTheDocument();
    expect(server.calls('POST', /^\/api\/story\/projects\/project-1\/versions\/project-1-v1\/accept$/)).toHaveLength(1);
    const manuscript = screen.getByRole('region', { name: 'Story manuscript' });
    expect(await within(manuscript).findByText('Tell me yours.')).toBeInTheDocument();
    expect(within(manuscript).getByText('The orchard rang like crystal at sunset.')).toBeInTheDocument();
    expect(within(manuscript).getByText('Mira listened.')).toBeInTheDocument();
    expect(within(manuscript).queryByText('Each branch remembered a name.')).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Proposed dialogue polish of page 1' })).not.toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'Story versions' })).getByText('Before accepting version 1')).toBeInTheDocument();
  });

  it('only dismisses a proposal whose page changed since it was written', async () => {
    const item = project('project-1');
    item.versions = [{
      id: 'project-1-v1', kind: 'rewrite', title: '', version_number: 1, source_job_id: 'job-9', created_at: now, pages: [],
      selection: {
        page_id: 'project-1-p1', start: 0, end: 1, status: 'pending',
        original: [{ kind: 'narration', text: 'An older first line.', speaker_id: null, attribution: null }],
        proposed: [{ kind: 'narration', text: 'A newer first line.', speaker_id: null, attribution: null }],
      },
    }];
    const server = storyServer({ projects: [item] });
    renderStoryteller();
    const proposal = await screen.findByRole('region', { name: 'Proposed rewrite of page 1' });
    expect(within(proposal).getByText(/The page has changed since this was written/)).toBeInTheDocument();
    expect(within(proposal).getByRole('button', { name: 'Accept change' })).toBeDisabled();
    fireEvent.click(within(proposal).getByRole('button', { name: 'Dismiss' }));
    await waitFor(() => expect(server.calls('POST', /\/versions\/project-1-v1\/reject$/)).toHaveLength(1));
    expect(server.calls('POST', /\/accept$/)).toHaveLength(0);
  });

  it('compares a version with the manuscript and with another version, then restores it', async () => {
    const item = project('project-1');
    const older = [page('project-1-p1', 'The orchard rang like crystal at dawn.\n\nEach branch remembered a name.')];
    item.versions = [
      { id: 'project-1-v1', kind: 'manual', title: '', version_number: 1, source_job_id: null, created_at: now, pages: older },
      { id: 'project-1-v2', kind: 'manual', title: '', version_number: 2, source_job_id: null, created_at: now, pages: item.pages },
    ];
    const server = storyServer({ projects: [item] });
    renderStoryteller();
    const versions = await screen.findByRole('region', { name: 'Story versions' });
    fireEvent.click(within(versions).getByRole('button', { name: 'Compare version 1' }));

    const compare = await screen.findByRole('region', { name: 'Compare version 1' });
    expect(await within(compare).findByText('Against the manuscript now, version 1 removes 1 paragraph and adds 1 paragraph.')).toBeInTheDocument();
    const changes = within(compare).getByRole('list', { name: 'Compare version 1: changes' });
    expect(within(changes).getByText('The orchard rang like crystal at sunset.').closest('li')).toHaveClass('storyteller-diff-removed');
    expect(within(changes).getByText('The orchard rang like crystal at dawn.').closest('li')).toHaveClass('storyteller-diff-added');
    expect(within(changes).getByText('Each branch remembered a name.').closest('li')).toHaveClass('storyteller-diff-same');
    expect(screen.queryByRole('region', { name: 'Story manuscript' })).not.toBeInTheDocument();

    fireEvent.change(within(compare).getByRole('combobox', { name: 'Compare against' }), { target: { value: 'project-1-v2' } });
    expect(await within(compare).findByText('Against version 2, version 1 removes 1 paragraph and adds 1 paragraph.')).toBeInTheDocument();

    fireEvent.click(within(compare).getByRole('button', { name: 'Restore version 1' }));
    expect(await screen.findByText('Restored version 1.')).toBeInTheDocument();
    expect(server.calls('POST', /^\/api\/story\/projects\/project-1\/versions\/project-1-v1\/restore$/)).toHaveLength(1);
    const manuscript = await screen.findByRole('region', { name: 'Story manuscript' });
    expect(await within(manuscript).findByText('The orchard rang like crystal at dawn.')).toBeInTheDocument();
  });
});
