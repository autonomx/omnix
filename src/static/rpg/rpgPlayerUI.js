/**
 * Phase 8 — Player UI Components
 *
 * Journal, Codex, Objectives, and Dialogue mode handling for the frontend.
 */

import { RPGPlayerClient } from "./rpgPlayerClient.js";

const playerClient = new RPGPlayerClient();

export async function loadJournal(setupPayload) {
  try {
    const res = await playerClient.getJournal(setupPayload);
    const entries = res.journal_entries || [];
    const el = document.getElementById("rpg-journal");
    if (!el) return;
    el.innerHTML = entries
      .map((e) => `<div class="journal-entry">${e.title || e.entry_id}: ${e.text || ""}</div>`)
      .join("");
    return entries;
  } catch (err) {
    console.error("Failed to load journal:", err);
    return [];
  }
}

export async function loadCodex(setupPayload) {
  try {
    const res = await playerClient.getCodex(setupPayload);
    const codex = res.codex || {};
    const el = document.getElementById("rpg-codex");
    if (!el) return;

    const npcs = Object.values(codex.npcs || {});
    const factions = Object.values(codex.factions || {});
    const locations = Object.values(codex.locations || {});
    const threads = Object.values(codex.threads || {});

    el.innerHTML = `
      <div class="codex-section">
        <h3>NPCs</h3>
        ${npcs.map((n) => `<div class="codex-item">${n.name}</div>`).join("")}
      </div>
      <div class="codex-section">
        <h3>Factions</h3>
        ${factions.map((f) => `<div class="codex-item">${f.name}</div>`).join("")}
      </div>
      <div class="codex-section">
        <h3>Locations</h3>
        ${locations.map((l) => `<div class="codex-item">${l.name}</div>`).join("")}
      </div>
      <div class="codex-section">
        <h3>Threads</h3>
        ${threads.map((t) => `<div class="codex-item">${t.name}</div>`).join("")}
      </div>
    `;
    return codex;
  } catch (err) {
    console.error("Failed to load codex:", err);
    return {};
  }
}

export async function loadObjectives(setupPayload) {
  try {
    const res = await playerClient.getObjectives(setupPayload);
    const list = res.active_objectives || [];
    const el = document.getElementById("rpg-objectives");
    if (!el) return;
    el.innerHTML = list
      .map((o) => `<div class="objective-item">${o.type || o.id} -> ${o.target_id || o.name || ""}</div>`)
      .join("");
    return list;
  } catch (err) {
    console.error("Failed to load objectives:", err);
    return [];
  }
}

export async function handleEnterDialogue(setupPayload, npcId, sceneId) {
  try {
    const res = await playerClient.enterDialogue(setupPayload, npcId, sceneId);
    return {
      setupPayload: res.setup_payload,
      playerState: res.player_state,
    };
  } catch (err) {
    console.error("Failed to enter dialogue:", err);
    return null;
  }
}

export async function handleExitDialogue(setupPayload) {
  try {
    const res = await playerClient.exitDialogue(setupPayload);
    return {
      setupPayload: res.setup_payload,
      playerState: res.player_state,
    };
  } catch (err) {
    console.error("Failed to exit dialogue:", err);
    return null;
  }
}

export async function refreshSidePanels(setupPayload) {
  await Promise.all([
    loadJournal(setupPayload),
    loadCodex(setupPayload),
    loadObjectives(setupPayload),
  ]);
}