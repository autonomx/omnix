import { describe, expect, it } from 'vitest';
import { omnixModules } from './modules';

const canonicalModuleIds = [
  'rpg',
  'chatbot',
  'storyteller',
  'podcast',
  'voice',
  'voice-cloning',
  'stt',
  'image-generation',
  'providers',
  'models',
  'jobs',
  'assets',
  'reports',
  'settings',
  'diagnostics',
];

describe('omnixModules', () => {
  it('matches the canonical platform module order', () => {
    expect(omnixModules.map((module) => module.id)).toEqual(canonicalModuleIds);
  });

  it('defines a unique route for every module', () => {
    const routes = omnixModules.map((module) => module.route);

    expect(new Set(routes).size).toBe(canonicalModuleIds.length);
    expect(routes).toHaveLength(canonicalModuleIds.length);
    expect(routes.every((route) => route.startsWith('/'))).toBe(true);
  });
});
