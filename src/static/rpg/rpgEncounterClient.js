export class RPGEncounterClient {
  async _post(path, payload) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
    if (!res.ok) {
      throw new Error(`Encounter request failed: ${res.status}`);
    }
    return res.json();
  }

  async start(setupPayload, scene) {
    return this._post("/api/rpg/encounter/start", {
      setup_payload: setupPayload,
      scene,
    });
  }

  async action(setupPayload, actionType, targetId = "") {
    return this._post("/api/rpg/encounter/action", {
      setup_payload: setupPayload,
      action_type: actionType,
      target_id: targetId,
    });
  }

  async npcTurn(setupPayload) {
    return this._post("/api/rpg/encounter/npc_turn", {
      setup_payload: setupPayload,
    });
  }

  async end(setupPayload) {
    return this._post("/api/rpg/encounter/end", {
      setup_payload: setupPayload,
    });
  }
}