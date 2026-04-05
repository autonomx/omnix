/**
 * Phase 8 — Player-Facing API Client
 *
 * Wires frontend to /api/rpg/player/* endpoints for state management.
 */

export class RPGPlayerClient {
  constructor(baseUrl = "") {
    this.baseUrl = baseUrl;
  }

  async _post(path, payload) {
    const res = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
    if (!res.ok) {
      throw new Error(`Player API error: ${res.status} at ${path}`);
    }
    return res.json();
  }

  async getState(setupPayload) {
    return this._post("/api/rpg/player/state", {
      setup_payload: setupPayload,
    });
  }

  async getJournal(setupPayload) {
    return this._post("/api/rpg/player/journal", {
      setup_payload: setupPayload,
    });
  }

  async getCodex(setupPayload) {
    return this._post("/api/rpg/player/codex", {
      setup_payload: setupPayload,
    });
  }

  async getObjectives(setupPayload) {
    return this._post("/api/rpg/player/objectives", {
      setup_payload: setupPayload,
    });
  }

  async enterDialogue(setupPayload, npcId, sceneId) {
    return this._post("/api/rpg/player/dialogue/enter", {
      setup_payload: setupPayload,
      npc_id: npcId,
      scene_id: sceneId,
    });
  }

  async exitDialogue(setupPayload) {
    return this._post("/api/rpg/player/dialogue/exit", {
      setup_payload: setupPayload,
    });
  }

  async buildEncounter(setupPayload, scene) {
    return this._post("/api/rpg/player/encounter", {
      setup_payload: setupPayload,
      scene,
    });
  }
}