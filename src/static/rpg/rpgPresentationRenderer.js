/**
 * Phase 10 — RPG Presentation Renderer.
 *
 * Renders speaker cards and presentation payloads for the frontend.
 *
 * Phase 11.2 — Character Inspector frontend additions.
 * Phase 12 — Visual Identity System (scene illustrations + portrait status).
 * Phase 12.4 — Appearance profile + events rendering.
 * Phase 12.7 — Tabbed inspector layout + navigation.
 * Phase 12.8 — GM Inspector panel.
 */

let selectedCharacterId = "";

// ---- Phase 12.7 — Tabbed inspector layout + navigation ----

let activeInspectorTab = "characters";

function getInspectorTabsContainer() {
  return document.getElementById("rpg-inspector-tabs");
}

function getCharactersSectionContainer() {
  return document.getElementById("rpg-characters-section");
}

function getWorldSectionContainer() {
  return document.getElementById("rpg-world-section");
}

function getVisualsSectionContainer() {
  return document.getElementById("rpg-visuals-section");
}

function getGMSectionContainer() {
  return document.getElementById("rpg-gm-section");
}

function getPackageSectionContainer() {
  return document.getElementById("rpg-package-section");
}

function getContentPackSectionContainer() {
  return document.getElementById("rpg-content-pack-section");
}

function getWizardSectionContainer() {
  return document.getElementById("rpg-wizard-section");
}

function getSessionSectionContainer() {
  return document.getElementById("rpg-session-section");
}

function getMemorySectionContainer() {
  return document.getElementById("rpg-memory-section");
}

export function renderInspectorTabs() {
  const container = getInspectorTabsContainer();
  if (!container) return;

  const tabs = [
    { id: "characters", label: "Characters" },
    { id: "world", label: "World" },
    { id: "visuals", label: "Visuals" },
    { id: "gm", label: "GM" },
    { id: "package", label: "Package" },
    { id: "packs", label: "Packs" },
    { id: "wizard", label: "Wizard" },
    { id: "sessions", label: "Sessions" },
    { id: "memory", label: "Memory" },
  ];

  container.innerHTML = `
    <div class="inspector-tabs">
      ${tabs.map((tab) => `
        <button
          type="button"
          class="inspector-tab${activeInspectorTab === tab.id ? " is-active" : ""}"
          data-tab-id="${tab.id}"
        >
          ${escapeHtml(tab.label)}
        </button>
      `).join("")}
    </div>
  `;
}

export function bindInspectorTabs() {
  const container = getInspectorTabsContainer();
  if (!container) return;

  container.onclick = (e) => {
    const node = e.target.closest("[data-tab-id]");
    if (!node) return;
    activeInspectorTab = String(node.getAttribute("data-tab-id") || "characters");
    updateInspectorVisibility();
    renderInspectorTabs();
  };
}

export function updateInspectorVisibility() {
  const charactersSection = getCharactersSectionContainer();
  const worldSection = getWorldSectionContainer();
  const visualsSection = getVisualsSectionContainer();
  const gmSection = getGMSectionContainer();
  const packageSection = getPackageSectionContainer();
  const packsSection = getContentPackSectionContainer();
  const wizardSection = getWizardSectionContainer();
  const sessionSection = getSessionSectionContainer();
  const memorySection = getMemorySectionContainer();

  if (charactersSection) charactersSection.style.display = activeInspectorTab === "characters" ? "" : "none";
  if (worldSection) worldSection.style.display = activeInspectorTab === "world" ? "" : "none";
  if (visualsSection) visualsSection.style.display = activeInspectorTab === "visuals" ? "" : "none";
  if (gmSection) gmSection.style.display = activeInspectorTab === "gm" ? "" : "none";
  if (packageSection) packageSection.style.display = activeInspectorTab === "package" ? "" : "none";
  if (packsSection) packsSection.style.display = activeInspectorTab === "packs" ? "" : "none";
  if (wizardSection) wizardSection.style.display = activeInspectorTab === "wizard" ? "" : "none";
  if (sessionSection) sessionSection.style.display = activeInspectorTab === "sessions" ? "" : "none";
  if (memorySection) memorySection.style.display = activeInspectorTab === "memory" ? "" : "none";
}

