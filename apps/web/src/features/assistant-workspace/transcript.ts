export type TranscriptStatus = 'partial' | 'final';

export type TranscriptSegment = {
  id: string;
  text: string;
  status: TranscriptStatus;
  createdAt: string;
};

export function createTranscriptSegment(segment: TranscriptSegment): TranscriptSegment {
  return { ...segment };
}

export function getFinalTranscriptText(segments: TranscriptSegment[]): string {
  return segments
    .filter((segment) => segment.status === 'final')
    .map((segment) => segment.text.trim())
    .filter(Boolean)
    .join(' ');
}

export function replacePartialTranscript(
  segments: TranscriptSegment[],
  next: TranscriptSegment,
): TranscriptSegment[] {
  return [...segments.filter((segment) => segment.status !== 'partial'), next];
}
