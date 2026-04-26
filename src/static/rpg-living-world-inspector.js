(function () {
  "use strict";

  function safeObj(value) {
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  }

  function safeArr(value) {
    return Array.isArray(value) ? value : [];
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function resultRoot(payload) {
    const root = safeObj(payload);
    return safeObj(root.result || root);
  }

  function findOrCreatePanel() {
    const host =
      document.getElementById("rpgInspectorPanel") ||
      document.getElementById("rpg-inspector-panel") ||
      document.getElementById("rpg-top-panels") ||
      document.querySelector("[data-rpg-inspector]") ||
      document.body;

    let panel = document.getElementById("rpgLivingWorldDebugPanel");
    if (!panel) {
      panel = document.createElement("section");
      panel.id = "rpgLivingWorldDebugPanel";
      panel.className = "rpg-living-world-debug-panel";
      host.appendChild(panel);
    }
    return panel;
  }

  function renderList(title, rows, renderRow) {
    rows = safeArr(rows);
    if (!rows.length) {
      return `<details class="rpg-debug-section"><summary>${escapeHtml(title)} (0)</summary><div class="rpg-debug-empty">None</div></details>`;
    }
    return `
      <details class="rpg-debug-section" open>
        <summary>${escapeHtml(title)} (${rows.length})</summary>
        <div class="rpg-debug-list">
          ${rows.map(renderRow).join("")}
        </div>
      </details>
    `;
  }

  function renderMap(title, obj, renderRow) {
    obj = safeObj(obj);
    const entries = Object.entries(obj);
    if (!entries.length) {
      return `<details class="rpg-debug-section"><summary>${escapeHtml(title)} (0)</summary><div class="rpg-debug-empty">None</div></details>`;
    }
    return `
      <details class="rpg-debug-section">
        <summary>${escapeHtml(title)} (${entries.length})</summary>
        <div class="rpg-debug-list">
          ${entries.map(([key, value]) => renderRow(key, safeObj(value))).join("")}
        </div>
      </details>
    `;
  }

  function render(payload) {
    const result = resultRoot(payload);
    const locationState = safeObj(result.location_state);
    const serviceResult = safeObj(result.service_result || safeObj(result.turn_contract).service_result);
    const travelResult = safeObj(result.travel_result);
    const currentLocation = safeObj(locationState.current_location);
    const currentLocationId =
      locationState.current_location_id ||
      result.current_location_id ||
      serviceResult.current_location_id ||
      travelResult.to_location_id ||
      travelResult.from_location_id ||
      "";

    const txHistory = safeArr(result.transaction_history || safeObj(result.living_world_debug).transaction_history);
    const memoryState = safeObj(result.memory_state);
    const serviceMemories = safeArr(memoryState.service_memories);
    const socialMemories = safeArr(memoryState.social_memories);
    const relationshipState = safeObj(result.relationship_state);
    const emotionState = safeObj(result.npc_emotion_state);
    const journalEntries = safeArr(safeObj(result.journal_state).entries);
    const worldEvents = safeArr(safeObj(result.world_event_state).events);
    const serviceOfferState = safeObj(result.service_offer_state);
    const offers = safeObj(serviceOfferState.offers);

    const panel = findOrCreatePanel();
    panel.innerHTML = `
      <div class="rpg-debug-header">
        <strong>Living World Debug</strong>
        <span>${escapeHtml(currentLocation.name || currentLocationId || "unknown location")}</span>
      </div>

      ${renderMap("Service Stock / Offers", offers, (key, offer) => `
        <div class="rpg-debug-row">
          <strong>${escapeHtml(key)}</strong>
          <span>${escapeHtml(offer.label || offer.offer_id || "")}</span>
          <code>stock=${escapeHtml(offer.stock_remaining ?? offer.stock ?? "")}</code>
        </div>
      `)}

      ${renderList("Transactions", txHistory, (tx) => `
        <div class="rpg-debug-row">
          <strong>${escapeHtml(tx.transaction_id || tx.id || "transaction")}</strong>
          <span>${escapeHtml(tx.status || "")}</span>
          <code>${escapeHtml(tx.offer_id || tx.service_kind || "")}</code>
        </div>
      `)}

      ${renderList("Service Memories", serviceMemories, (memory) => `
        <div class="rpg-debug-row">
          <strong>${escapeHtml(memory.owner_name || memory.owner_id || "NPC")}</strong>
          <span>${escapeHtml(memory.summary || "")}</span>
        </div>
      `)}

      ${renderList("Social Memories", socialMemories, (memory) => `
        <div class="rpg-debug-row">
          <strong>${escapeHtml(memory.owner_name || memory.owner_id || "NPC")}</strong>
          <span>${escapeHtml(memory.summary || "")}</span>
        </div>
      `)}

      ${renderMap("Relationships", relationshipState, (key, rel) => {
        const axes = safeObj(rel.axes);
        return `
          <div class="rpg-debug-row">
            <strong>${escapeHtml(key)}</strong>
            <code>trust=${escapeHtml(axes.trust ?? 0)} familiarity=${escapeHtml(axes.familiarity ?? 0)} annoyance=${escapeHtml(axes.annoyance ?? 0)}</code>
          </div>
        `;
      })}

      ${renderMap("NPC Emotions", emotionState, (key, emo) => `
        <div class="rpg-debug-row">
          <strong>${escapeHtml(key)}</strong>
          <code>${escapeHtml(emo.dominant_emotion || "neutral")} v=${escapeHtml(emo.valence ?? 0)} a=${escapeHtml(emo.arousal ?? 0)}</code>
        </div>
      `)}

      ${renderList("Journal", journalEntries, (entry) => `
        <div class="rpg-debug-row">
          <strong>${escapeHtml(entry.title || entry.entry_id || "journal")}</strong>
          <span>${escapeHtml(entry.summary || "")}</span>
          <code>${escapeHtml(entry.status || "")}</code>
        </div>
      `)}

      ${renderList("World Events", worldEvents.slice(-8), (event) => `
        <div class="rpg-debug-row">
          <strong>${escapeHtml(event.title || event.kind || "event")}</strong>
          <span>${escapeHtml(event.summary || "")}</span>
          <code>${escapeHtml(event.kind || "")}</code>
        </div>
      `)}
    `;
  }

  window.RpgLivingWorldInspector = { render };
})();
