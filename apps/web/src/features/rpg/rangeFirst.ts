export function rangeFirst<T>(values: T[] | null | undefined): T | undefined {
  return values?.[0];
}
