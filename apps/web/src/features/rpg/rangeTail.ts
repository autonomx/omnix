export function rangeTail<T>(values: T[] | null | undefined): T | undefined {
  return values && values.length > 0 ? values[values.length - 1] : undefined;
}
