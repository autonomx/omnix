export type MemoryScope = 'global' | 'workspace' | 'project' | 'session';
export type MemorySource = 'user_saved' | 'assistant_suggested' | 'imported';

export type MemoryRecord = {
  id: string;
  scope: MemoryScope;
  source: MemorySource;
  category: 'preference' | 'fact' | 'project' | 'relationship' | 'instruction';
  content: string;
  confidence: number;
  pinned?: boolean;
  createdAt: string;
  updatedAt: string;
};

export function createMemoryRecord(memory: MemoryRecord): MemoryRecord {
  return { ...memory };
}

export function filterMemoriesByScope(memories: MemoryRecord[], scope: MemoryScope): MemoryRecord[] {
  return memories.filter((memory) => memory.scope === scope);
}

export function pinMemory(memory: MemoryRecord, updatedAt: string): MemoryRecord {
  return { ...memory, pinned: true, updatedAt };
}

export function requiresMemoryConfirmation(memory: MemoryRecord): boolean {
  return memory.source === 'assistant_suggested';
}