// ---- End Phase 12.7 additions ----

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
      ${list.map((tag) => `<span class="rpg-speaker-tag">${escapeHtml(tag)}</span>`).join("")}
    </div>
  `;
}

export function renderSpeakerCards(cards) {
  const list = Array.isArray(cards) ? cards : [];
  return `
    <div class="rpg-speaker-card-list">
      ${list.map((card) => `
        <div class="rpg-speaker-card" data-speaker-id="${escapeHtml(card.speaker_id)}">
          <div class="rpg-speaker-card-name">${escapeHtml(card.name || card.speaker_id)}</div>
          <div class="rpg-speaker-card-kind">${escapeHtml(card.kind || "")}</div>
          ${renderStyleTags(card.style_tags)}
        </div>
      `).join("")}
    </div>
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
          <span>${escapeHtml(payload.scene_id || "")}</span>
          <span>${escapeHtml(payload.tone || "")}</span>
        </div>
      </div>
      ${renderSpeakerCards(payload.speaker_cards || [])}
      <div class="rpg-presentation-section">
        <h4>Companion Interjections</h4>
        ${
          interjections.length
            ? interjections.map((it) => `<div class="codex-item">${escapeHtml(it.summary || "")}</div>`).join("")
            : `<div class="codex-item">No interjections</div>`
        }
      </div>
      <div class="rpg-presentation-section">
        <h4>Companion Reactions</h4>
        ${
          reactions.length
            ? reactions.map((it) => `<div class="codex-item">${escapeHtml(it.summary || "")}</div>`).join("")
            : `<div class="codex-item">No reactions</div>`
        }
      </div>
    </div>
  `;
}

export function renderDialoguePresentation(presentation) {
  const payload = presentation || {};
  return `
    <div class="rpg-presentation-block">
      <div class="rpg-presentation-header">
        <h3>Dialogue Presentation</h3>
        <div class="rpg-presentation-meta">
          <span>${escapeHtml(payload.dialogue_id || "")}</span>
          <span>${escapeHtml(payload.speaker_id || "")}</span>
        </div>
      </div>
      ${renderSpeakerCards(payload.speaker_cards || [])}
    </div>
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

  // ---- Phase 12.7 — Render inspector tabs ----
  renderInspectorTabs();
  bindInspectorTabs();
  updateInspectorVisibility();

  // ---- Phase 12.8 — GM Inspector panel ----
  const gmInspectorState = payload?.trace || payload?.gm_inspector_state || null;
  if (gmInspectorState && typeof gmInspectorState === "object") {
    renderGMInspector(gmInspectorState);
  }

  // ---- Phase 12.9 — Package inspector ----
  const packageManifest = payload?.package_manifest || payload?.manifest || null;
  if (packageManifest && typeof packageManifest === "object") {
    renderPackageInspector(payload);
  }

  // ---- Phase 13.0 — Content packs ----
  if (Array.isArray(payload?.content_packs)) {
    renderContentPacks(payload);
  }

  // ---- Phase 13.4 — Wizard ----
  if (payload?.wizard_state && typeof payload.wizard_state === "object") {
    renderAdventureWizard(payload);
  }

  // ---- Phase 13.5 — Sessions ----
  if (Array.isArray(payload?.sessions)) {
    renderSessions(payload);
  }

  // ---- Phase 14.0 — Memory ----
  if (payload?.memory_state && typeof payload.memory_state === "object") {
    renderMemory(payload);
  }

  return presentation;
}

// ---- Phase 12.8 — GM Inspector panel renderer ----

function getGMInspectorContainer() {
  return document.getElementById("rpg-gm-inspector");
}

