/**
 * Phase 10 — RPG Presentation Renderer.
 *
 * Renders speaker cards and presentation payloads for the frontend.
 *
 * Phase 11.2 — Character Inspector frontend additions.
 */
function escapeHtml(str) {
  return String(str || "")
    .replace(/\u0026/g, "\u0026amp;")
    .replace(/\u003c/g, "\u0026lt;")
    .replace(/\u003e/g, "\u0026gt;")
    .replace(/"/g, "\u0026quot;")
    .replace(/'/g, "\u0026#039;");
}

let selectedCharacterId = "";

function getCharacterInspectorContainer() {
  return document.getElementById("rpg-character-inspector");
}

function getCharacterListContainer() {
  return document.getElementById("rpg-character-panel");
}

function toCharacterInspectorModel(entry) {
  return entry && typeof entry === "object" ? entry : null;
}

// ---- Phase 11.2 — Character Inspector renderers ----

export function renderInventoryItems(items) {
  const list = Array.isArray(items) ? items : [];
  if (!list.length) return `<div class="inspector-empty">None</div>`;
  return list.map((item) => `
    <div class="inspector-inventory-item">
      <span class="inspector-item-name">${escapeHtml(item.name || item.id)}</span>
      ${typeof item.quantity === "number" && item.quantity > 1 ? `<span class="inspector-item-qty">x${item.quantity}</span>` : ""}
    </div>
  `).join("");
}

export function renderGoals(goals) {
  const list = Array.isArray(goals) ? goals : [];
  if (!list.length) return `<div class="inspector-empty">None</div>`;
  return `<ul class="inspector-list">${list.map((g) => `<li>${escapeHtml(g)}</li>`).join("")}</ul>`;
}

export function renderBeliefs(beliefs) {
  const list = Array.isArray(beliefs) ? beliefs : [];
  if (!list.length) return `<div class="inspector-empty">None</div>`;
  return list.map((b) => `
    <div class="inspector-belief">
      <span class="inspector-belief-target">${escapeHtml(b.target_id)}:</span>
      <span class="inspector-belief-summary">${escapeHtml(b.summary || "")}</span>
    </div>
  `).join("");
}

export function renderActiveQuests(quests) {
  const list = Array.isArray(quests) ? quests : [];
  if (!list.length) return `<div class="inspector-empty">None</div>`;
  return list.map((q) => `
    <div class="inspector-quest">
      <span class="inspector-quest-title">${escapeHtml(q.title || q.id)}</span>
      <span class="inspector-quest-status">${escapeHtml(q.status || "active")}</span>
    </div>
  `).join("");
}

export function renderRelationshipSummary(summary) {
  const s = summary || {};
  return `
    <div class="inspector-relationships">
      <span class="inspector-rel-positive">+${s.positive || 0}</span>
      <span class="inspector-rel-neutral">=${s.neutral || 0}</span>
      <span class="inspector-rel-negative">-${s.negative || 0}</span>
    </div>
  `;
}

export function renderInspectorPanel(character) {
  if (!character || typeof character !== "object") return "";
  const inspector = character.inspector || {};
  return `
    <div class="inspector-panel" data-character-id="${escapeHtml(character.id)}">
      <div class="inspector-header">${escapeHtml(character.name || character.id)}</div>
      <div class="inspector-section">
        <h5>Inventory</h5>
        ${renderInventoryItems(inspector.inventory)}
      </div>
      <div class="inspector-section">
        <h5>Goals</h5>
        ${renderGoals(inspector.goals)}
      </div>
      <div class="inspector-section">
        <h5>Beliefs</h5>
        ${renderBeliefs(inspector.beliefs)}
      </div>
      <div class="inspector-section">
        <h5>Active Quests</h5>
        ${renderActiveQuests(inspector.active_quests)}
      </div>
      <div class="inspector-section">
        <h5>Relationships</h5>
        ${renderRelationshipSummary(inspector.relationship_summary)}
      </div>
    </div>
  `;
}

export function renderCharacterInspector(character) {
  const container = getCharacterInspectorContainer();
  if (!container) return;

  if (!character || typeof character !== "object") {
    container.innerHTML = `<div class="inspector-empty">Select a character.</div>`;
    return;
  }

  container.innerHTML = renderInspectorPanel(character);
}

export function renderCharacterList(inspectorState) {
  const container = getCharacterListContainer();
  if (!container) return;

  const characters = Array.isArray(inspectorState?.characters) ? inspectorState.characters : [];
  if (!characters.length) {
    container.innerHTML = `<div class="inspector-empty">No characters in inspector state.</div>`;
    return;
  }

  container.innerHTML = characters.map((c) => {
    const id = escapeHtml(c.id || "");
    const name = escapeHtml(c.name || c.id || "Unknown");
    const role = escapeHtml(c.role || "character");
    const currentIntent = escapeHtml(c.current_intent || "");
    const selected = selectedCharacterId && selectedCharacterId === (c.id || "") ? " is-selected" : "";
    return `
      <button
        type="button"
        class="inspector-character-button${selected}"
        data-character-id="${id}"
      >
        <div class="inspector-character-name">${name}</div>
        <div class="inspector-character-role">${role}</div>
        ${currentIntent ? `<div class="inspector-character-intent">${currentIntent}</div>` : ""}
      </button>
    `;
  }).join("");
}

export function bindCharacterInspectorEvents(inspectorState) {
  const container = getCharacterListContainer();
  if (!container) return;

  const characters = Array.isArray(inspectorState.characters) ? inspectorState.characters : [];

  container.onclick = (e) => {
    const node = e.target.closest("[data-character-id]");
    if (!node) return;

    selectedCharacterId = String(node.getAttribute("data-character-id") || "");
    const selected = characters.find((c) => String(c?.id || "") === selectedCharacterId) || null;

    renderCharacterList(inspectorState);
    renderCharacterInspector(selected);
  };
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

export function renderPresentation(payload) {
  const presentation = payload && typeof payload === "object" ? payload.presentation : null;
  // existing presentation rendering continues here
  // ...

  const inspectorState = payload?.character_inspector_state || null;

  if (!inspectorState || !Array.isArray(inspectorState.characters)) {
    return presentation;
  }

  const characters = inspectorState.characters.map(toCharacterInspectorModel).filter(Boolean);
  const normalizedInspectorState = {
    characters,
    count: typeof inspectorState.count === "number" ? inspectorState.count : characters.length,
  };

  if (!characters.length) {
    renderCharacterList(normalizedInspectorState);
    renderCharacterInspector(null);
    return presentation;
  }

  if (!selectedCharacterId) {
    selectedCharacterId = String(characters[0].id || "");
  }

  const selected =
    characters.find((c) => String(c?.id || "") === selectedCharacterId) ||
    characters[0] ||
    null;

  renderCharacterList(normalizedInspectorState);
  renderCharacterInspector(selected);
  bindCharacterInspectorEvents(normalizedInspectorState);

  return presentation;
}