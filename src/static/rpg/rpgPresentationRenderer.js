/**
 * Phase 10 — RPG Presentation Renderer.
 *
 * Renders speaker cards and presentation payloads for the frontend.
 */
function escapeHtml(str) {
  return String(str || "")
    .replace(/\u0026/g, "\u0026amp;")
    .replace(/\u003c/g, "\u0026lt;")
    .replace(/\u003e/g, "\u0026gt;")
    .replace(/"/g, "\u0026quot;")
    .replace(/'/g, "\u0026#039;");
}

function renderStyleTags(tags) {
  const list = Array.isArray(tags) ? tags : [];
  if (!list.length) return "";
  return `
    <div class="rpg-speaker-tags">
      ${list.map((tag) => `\u003cspan class="rpg-speaker-tag">${escapeHtml(tag)}\u003c/span>`).join("")}
    </div>
  `;
}

export function renderSpeakerCards(cards) {
  const list = Array.isArray(cards) ? cards : [];
  return `
    <div class="rpg-speaker-card-list">
      ${list.map((card) => `
        <div class="rpg-speaker-card" data-speaker-id="${escapeHtml(card.speaker_id)}">
          <div class="rpg-speaker-card-name">${escapeHtml(card.name || card.speaker_id)}\u003c/div>
          <div class="rpg-speaker-card-kind">${escapeHtml(card.kind || "")}\u003c/div>
          ${renderStyleTags(card.style_tags)}
        \u003c/div>
      `).join("")}
    \u003c/div>
  `;
}

export function renderScenePresentation(presentation) {
  const payload = presentation || {};
  const interjections = Array.isArray(payload.companion_interjections) ? payload.companion_interjections : [];
  const reactions = Array.isArray(payload.companion_reactions) ? payload.companion_reactions : [];

  return `
    <div class="rpg-presentation-block">
      <div class="rpg-presentation-header">
        <h3>Scene Presentation</h3>
        <div class="rpg-presentation-meta">
          <span>${escapeHtml(payload.scene_id || "")}\u003c/span>
          <span>${escapeHtml(payload.tone || "")}\u003c/span>
        \u003c/div>
      \u003c/div>
      ${renderSpeakerCards(payload.speaker_cards || [])}
      <div class="rpg-presentation-section">
        <h4>Companion Interjections</h4>
        ${
          interjections.length
            ? interjections.map((it) => `\u003cdiv class="codex-item">${escapeHtml(it.summary || "")}\u003c/div>`).join("")
            : `\u003cdiv class="codex-item">No interjections\u003c/div>`
        }
      \u003c/div>
      <div class="rpg-presentation-section">
        <h4>Companion Reactions</h4>
        ${
          reactions.length
            ? reactions.map((it) => `\u003cdiv class="codex-item">${escapeHtml(it.summary || "")}\u003c/div>`).join("")
            : `\u003cdiv class="codex-item">No reactions\u003c/div>`
        }
      \u003c/div>
    \u003c/div>
  `;
}

export function renderDialoguePresentation(presentation) {
  const payload = presentation || {};
  return `
    <div class="rpg-presentation-block">
      <div class="rpg-presentation-header">
        <h3>Dialogue Presentation</h3>
        <div class="rpg-presentation-meta">
          <span>${escapeHtml(payload.dialogue_id || "")}\u003c/span>
          <span>${escapeHtml(payload.speaker_id || "")}\u003c/span>
        \u003c/div>
      \u003c/div>
      ${renderSpeakerCards(payload.speaker_cards || [])}
    \u003c/div>
  `;
}