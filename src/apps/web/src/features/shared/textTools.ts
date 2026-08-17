export function firstLineTitle(text: string): string {
  const firstLine = text.split('\n').find((line) => line.trim());
  return firstLine ? firstLine.trim().slice(0, 48) : 'Untitled';
}