export function renderGMInspector(payload) {
  const container = getGMInspectorContainer();
  if (!container) return;

  const selectedCharacter = payload?.character || null;
  const inspectorCharacter = payload?.inspector || null;
  const appearanceEvents = Array.isArray(payload?.appearance_events) ? payload.appearance_events : [];
  const visualAssets = Array.isArray(payload?.visual_assets) ? payload.visual_assets : [];
  const imageRequests = Array.isArray(payload?.image_requests) ? payload.image_requests : [];

  const selectedCharHtml = selectedCharacter
    ? `<div class="gm-inspector-section"><h5>Selected Character</h5><div>${escapeHtml(selectedCharacter.name || selectedCharacter.id)}</div></div>`
    : "";

  const inspectorCharHtml = inspectorCharacter
    ? `<div class="gm-inspector-section"><h5>Inspector Character</h5><div>${escapeHtml(inspectorCharacter.name || inspectorCharacter.id)}</div></div>`
    : "";

  const appearanceHtml = appearanceEvents.length
    ? appearanceEvents.map((e) => `
        <div class="inspector-appearance-event">
          <span class="inspector-event-reason">${escapeHtml(e.reason || "")}</span>
          <span class="inspector-event-summary">${escapeHtml(e.summary || "")}</span>
        </div>
      `).join("")
    : `<div class="inspector-empty">No appearance events.</div>`;

  const visualAssetsHtml = visualAssets.length
    ? visualAssets.map((a) => `
        <div class="visual-asset-card">
          <div class="visual-asset-meta">
            <span>${escapeHtml(a.target_id || "")}</span>
            <span>${escapeHtml(a.kind || "")}</span>
          </div>
          ${a.url ? `<img class="visual-asset-image" src="${escapeHtml(a.url)}" alt="asset">` : ""}
        </div>
      `).join("")
    : `<div class="inspector-empty">No visual assets.</div>`;

  const imageRequestsHtml = imageRequests.length
    ? imageRequests.map((r) => {
        const status = escapeHtml(r.status || "pending");
        return `
        <div class="gm-image-request">
          <span class="gm-request-actor">${escapeHtml(r.target_id || "")}</span>
          <span class="gm-request-status ${status}">${status}</span>
        </div>
      `; }).join("")
    : `<div class="inspector-empty">No image requests.</div>`;

  container.innerHTML = `
    <div class="gm-inspector-panel">
      <div class="inspector-header">GM Inspector</div>
      ${selectedCharHtml}
      ${inspectorCharHtml}
      <div class="gm-inspector-section">
        <h5>Appearance Events</h5>
        ${appearanceHtml}
      </div>
      <div class="gm-inspector-section">
        <h5>Visual Assets</h5>
        ${visualAssetsHtml}
      </div>
      <div class="gm-inspector-section">
        <h5>Image Requests</h5>
        ${imageRequestsHtml}
      </div>
    </div>
  `;
}

// ---- End Phase 12.8 additions ----

// ---- Phase 12.9 — Package Inspector renderer ----

function getPackageInspectorContainer() {
  return document.getElementById("rpg-package-inspector");
}

export function renderPackageInspector(payload) {
  const container = getPackageInspectorContainer();
  if (!container) return;

  const manifest = payload?.package_manifest || payload?.manifest || null;
  if (!manifest || typeof manifest !== "object") {
    container.innerHTML = `<div class="inspector-empty">No package loaded.</div>`;
    return;
  }

  container.innerHTML = `
    <div class="inspector-panel">
      <div class="inspector-header">Package</div>
      <div class="inspector-section"><h5>Title</h5><div>${escapeHtml(manifest.title || "—")}</div></div>
      <div class="inspector-section"><h5>Description</h5><div>${escapeHtml(manifest.description || "—")}</div></div>
      <div class="inspector-section"><h5>Version</h5><div>${escapeHtml(manifest.package_version || "—")}</div></div>
      <div class="inspector-section"><h5>Created By</h5><div>${escapeHtml(manifest.created_by || "—")}</div></div>
    </div>
  `;
}

// ---- Phase 13.0 — Content Packs renderer ----

function getContentPackContainer() {
  return document.getElementById("rpg-content-packs");
}

export function renderContentPacks(payload) {
  const container = getContentPackContainer();
  if (!container) return;

  const packs = Array.isArray(payload?.content_packs) ? payload.content_packs : [];
  if (!packs.length) {
    container.innerHTML = `<div class="inspector-empty">No content packs.</div>`;
    return;
  }

  container.innerHTML = packs.map((pack) => {
    const manifest = pack?.manifest || {};
    return `
      <div class="content-pack-card">
        <div class="content-pack-title">${escapeHtml(manifest.title || manifest.id || "Pack")}</div>
        <div class="pack-meta">${escapeHtml(manifest.description || "")}</div>
        <div class="pack-meta">${escapeHtml(manifest.author || "")} · ${escapeHtml(manifest.version || "")}</div>
      </div>
    `;
  }).join("");
}

// ---- Phase 13.4 — Wizard UI renderer ----

function getWizardContainer() {
  return document.getElementById("rpg-wizard");
}

