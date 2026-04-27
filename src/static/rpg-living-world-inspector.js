(function () {
  "use strict";

  function safeObj(value) {
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  }

  function safeArr(value) {
    return Array.isArray(value) ? value : [];
  }

  function safeStr(value) {
    return value == null ? "" : String(value);
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
    const conversationState = safeObj(result.conversation_thread_state);
    const conversationThreads = safeArr(conversationState.threads);
    const worldSignals = safeArr(conversationState.world_signals);
    const serviceOfferState = safeObj(result.service_offer_state);
    const offers = safeObj(serviceOfferState.offers);
    const npcGoalState = safeObj(result.npc_goal_state || safeObj(result.ambient_tick_result).npc_goal_state);
    const npcGoals = safeObj(npcGoalState.goals);
    const sceneActivityState = safeObj(result.scene_activity_state || safeObj(safeObj(result.ambient_tick_result).scene_activity_result).scene_activity_state);
    const sceneActivities = safeArr(sceneActivityState.recent);
    const conversation = safeObj(result.conversation_result || result);
    const npcHistoryStateRaw = safeObj(result.npc_history_state || conversation.npc_history_state || safeObj(result.ambient_tick_result).npc_history_state);
    const npcHistoryByNpc = safeObj(npcHistoryStateRaw.by_npc);
    const npcReputationStateRaw = safeObj(result.npc_reputation_state || conversation.npc_reputation_state || safeObj(result.ambient_tick_result).npc_reputation_state);
    const npcReputationByNpc = safeObj(npcReputationStateRaw.by_npc);
    const conversationDirectorState = safeObj(result.conversation_director_state || safeObj(result.ambient_tick_result).conversation_director_state);
    const directorDebug = safeObj(conversationDirectorState.debug);
    const directorIntent = safeObj(directorDebug.selected_intent || conversation.director_intent);
    const dialogueProfile = safeObj(result.dialogue_profile || conversation.dialogue_profile);
    const npcResponseBeat = safeObj(conversation.npc_response_beat);
    const roleplaySource =
      result.roleplay_source ||
      conversation.roleplay_source ||
      npcResponseBeat.roleplay_source ||
      "";
    const biographyRole =
      npcResponseBeat.biography_role ||
      safeStr(dialogueProfile.role) ||
      "";
    const usedFactIds = safeArr(
      result.used_fact_ids ||
      conversation.used_fact_ids ||
      npcResponseBeat.used_fact_ids
    );

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

      ${renderList("NPC Conversation Threads", conversationThreads.slice(-6), (thread) => {
        const beats = safeArr(thread.beats);
        const latest = safeObj(beats[beats.length - 1]);
        return `
          <div class="rpg-debug-row">
            <strong>${escapeHtml(thread.topic || thread.thread_id || "conversation")}</strong>
            <span>${escapeHtml(latest.speaker_name || "")}: ${escapeHtml(latest.line || "")}</span>
            <code>${escapeHtml(thread.status || "active")}</code>
          </div>
        `;
      })}

      ${renderMap("NPC Goals", npcGoals, (npcId, goals) => `
        <div class="rpg-debug-row">
          <strong>${escapeHtml(npcId)}</strong>
          <span>${escapeHtml(safeArr(goals).map((goal) => goal.kind || goal.goal_id).join(", "))}</span>
          <code>${escapeHtml(safeArr(goals).length)} active</code>
        </div>
      `)}

      ${renderList("Recent Scene Activities", sceneActivities.slice(-8), (activity) => `
        <div class="rpg-debug-row">
          <strong>${escapeHtml(activity.npc_name || activity.npc_id || "scene")}</strong>
          <span>${escapeHtml(activity.text || "")}</span>
          <code>${escapeHtml(activity.kind || "activity")} goal=${escapeHtml(activity.goal_kind || "")}</code>
        </div>
      `)}

      ${renderList("World Signals", worldSignals.slice(-8), (signal) => `
        <div class="rpg-debug-row">
          <strong>${escapeHtml(signal.kind || "signal")}</strong>
          <span>${escapeHtml(signal.summary || "")}</span>
          <code>${escapeHtml(signal.topic_id || "")}</code>
        </div>
      `)}

      ${biographyRole || roleplaySource || usedFactIds.length ? `
      <details>
        <summary><strong>NPC Biography Roleplay</strong></summary>
        <div class="rpg-debug-section">
          <div class="rpg-debug-row">
            <strong>NPC Biography Role</strong>
            <span>${escapeHtml(biographyRole)}</span>
          </div>
          <div class="rpg-debug-row">
            <strong>Roleplay Source</strong>
            <span>${escapeHtml(roleplaySource)}</span>
          </div>
          ${usedFactIds.length ? `<div class="rpg-debug-row">
            <strong>Used Fact IDs</strong>
            <span>${usedFactIds.map((id) => escapeHtml(id)).join(", ")}</span>
          </div>` : ""}
        </div>
      </details>
      ` : ""}

      ${Object.keys(npcHistoryByNpc).length ? `
      <details>
        <summary><strong>NPC History</strong></summary>
        <div class="rpg-debug-section">
          ${Object.entries(npcHistoryByNpc).map(([npcId, npcState]) => {
            const entries = safeArr(safeObj(npcState).entries);
            return `
              <div class="rpg-debug-row">
                <strong>${escapeHtml(npcId)}</strong>
                <span>${entries.map((e) => escapeHtml(safeObj(e).summary || safeObj(e).kind || "")).join(" | ")}</span>
                <code>${entries.length} entries</code>
              </div>
            `;
          }).join("")}
        </div>
      </details>
      ` : ""}

      ${Object.keys(npcReputationByNpc).length ? `
      <details>
        <summary><strong>NPC Reputation</strong></summary>
        <div class="rpg-debug-section">
          ${Object.entries(npcReputationByNpc).map(([npcId, rep]) => {
            const r = safeObj(rep);
            return `
              <div class="rpg-debug-row">
                <strong>${escapeHtml(npcId)}</strong>
                <code>fam=${escapeHtml(r.familiarity ?? 0)} trust=${escapeHtml(r.trust ?? 0)} annoy=${escapeHtml(r.annoyance ?? 0)} fear=${escapeHtml(r.fear ?? 0)} resp=${escapeHtml(r.respect ?? 0)}</code>
              </div>
            `;
          }).join("")}
        </div>
      </details>
      ` : ""}

      ${directorIntent && directorIntent.selected ? `
      <details>
        <summary><strong>Conversation Director</strong></summary>
        <div class="rpg-debug-section">
          <div class="rpg-debug-row">
            <strong>Speaker</strong><span>${escapeHtml(directorIntent.speaker_id || "")}</span>
          </div>
          <div class="rpg-debug-row">
            <strong>Listener</strong><span>${escapeHtml(directorIntent.listener_id || "")}</span>
          </div>
          <div class="rpg-debug-row">
            <strong>Topic</strong><span>${escapeHtml(directorIntent.topic_id || "")}</span>
            <code>type=${escapeHtml(directorIntent.topic_type || "")} priority=${escapeHtml(directorIntent.priority ?? 0)}</code>
          </div>
          <div class="rpg-debug-row">
            <strong>Reason</strong><span>${escapeHtml(directorIntent.reason || "")}</span>
          </div>
        </div>
      </details>
      ` : ""}
    `;
  }

  window.RpgLivingWorldInspector = { render };
})();
