/**
 * Phase 10 — RPG Presentation Renderer.
 *
 * Renders speaker cards and presentation payloads for the frontend.
 *
 * Phase 11.2 — Character Inspector frontend additions.
 * Phase 12 — Visual Identity System (scene illustrations + portrait status).
 * Phase 12.4 — Appearance profile + events rendering.
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

// ---- Phase 12 — Scene Illustrations ----

function getSceneIllustrationContainer() {
  return document.getElementById("rpg-scene-illustrations");
}

export function renderSceneIllustrations(visualState) {
  const container = getSceneIllustrationContainer();
  if (!container) return;

  const illustrations = Array.isArray(visualState?.scene_illustrations)
    ? visualState.scene_illustrations
    : [];

  if (!illustrations.length) {
    container.innerHTML = `<div class="inspector-empty">No scene illustrations.</div>`;
    return;
  }

  container.innerHTML = illustrations.map((item) => {
    const title = escapeHtml(item.title || item.scene_id || item.event_id || "Scene");
    const imageUrl = escapeHtml(item.image_url || "");
    const style = escapeHtml(item.style || "");
    const prompt = escapeHtml(item.prompt || "");
    const image = imageUrl
      ? `<img class="scene-illustration-image" src="${imageUrl}" alt="${title}">`
      : `<div class="scene-illustration-image scene-illustration-image--placeholder"></div>`;

    return `
      <div class="scene-illustration-card">
        ${image}
        <div class="scene-illustration-title">${title}</div>
        ${style ? `<div class="scene-illustration-meta">${style}</div>` : ""}
        ${prompt ? `<div class="scene-illustration-prompt">${prompt}</div>` : ""}
      </div>
    `;
  }).join("");
}

// ---- End Phase 12 additions ----

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

// ---- Phase 12.4 — Appearance rendering ----

export function renderAppearanceEvents(events) {
  const list = Array.isArray(events) ? events : [];
  if (!list.length) return `<div class="inspector-empty">No appearance events.</div>`;
  return list.map((e) => `
    <div class="inspector-appearance-event">
      <span class="inspector-event-reason">${escapeHtml(e.reason)}</span>
      <span class="inspector-event-summary">${escapeHtml(e.summary || "")}</span>
    </div>
  `).join("");
}

export function renderInspectorPanel(character) {
  if (!character || typeof character !== "object") return "";
  const inspector = character.inspector || {};

  // Phase 12.4 — Appearance profile and events
  const appearance = character.appearance || {};
  const appearanceProfile = appearance.profile || {};
  const appearanceSummary = escapeHtml(appearanceProfile.current_summary || "—");
  const recentEvents = Array.isArray(appearance.recent_events) ? appearance.recent_events : [];

  return `
    <div class="inspector-panel" data-character-id="${escapeHtml(character.id)}">
      <div class="inspector-header">${escapeHtml(character.name || character.id)}</div>
      <div class="inspector-section">
        <h5>Appearance</h5>
        <div>${appearanceSummary}</div>
      </div>
      <div class="inspector-section">
        <h5>Recent Appearance Events</h5>
        ${renderAppearanceEvents(recentEvents)}
      </div>
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
    // ---- Phase 11.4 — Character Cards + Portraits ----
    // ---- Phase 12 — Portrait Status Indicators ----
    const subtitle = escapeHtml(c.card?.subtitle || role);
    const summary = escapeHtml(c.card?.summary || "");
    const badge = escapeHtml(c.card?.badge || "");
    const portraitUrl = escapeHtml(c.visual_identity?.portrait_url || "");
    const portraitStatus = escapeHtml(c.visual_identity?.status || "idle");

    // Phase 12.4 — Appearance summary
    const appearanceReason = escapeHtml(c.appearance?.profile?.last_reason || "");

    const portrait = portraitUrl
      ? `<img class="inspector-character-portrait" src="${portraitUrl}" alt="${name}">`
      : `<div class="inspector-character-portrait inspector-character-portrait--placeholder"></div>`;

    const selected = selectedCharacterId && selectedCharacterId === (c.id || "") ? " is-selected" : "";
    return `
      <button
        type="button"
        class="inspector-character-button${selected}"
        data-character-id="${id}"
      >
        ${portrait}
        <div class="inspector-character-name">${name}</div>
        <div class="inspector-character-role">${subtitle}</div>
        ${badge ? `<div class="inspector-character-badge">${badge}</div>` : ""}
        ${summary ? `<div class="inspector-character-summary">${summary}</div>` : ""}
        ${appearanceReason ? `<div class="inspector-character-summary">appearance: ${appearanceReason}</div>` : ""}
        ${portraitStatus && portraitStatus !== "idle" ? `<div class="inspector-character-portrait-status portrait-status-${portraitStatus}">portrait: ${portraitStatus}</div>` : ""}
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

// ---- Phase 11.3 — World Inspector ----

let selectedWorldItemId = "";
let selectedWorldItemKind = "location";

function getWorldInspectorContainer() {
  return document.getElementById("rpg-world-inspector");
}

function getWorldListContainer() {
  return document.getElementById("rpg-world-panel");
}

export function renderWorldList(worldInspectorState) {
  const container = getWorldListContainer();
  if (!container) return;

  const factions = Array.isArray(worldInspectorState?.factions?.factions) ? worldInspectorState.factions.factions : [];
  const locations = Array.isArray(worldInspectorState?.locations?.locations) ? worldInspectorState.locations.locations : [];

  const items = [
    ...locations.map((item) => ({ ...item, _kind: "location" })),
    ...factions.map((item) => ({ ...item, _kind: "faction" })),
  ];

  if (!items.length) {
    container.innerHTML = `<div class="inspector-empty">No world items available.</div>`;
    return;
  }

  container.innerHTML = items.map((item) => {
    const id = escapeHtml(item.id || "");
    const name = escapeHtml(item.name || item.id || "Unknown");
    const kind = escapeHtml(item._kind || item.kind || "world");
    const selected =
      selectedWorldItemId === (item.id || "") && selectedWorldItemKind === (item._kind || "")
        ? " is-selected"
        : "";

    return `
      <button
        type="button"
        class="inspector-world-button${selected}"
        data-world-id="${id}"
        data-world-kind="${kind}"
      >
        <div class="inspector-world-name">${name}</div>
        <div class="inspector-world-kind">${kind}</div>
      </button>
    `;
  }).join("");
}

export function renderWorldInspector(worldInspectorState) {
  const container = getWorldInspectorContainer();
  if (!container) return;

  const factions = Array.isArray(worldInspectorState?.factions?.factions) ? worldInspectorState.factions.factions : [];
  const locations = Array.isArray(worldInspectorState?.locations?.locations) ? worldInspectorState.locations.locations : [];

  const items = [
    ...locations.map((item) => ({ ...item, _kind: "location" })),
    ...factions.map((item) => ({ ...item, _kind: "faction" })),
  ];

  const selected =
    items.find((item) => String(item.id || "") === selectedWorldItemId && String(item._kind || "") === selectedWorldItemKind) ||
    items[0] ||
    null;

  if (!selected) {
    container.innerHTML = `<div class="inspector-empty">Select a world item.</div>`;
    return;
  }

  if (selected._kind === "location") {
    const tags = Array.isArray(selected.tags) ? selected.tags.map((t) => `<span class="inspector-tag">${escapeHtml(t)}</span>`).join("") : "";
    const actors = Array.isArray(selected.actors) ? selected.actors.map((a) => `<li>${escapeHtml(a)}</li>`).join("") : "";
    container.innerHTML = `
      <div class="inspector-panel">
        <div class="inspector-header">${escapeHtml(selected.name || selected.id)}</div>
        <div class="inspector-section"><h5>Description</h5><div>${escapeHtml(selected.description || "—")}</div></div>
        <div class="inspector-section"><h5>Tags</h5><div>${tags || '<div class="inspector-empty">None</div>'}</div></div>
        <div class="inspector-section"><h5>Actors</h5>${actors ? `<ul class="inspector-list">${actors}</ul>` : '<div class="inspector-empty">None</div>'}</div>
      </div>
    `;
    return;
  }

  const rels = Array.isArray(selected.relationships)
    ? selected.relationships.map((r) => `<li>${escapeHtml(r.target_id)} — ${escapeHtml(r.kind || "neutral")}</li>`).join("")
    : "";
  const members = Array.isArray(selected.members)
    ? selected.members.map((m) => `<li>${escapeHtml(m)}</li>`).join("")
    : "";

  container.innerHTML = `
    <div class="inspector-panel">
      <div class="inspector-header">${escapeHtml(selected.name || selected.id)}</div>
      <div class="inspector-section"><h5>Description</h5><div>${escapeHtml(selected.description || "—")}</div></div>
      <div class="inspector-section"><h5>Members</h5>${members ? `<ul class="inspector-list">${members}</ul>` : '<div class="inspector-empty">None</div>'}</div>
      <div class="inspector-section"><h5>Relationships</h5>${rels ? `<ul class="inspector-list">${rels}</ul>` : '<div class="inspector-empty">None</div>'}</div>
    </div>
  `;
}

export function bindWorldInspectorEvents(worldInspectorState) {
  const container = getWorldListContainer();
  if (!container) return;

  container.onclick = (e) => {
    const node = e.target.closest("[data-world-id]");
    if (!node) return;
    selectedWorldItemId = String(node.getAttribute("data-world-id") || "");
    selectedWorldItemKind = String(node.getAttribute("data-world-kind") || "location");
    renderWorldList(worldInspectorState);
    renderWorldInspector(worldInspectorState);
  };
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

  // ---- Phase 11.3 — World Inspector ----
  const worldInspectorState = payload?.world_inspector_state || null;
  if (worldInspectorState && typeof worldInspectorState === "object") {
    const locations = Array.isArray(worldInspectorState?.locations?.locations) ? worldInspectorState.locations.locations : [];
    const factions = Array.isArray(worldInspectorState?.factions?.factions) ? worldInspectorState.factions.factions : [];
    if (!selectedWorldItemId) {
      const first = locations[0] || factions[0] || null;
      if (first) {
        selectedWorldItemId = String(first.id || "");
        selectedWorldItemKind = locations[0] ? "location" : "faction";
      }
    }
    renderWorldList(worldInspectorState);
    renderWorldInspector(worldInspectorState);
    bindWorldInspectorEvents(worldInspectorState);
  }

  // ---- Phase 12 — Render scene illustrations in presentation payload ----
  const visualState = payload?.visual_state || null;
  if (visualState && typeof visualState === "object") {
    renderSceneIllustrations(visualState);
  }

  return presentation;
}