export function renderAdventureWizard(payload) {
  const container = getWizardContainer();
  if (!container) return;

  const wizardState = payload?.wizard_state || null;
  if (!wizardState || typeof wizardState !== "object") {
    container.innerHTML = `<div class="inspector-empty">No wizard active.</div>`;
    return;
  }

  const preview = payload?.wizard_preview || {};
  const step = escapeHtml(wizardState.step || "mode");
  const mode = escapeHtml(wizardState.mode || "blank");
  const title = escapeHtml(preview.title || wizardState.title || "—");
  const summary = escapeHtml(preview.summary || wizardState.summary || "—");
  const characterCount = preview.character_count ?? 0;
  const visualDefaults = preview.visual_defaults || wizardState.visual_defaults || {};

  let detailsHtml = "";
  if (Object.keys(visualDefaults).length > 0) {
    detailsHtml = Object.entries(visualDefaults).map(([k, v]) => `
      <div class="wizard-step">
        <span class="wizard-step-title">${escapeHtml(k)}:</span>
        <span class="wizard-step-body">${escapeHtml(v)}</span>
      </div>
    `).join("");
  }

  container.innerHTML = `
    <div class="wizard-card">
      <div class="wizard-step-title">New Adventure Wizard</div>
      <div class="wizard-step">
        <span class="wizard-step-title">Step:</span>
        <span class="wizard-step-body">${step}</span>
      </div>
      <div class="wizard-step">
        <span class="wizard-step-title">Mode:</span>
        <span class="wizard-step-body">${mode}</span>
      </div>
      <div class="wizard-step">
        <span class="wizard-step-title">Title:</span>
        <span class="wizard-step-body">${title}</span>
      </div>
      <div class="wizard-step">
        <span class="wizard-step-title">Summary:</span>
        <span class="wizard-step-body">${summary}</span>
      </div>
      <div class="wizard-step">
        <span class="wizard-step-title">Characters:</span>
        <span class="wizard-step-body">${characterCount}</span>
      </div>
      ${detailsHtml}
    </div>
  `;
}

// ---- Phase 13.5 — Session UI renderer ----

function getSessionContainer() {
  return document.getElementById("rpg-sessions");
}

export function renderSessions(payload) {
  const container = getSessionContainer();
  if (!container) return;

  const sessions = Array.isArray(payload?.sessions) ? payload.sessions : [];
  if (!sessions.length) {
    container.innerHTML = `<div class="inspector-empty">No sessions.</div>`;
    return;
  }

  container.innerHTML = sessions.map((session) => {
    const manifest = session?.manifest || {};
    const status = escapeHtml(manifest.status || "active");
    const statusClass = status === "archived" ? "session-status--archived" : "session-status";
    const sessionId = escapeHtml(manifest.id || "");
    const title = escapeHtml(manifest.title || manifest.id || "Session");
    const createdAt = escapeHtml(manifest.created_at || "");
    const updatedAt = escapeHtml(manifest.updated_at || "");

    return `
      <div class="session-card" data-session-id="${sessionId}">
        <div class="session-title">${title}</div>
        <div class="session-meta">
          <span class="session-status ${statusClass}">${status}</span>
          ${createdAt ? ` · Created: ${createdAt}` : ""}
          ${updatedAt ? ` · Updated: ${updatedAt}` : ""}
        </div>
      </div>
    `;
  }).join("");
}

// ---- Phase 14.0 — Memory UI renderer ----

function getMemoryContainer() {
  return document.getElementById("rpg-memory");
}

export function renderMemory(payload) {
  const container = getMemoryContainer();
  if (!container) return;

  const memoryState = payload?.memory_state || null;
  if (!memoryState || typeof memoryState !== "object") {
    container.innerHTML = `<div class="inspector-empty">No memory data.</div>`;
    return;
  }

  const shortTerm = Array.isArray(memoryState.short_term) ? memoryState.short_term : [];
  const longTerm = Array.isArray(memoryState.long_term) ? memoryState.long_term : [];
  const worldMemory = Array.isArray(memoryState.world_memory) ? memoryState.world_memory : [];

  if (!shortTerm.length && !longTerm.length && !worldMemory.length) {
    container.innerHTML = `<div class="inspector-empty">No memories stored.</div>`;
    return;
  }

  const renderEntries = (entries) => entries.map((e) => {
    const summary = escapeHtml(e.summary || "");
    const kind = escapeHtml(e.kind || "fact");
    const tick = typeof e.tick === "number" ? ` (tick ${e.tick})` : "";
    return `<div class="memory-entry"><span class="memory-entry-summary">${summary}</span><span class="memory-entry-kind">${kind}${tick}</span></div>`;
  }).join("");

  container.innerHTML = `
    ${shortTerm.length ? `<div class="memory-lane"><div class="memory-lane-title">Short-term Memory (${shortTerm.length})</div>${renderEntries(shortTerm)}</div>` : ""}
    ${longTerm.length ? `<div class="memory-lane"><div class="memory-lane-title">Long-term Memory (${longTerm.length})</div>${renderEntries(longTerm)}</div>` : ""}
    ${worldMemory.length ? `<div class="memory-lane"><div class="memory-lane-title">World Memory (${worldMemory.length})</div>${renderEntries(worldMemory)}</div>` : ""}
  `;
}

