import { describe, expect, it } from 'vitest';
import type { StoryCharacter, StoryNote } from './api/storyClient';
import {
  acceptCharacter, newCharacterId, withCharacter, withPreset, withWorldNote, withoutCharacter, withoutNote,
} from './storyBibleModel';

function character(id: string, name: string, suggested = false): StoryCharacter {
  return { id, name, aliases: [], description: '', traits: ['brave'], role: '', suggested } as StoryCharacter;
}

function note(id: string, kind: string, title: string, extra: Partial<StoryNote> = {}): StoryNote {
  return { id, kind, title, body: '', tone: '', writing_style: '', created_at: '', updated_at: '', ...extra } as StoryNote;
}

describe('storyBibleModel', () => {
  it('makes an unused id the server accepts from a name', () => {
    expect(newCharacterId('Old Wren', [])).toBe('old-wren');
    expect(newCharacterId('Old Wren', [{ id: 'old-wren' }, { id: 'old-wren-2' }])).toBe('old-wren-3');
    expect(newCharacterId('Élodie', [])).toBe('elodie');
    expect(newCharacterId('???', [])).toBe('character');
    expect(newCharacterId('x'.repeat(90), [])).toHaveLength(40);
  });

  it('sends the whole cast back with every change, suggestions still marked', () => {
    const cast = [character('mira', 'Mira'), character('tobin', 'Tobin', true)];
    const added = withCharacter(cast, { name: ' Wren ', role: 'keeper', aliases: 'Wren, Old Wren, Wren', description: '' });
    expect(added.map((entry) => [entry.id, entry.suggested])).toEqual([['mira', false], ['tobin', true], ['wren', false]]);
    expect(added[2].aliases).toEqual(['Old Wren']);
    expect(withCharacter(cast, { name: '  ', role: '', aliases: '', description: '' })).toHaveLength(2);

    const edited = withCharacter(cast, { name: 'Tobin Ash', role: '', aliases: '', description: 'A smith' }, 'tobin');
    expect(edited[1]).toMatchObject({ id: 'tobin', name: 'Tobin Ash', description: 'A smith', suggested: true, traits: ['brave'] });
    expect(acceptCharacter(cast, 'tobin')[1].suggested).toBe(false);
    expect(withoutCharacter(cast, 'tobin').map((entry) => entry.id)).toEqual(['mira']);
  });

  it('adds and edits world notes and passes the other notes back unchanged', () => {
    const notes = [note('n1', 'preset', 'Noir', { tone: 'bleak', writing_style: 'terse' }), note('n2', 'world', 'The orchard')];
    const added = withWorldNote(notes, 'Rules', 'No magic at night');
    expect(added).toEqual([
      { id: 'n1', kind: 'preset', title: 'Noir', body: '', tone: 'bleak', writing_style: 'terse' },
      { id: 'n2', kind: 'world', title: 'The orchard', body: '', tone: '', writing_style: '' },
      { kind: 'world', title: 'Rules', body: 'No magic at night' },
    ]);
    expect(withWorldNote(notes, 'Orchard', 'Fruit remembers', 'n2')[1]).toMatchObject({ id: 'n2', kind: 'world', title: 'Orchard', body: 'Fruit remembers' });
    expect(withWorldNote(notes, ' ', ' ')).toHaveLength(2);
    expect(withoutNote(notes, 'n2').map((entry) => entry.id)).toEqual(['n1']);
  });

  it('adds and edits presets with their tone, style and instructions; a preset needs a name', () => {
    const notes = [note('n1', 'preset', 'Noir', { tone: 'bleak', writing_style: 'terse', body: 'Short.' }), note('n2', 'world', 'River')];
    const added = withPreset(notes, { title: ' Fable ', tone: 'warm', writingStyle: 'lyrical', body: ' Speak plainly. ' });
    expect(added[2]).toEqual({ kind: 'preset', title: 'Fable', tone: 'warm', writing_style: 'lyrical', body: 'Speak plainly.' });
    expect(added[0]).toEqual({ id: 'n1', kind: 'preset', title: 'Noir', body: 'Short.', tone: 'bleak', writing_style: 'terse' });
    const edited = withPreset(notes, { title: 'Noir', tone: 'grim', writingStyle: 'terse', body: 'Shorter.' }, 'n1');
    expect(edited[0]).toMatchObject({ id: 'n1', kind: 'preset', tone: 'grim', body: 'Shorter.' });
    expect(withPreset(notes, { title: '  ', tone: 'x', writingStyle: '', body: 'y' })).toHaveLength(2);
  });
});
