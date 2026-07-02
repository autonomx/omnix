export function rangeHas(values: unknown[] | null | undefined): boolean {
  return Boolean(values && values.length > 0);
}