// ---------------------------------------------------------------------------
// Phase 18.1.B — Memory inspector UI helpers
// ---------------------------------------------------------------------------

function _safeText(value) {
  return value == null ? "" : String(value);
}

function escapeHtml(value) {
  const str = value == null ? "" : String(value);
  const amp = "\u0026amp;";
  const lt = "\u0026lt;";
  const gt = "\u0026gt;";
  const quot = "\u0026quot;";
  const apos = "\u0026#39;";
  return str
    .replace(/\u0026/g, amp)
    .replace(/\u003c/g, lt)
    .replace(/\u003e/g, gt)
    .replace(/"/g, quot)
    .replace(/'/g, apos);
}

export function renderInspectorError(label, error) {
  return `<div class="rpg-inspector-error">${escapeHtml(label)}: ${escapeHtml(error || "unknown_error")}</div>`;
}

function _renderInspectorEmpty(message) {
  return `<div class="rpg-inspector-empty">${escapeHtml(message || "No data")}</div>`;
}

function _renderKeyValueList(rows) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return _renderInspectorEmpty("No items");
  }
  return `
    <div class="rpg-inspector-kv-list">
      ${rows.map(row => `
        <div class="rpg-inspector-kv-row">
          <div class="rpg-inspector-kv-key">${escapeHtml(row.key)}</div>
          <div class="rpg-inspector-kv-value">${escapeHtml(row.value)}</div>
        </div>
      `).join("")}
    </div>
  `;
}

