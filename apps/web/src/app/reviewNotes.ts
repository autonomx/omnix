export function normalizeReviewNotes(notes: string, maxLength = 500): string {
  const trimmed = notes.trim().replace(/\s+/g, ' ');
  if (trimmed.length <= maxLength) {
    return trimmed;
  }
  return trimmed.slice(0, Math.max(0, maxLength)).trimEnd();
}
