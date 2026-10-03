/** Reading chat messages for display: attachments and times. */
export const MAX_CHAT_IMAGE_ATTACHMENTS = 8;
export const SUPPORTED_CHAT_IMAGE_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp']);

export function formatMessageTime(value: string): string { if (value.includes('T')) return value.slice(11, 16); return value; }
export function chatImageDataUrls(metadata?: Record<string, unknown>): string[] {
  const candidates: unknown[] = [];
  if (Array.isArray(metadata?.image_data_urls)) candidates.push(...metadata.image_data_urls);
  if (metadata?.image_data_url) candidates.unshift(metadata.image_data_url);
  const images: string[] = [];
  for (const value of candidates) {
    if (typeof value !== 'string') continue;
    if (![...SUPPORTED_CHAT_IMAGE_TYPES].some((mimeType) => value.startsWith(`data:${mimeType};base64,`))) continue;
    if (!images.includes(value)) images.push(value);
    if (images.length >= MAX_CHAT_IMAGE_ATTACHMENTS) break;
  }
  return images;
}
export function chatTextAttachment(metadata?: Record<string, unknown>): { filename: string; mimeType: string } | null { const value = metadata?.text_attachment; if (!value || typeof value !== 'object' || Array.isArray(value)) return null; const attachment = value as Record<string, unknown>; const filename = typeof attachment.filename === 'string' ? attachment.filename.trim() : ''; const mimeType = typeof attachment.mime_type === 'string' ? attachment.mime_type.trim() : ''; const text = typeof attachment.text === 'string' ? attachment.text : ''; return filename && mimeType && text ? { filename, mimeType } : null; }