export function renderMemoryInspector(memoryInspector) {
  const payload = memoryInspector || {};
  const actorMemory = Array.isArray(payload.actor_memory) ? payload.actor_memory : [];
  const worldRumors = Array.isArray(payload.world_rumors) ? payload.world_rumors : [];

  const actorHtml = actorMemory.length
    ? actorMemory.map(actor => {
        const entries = Array.isArray(actor.entries) ? actor.entries : [];
        return `
          <div class="rpg-inspector-card">
            <div class="rpg-inspector-card-title">${escapeHtml(actor.actor_id || "unknown_actor")}</div>
            <div class="rpg-inspector-card-subtitle">${escapeHtml(`Entries: ${actor.entry_count || entries.length || 0}`)}</div>
            <div class="rpg-inspector-entry-list">
              ${entries.length ? entries.map(entry => `
                <div class="rpg-inspector-entry">
                  <div class="rpg-inspector-entry-text">${escapeHtml(entry.text || "")}</div>
                  <div class="rpg-inspector-entry-meta">
                    ${escapeHtml(`strength=${entry.strength ?? 0}`)}
                  </div>
                </div>
              `).join("") : _renderInspectorEmpty("No entries")}
            </div>
          </div>
        `;
      }).join("")
    : _renderInspectorEmpty("No actor memory");

  const rumorHtml = worldRumors.length
    ? `
      <div class="rpg-inspector-card">
        <div class="rpg-inspector-card-title">World Rumors</div>
        <div class="rpg-inspector-entry-list">
          ${worldRumors.map(rumor => `
            <div class="rpg-inspector-entry">
              <div class="rpg-inspector-entry-text">${escapeHtml(rumor.text || "")}</div>
              <div class="rpg-inspector-entry-meta">
                ${escapeHtml(`strength=${rumor.strength ?? 0}, reach=${rumor.reach ?? 0}`)}
              </div>
            </div>
          `).join("")}
        </div>
      </div>
    `
    : _renderInspectorEmpty("No world rumors");

  return `
    <div class="rpg-inspector-section">
      <div class="rpg-inspector-section-title">Memory Inspector</div>
      <div class="rpg-inspector-grid">
        <div>${actorHtml}</div>
        <div>${rumorHtml}</div>
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Phase 18.1.C — Visual inspector UI
// ---------------------------------------------------------------------------

export function renderVisualInspector(visualInspector) {
  const payload = visualInspector || {};
  const requests = Array.isArray(payload.requests)
    ? payload.requests
    : Array.isArray(payload.image_requests)
      ? payload.image_requests
      : [];
  const assets = Array.isArray(payload.assets)
    ? payload.assets
    : Array.isArray(payload.visual_assets)
      ? payload.visual_assets
      : [];
  const queueJobs = Array.isArray(payload.queue_jobs) ? payload.queue_jobs : [];
  const manifestAssets = Array.isArray(payload.asset_manifest)
    ? payload.asset_manifest
    : payload.asset_manifest && payload.asset_manifest.assets && typeof payload.asset_manifest.assets === "object"
      ? Object.values(payload.asset_manifest.assets)
      : [];

  const summary = _renderKeyValueList([
    { key: "Requests", value: String(payload.request_count || 0) },
    { key: "Assets", value: String(payload.asset_count || 0) },
    { key: "Queue Jobs", value: String(payload.queue_job_count || 0) },
    { key: "Manifest Assets", value: String(payload.manifest_asset_count || 0) },
  ]);

  const requestHtml = requests.length
    ? requests.map(item => `
      <div class="rpg-inspector-entry">
        <div class="rpg-inspector-entry-text">${escapeHtml(item.request_id || "")}</div>
        <div class="rpg-inspector-entry-meta">${escapeHtml(`${item.kind || ""} \u2022 ${item.target_id || ""} \u2022 ${item.status || ""}`)}</div>
      </div>
    `).join("")
    : _renderInspectorEmpty("No visual requests");

  const assetHtml = assets.length
    ? assets.map(item => `
      <div class="rpg-inspector-entry">
        <div class="rpg-inspector-entry-text">${escapeHtml(item.asset_id || "")}</div>
        <div class="rpg-inspector-entry-meta">${escapeHtml(`${item.kind || ""} \u2022 ${item.target_id || ""} \u2022 ${item.status || ""}`)}</div>
      </div>
    `).join("")
    : _renderInspectorEmpty("No visual assets");

  const queueHtml = queueJobs.length
    ? queueJobs.map(item => `
      <div class="rpg-inspector-entry">
        <div class="rpg-inspector-entry-text">${escapeHtml(item.job_id || "")}</div>
        <div class="rpg-inspector-entry-meta">${escapeHtml(`${item.request_id || ""} \u2022 ${item.status || ""} \u2022 attempts=${item.attempts ?? 0}`)}</div>
      </div>
    `).join("")
    : _renderInspectorEmpty("No queue jobs");

  const manifestHtml = manifestAssets.length
    ? manifestAssets.map(item => `
      <div class="rpg-inspector-entry">
        <div class="rpg-inspector-entry-text">${escapeHtml(item.asset_id || "")}</div>
        <div class="rpg-inspector-entry-meta">${escapeHtml(`${item.filename || ""} \u2022 ${item.mime_type || ""} \u2022 ${item.kind || ""}`)}</div>
      </div>
    `).join("")
    : _renderInspectorEmpty("No manifest assets");

  return `
    <div class="rpg-inspector-section">
      <div class="rpg-inspector-section-title">Visual Inspector</div>
      ${summary}
      <div class="rpg-inspector-grid">
        <div class="rpg-inspector-card">
          <div class="rpg-inspector-card-title">Requests</div>
          <div class="rpg-inspector-entry-list">${requestHtml}</div>
        </div>
        <div class="rpg-inspector-card">
          <div class="rpg-inspector-card-title">Assets</div>
          <div class="rpg-inspector-entry-list">${assetHtml}</div>
        </div>
        <div class="rpg-inspector-card">
          <div class="rpg-inspector-card-title">Queue</div>
          <div class="rpg-inspector-entry-list">${queueHtml}</div>
        </div>
        <div class="rpg-inspector-card">
          <div class="rpg-inspector-card-title">Manifest</div>
          <div class="rpg-inspector-entry-list">${manifestHtml}</div>
        </div>
      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Phase 18.1.E — Session/package panel renderer
// ---------------------------------------------------------------------------

export function renderSessionPackagePanel(sessionData, packageData) {
  const sessionManifest = (sessionData && sessionData.manifest) || {};
  const installedPacks = Array.isArray(sessionData && sessionData.installed_packs)
    ? sessionData.installed_packs
    : Array.isArray(sessionData && sessionData.installedPacks)
      ? sessionData.installedPacks
      : [];
  const packageManifest = (packageData && packageData.package_manifest) || {};

  const packListHtml = installedPacks.length
    ? installedPacks.map(pack => `<div class="rpg-inspector-entry-text">${escapeHtml(pack)}</div>`).join("")
    : _renderInspectorEmpty("No installed packs");

  return `
    <div class="rpg-inspector-section">
      <div class="rpg-inspector-section-title">Session / Package</div>
      <div class="rpg-inspector-grid">
        <div class="rpg-inspector-card">
          <div class="rpg-inspector-card-title">Session Manifest</div>
          ${_renderKeyValueList([
            { key: "ID", value: sessionManifest.id || "" },
            { key: "Title", value: sessionManifest.title || "" },
            { key: "Schema", value: String(sessionManifest.schema_version || "") },
            { key: "Archived", value: String(!!sessionManifest.archived) },
          ])}
        </div>
        <div class="rpg-inspector-card">
          <div class="rpg-inspector-card-title">Installed Packs</div>
          <div class="rpg-inspector-entry-list">
            ${packListHtml}
          </div>
        </div>
        <div class="rpg-inspector-card">
          <div class="rpg-inspector-card-title">Last Export</div>
          ${_renderKeyValueList([
            { key: "Package Kind", value: packageManifest.package_kind || "" },
            { key: "Schema", value: String(packageManifest.schema_version || "") },
            { key: "Source Session", value: packageManifest.source_session_id || "" },
            { key: "Title", value: packageManifest.title || "" },
          ])}
        </div>
      </div>
    </div>
  `;
}

// ---- Conversation inspector ----

export function renderConversationInspector(payload) {
  const container = document.getElementById("rpg-conversation-inspector");
  if (!container) return;

  const activeConvs = Array.isArray(payload?.active_conversations) ? payload.active_conversations : [];
  const recentConvs = Array.isArray(payload?.recent_conversations) ? payload.recent_conversations : [];

  const activeHtml = activeConvs.length
    ? activeConvs.map((conv) => {
        const topic = conv.topic || {};
        const lines = Array.isArray(conv.lines) ? conv.lines : [];
        const lastLines = lines.slice(-3).map((l) =>
          `<div class="inspector-conv-line">${escapeHtml(l.speaker || "?")}: ${escapeHtml(l.text || "")}</div>`
        ).join("");
        return `
          <div class="inspector-conv-card">
            <div class="inspector-conv-header">
              <span class="inspector-conv-id">${escapeHtml(conv.conversation_id || "")}</span>
              <span class="inspector-conv-kind">${escapeHtml(conv.kind || "")}</span>
            </div>
            ${_renderKeyValueList([
              { key: "Topic", value: topic.type || "" },
              { key: "Anchor", value: topic.anchor || "" },
              { key: "Participants", value: (conv.participants || []).join(", ") },
              { key: "Turns", value: String(conv.turn_count || 0) + " / " + String(conv.max_turns || 0) },
            ])}
            <div class="inspector-conv-lines">${lastLines || "<em>No lines yet.</em>"}</div>
          </div>
        `;
      }).join("")
    : `<div class="inspector-empty">No active conversations.</div>`;

  const recentHtml = recentConvs.length
    ? recentConvs.slice(-5).map((conv) => {
        const topic = conv.topic || {};
        return `
          <div class="inspector-conv-card inspector-conv-closed">
            <div class="inspector-conv-header">
              <span class="inspector-conv-id">${escapeHtml(conv.conversation_id || "")}</span>
              <span class="inspector-conv-reason">${escapeHtml(conv.close_reason || "closed")}</span>
            </div>
            ${_renderKeyValueList([
              { key: "Topic", value: topic.type || "" },
              { key: "Participants", value: (conv.participants || []).join(", ") },
            ])}
          </div>
        `;
      }).join("")
    : `<div class="inspector-empty">No recent conversations.</div>`;

  container.innerHTML = `
    <div class="inspector-panel">
      <div class="inspector-header">Conversations</div>
      <div class="inspector-section"><h5>Active</h5>${activeHtml}</div>
      <div class="inspector-section"><h5>Recent</h5>${recentHtml}</div>
    </div>
  `;
}