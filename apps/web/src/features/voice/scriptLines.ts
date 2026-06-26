export interface ScriptSpeakerRow {
  name: string;
  count: number;
}

export function parseScriptSpeakers(text: string): ScriptSpeakerRow[] {
  const counts = new Map<string, number>();
  for (const rawLine of text.split('\n')) {
    const line = rawLine.trim();
    const colon = line.indexOf(':');
    if (colon <= 0) {
      continue;
    }
    const name = line.slice(0, colon).trim();
    const content = line.slice(colon + 1).trim();
    if (!name || !content || name.length > 50) {
      continue;
    }
    counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  return Array.from(counts.entries()).map(([name, count]) => ({ name, count }));
}
