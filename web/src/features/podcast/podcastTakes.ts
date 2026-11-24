/**
 * The run's script saved as a Voice Studio script (owner question 2026-11-24: the final render "seems like doing
 * the same thing twice"). Each preview line is spoken under its saved line, so the voice job keeps it as that
 * line's take; the final render then reuses every take (`render_line_ids: []`) and speaks only lines the preview
 * never made, before mixing. The script stays in Voice Studio, where a line can be spoken again and the episode
 * restitched.
 */
import { voiceApiClient } from '../voice';
import type { ScriptSegment } from './podcastScript';

export type SavedLines = { scriptId: string; lineIds: string[] };

/**
 * Saves `segments` as a script and returns each segment's line id, in order. Null when scripts can't be saved (no
 * PostgreSQL, say) or the saved lines don't match the segments one for one: the run then renders as before.
 */
export async function saveRunScript(title: string, segments: Array<Pick<ScriptSegment, 'speaker' | 'text'>>): Promise<SavedLines | null> {
  const text = segments.map((segment) => `${segment.speaker}: ${segment.text}`).join('\n');
  const script = await voiceApiClient.createScript({ title: `${title.trim() || 'Podcast'} (podcast)`, text, settings: { source: 'podcast' } }).catch(() => null);
  if (!script) return null;
  const lines = script.lines ?? [];
  const matches = lines.length === segments.length
    && lines.every((line, index) => line.speaker === segments[index].speaker && line.text === segments[index].text.trim());
  if (matches) return { scriptId: script.id, lineIds: lines.map((line) => line.id) };
  await voiceApiClient.deleteScript(script.id).catch(() => undefined);
  return null;
}
