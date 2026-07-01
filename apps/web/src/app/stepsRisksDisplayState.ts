export interface ProposalListItem {
  id: string;
  title: string;
  detail: string;
  badge: string;
  reviewRequired: boolean;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function itemText(value: unknown, fallback: string): string {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback;
}

export function createStepListState(value: unknown): ProposalListItem[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item, index) => {
    const record = asRecord(item);
    if (!record) {
      return [];
    }
    return [{
      id: itemText(record.id, `step-${index + 1}`),
      title: itemText(record.title, 'Review step'),
      detail: itemText(record.description, 'Review before use.'),
      badge: itemText(record.status, 'pending'),
      reviewRequired: true,
    }];
  });
}

export function createRiskListState(value: unknown): ProposalListItem[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item, index) => {
    const record = asRecord(item);
    if (!record) {
      return [];
    }
    return [{
      id: itemText(record.id, `risk-${index + 1}`),
      title: itemText(record.label, 'Review risk'),
      detail: itemText(record.message, 'Review before use.'),
      badge: itemText(record.severity, 'medium'),
      reviewRequired: true,
    }];
  });
}
