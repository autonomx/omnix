export type SourceItem = { id: string; label: string };
export function listSourceItems(items: SourceItem[]): SourceItem[] { return [...items]; }
