export function rangeEmpty(values: unknown[] | null | undefined): boolean {
  return !values || values.length === 0;
}
