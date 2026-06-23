export type TimelineItemKind = 'turn' | 'event' | 'note';

export type TimelineItem = {
  id: string;
  kind: TimelineItemKind;
  createdAt: string;
  label: string;
};

export function sortTimelineItems(items: TimelineItem[]): TimelineItem[] {
  return [...items].sort((left, right) => left.createdAt.localeCompare(right.createdAt) || left.id.localeCompare(right.id));
}

export function filterTimelineItemsByKind(items: TimelineItem[], kind: TimelineItemKind): TimelineItem[] {
  return items.filter((item) => item.kind === kind);
}

export function createTimelineNote(id: string, label: string, createdAt: string): TimelineItem {
  return { id, kind: 'note', label, createdAt };
}
