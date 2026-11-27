/**
 * The story bible as the cards edit it (ST-2.3): the project's characters, world notes and presets (ST-5.2). The server
 * replaces the cast and the notes whole, so every change sends the full list back, with the suggestions
 * the writer has not answered yet still marked `suggested`.
 */
import type { StoryCharacter, StoryCharacterInput, StoryNote, StoryNoteInput } from './api/storyClient';

export type CharacterDraft = { name: string; role: string; aliases: string; description: string };

export const emptyCharacterDraft: CharacterDraft = { name: '', role: '', aliases: '', description: '' };

export function characterInput(character: StoryCharacter): StoryCharacterInput {
  return {
    id: character.id,
    name: character.name,
    aliases: character.aliases,
    description: character.description,
    traits: character.traits,
    role: character.role,
    suggested: character.suggested,
  };
}

export function draftOf(character: StoryCharacter): CharacterDraft {
  return { name: character.name, role: character.role, aliases: character.aliases.join(', '), description: character.description };
}

/** An id the server accepts, made from the name and unused in this cast. */
export function newCharacterId(name: string, cast: Array<{ id: string }>): string {
  const base = name.normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40) || 'character';
  const taken = new Set(cast.map((character) => character.id));
  let id = base;
  for (let suffix = 2; taken.has(id); suffix += 1) id = `${base}-${suffix}`;
  return id;
}

function fromDraft(draft: CharacterDraft): Pick<StoryCharacterInput, 'name' | 'role' | 'aliases' | 'description'> {
  const name = draft.name.trim().slice(0, 120);
  const aliases = [...new Set(draft.aliases.split(',').map((alias) => alias.trim()).filter((alias) => alias && alias !== name))];
  return { name, role: draft.role.trim().slice(0, 120), aliases: aliases.slice(0, 20), description: draft.description.trim().slice(0, 2_000) };
}

/** The cast with a character added (a new id) or changed (``id`` given); a changed suggestion stays a suggestion. */
export function withCharacter(cast: StoryCharacter[], draft: CharacterDraft, id?: string): StoryCharacterInput[] {
  const fields = fromDraft(draft);
  if (!fields.name) return cast.map(characterInput);
  if (id) return cast.map((character) => (character.id === id ? { ...characterInput(character), ...fields } : characterInput(character)));
  return [...cast.map(characterInput), { id: newCharacterId(fields.name, cast), ...fields, traits: [], suggested: false }];
}

export function acceptCharacter(cast: StoryCharacter[], id: string): StoryCharacterInput[] {
  return cast.map((character) => ({ ...characterInput(character), ...(character.id === id ? { suggested: false } : {}) }));
}

/** Removing a character, or dismissing a suggestion: their lines stay, flagged, until someone in the cast speaks them. */
export function withoutCharacter(cast: StoryCharacter[], id: string): StoryCharacterInput[] {
  return cast.filter((character) => character.id !== id).map(characterInput);
}

export function noteInput(note: StoryNote): StoryNoteInput {
  return { id: note.id, kind: note.kind, title: note.title, body: note.body, tone: note.tone, writing_style: note.writing_style };
}

/** The notes with a world note added (no ``id``) or changed; the others go back as they are. */
export function withWorldNote(notes: StoryNote[], title: string, body: string, id?: string): StoryNoteInput[] {
  const fields = { title: title.trim().slice(0, 200), body: body.trim().slice(0, 20_000) };
  if (!fields.title && !fields.body) return notes.map(noteInput);
  if (id) return notes.map((note) => (note.id === id ? { ...noteInput(note), ...fields } : noteInput(note)));
  return [...notes.map(noteInput), { kind: 'world', ...fields }];
}

export function withoutNote(notes: StoryNote[], id: string): StoryNoteInput[] {
  return notes.filter((note) => note.id !== id).map(noteInput);
}

/** A preset (ST-5.2): a named tone and writing style, and instructions on how the story is told. */
export type PresetDraft = { title: string; tone: string; writingStyle: string; body: string };

export const emptyPresetDraft: PresetDraft = { title: '', tone: '', writingStyle: '', body: '' };

export function presetDraftOf(note: StoryNote): PresetDraft {
  return { title: note.title, tone: note.tone, writingStyle: note.writing_style, body: note.body };
}

/** The notes with a preset added (no ``id``) or changed; a preset needs a name. */
export function withPreset(notes: StoryNote[], draft: PresetDraft, id?: string): StoryNoteInput[] {
  const fields = {
    title: draft.title.trim().slice(0, 200),
    tone: draft.tone.trim().slice(0, 80),
    writing_style: draft.writingStyle.trim().slice(0, 80),
    body: draft.body.trim().slice(0, 20_000),
  };
  if (!fields.title) return notes.map(noteInput);
  if (id) return notes.map((note) => (note.id === id ? { ...noteInput(note), ...fields } : noteInput(note)));
  return [...notes.map(noteInput), { kind: 'preset', ...fields }];
}
