import { describe, expect, it } from 'vitest';
import { SETTINGS_OWNERSHIP_MAP, ownershipByMigration, ownershipForKey, validateSettingsOwnership } from './settingsOwnership';

describe('settings ownership map', () => {
  it('assigns a source and target owner to every mapped area', () => {
    expect(validateSettingsOwnership()).toEqual([]);
    expect(SETTINGS_OWNERSHIP_MAP.length).toBeGreaterThan(20);
    expect(SETTINGS_OWNERSHIP_MAP.every((record) => record.currentOwner && record.targetOwner && record.source)).toBe(true);
  });

  it('excludes job and session overrides from central persistence', () => {
    const scoped = SETTINGS_OWNERSHIP_MAP.filter((record) => record.scope === 'job' || record.scope === 'session');
    expect(scoped.length).toBeGreaterThan(0);
    expect(scoped.every((record) => record.migration === 'exclude')).toBe(true);
  });

  it('keeps tool governance with its integration owner', () => {
    expect(ownershipForKey('tools.governance')).toMatchObject({
      currentOwner: 'integration-api',
      targetOwner: 'integration-api',
      migration: 'summarize',
    });
  });

  it('identifies the areas that will be centralized', () => {
    const centralized = ownershipByMigration('centralize').map((record) => record.key);
    expect(centralized).toEqual(expect.arrayContaining(['global.models', 'assistant.defaults', 'voice.defaults', 'rpg.campaign-preferences']));
  });

  it('rejects accidental migration of a job-only value', () => {
    const invalid = SETTINGS_OWNERSHIP_MAP.map((record) => record.key === 'image.job-overrides' ? { ...record, migration: 'centralize' as const } : record);
    expect(validateSettingsOwnership(invalid)).toContainEqual({ code: 'invalid-exclusion', key: 'image.job-overrides' });
  });
});
