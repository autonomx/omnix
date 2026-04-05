export class RPGDialogueClient {
  async _post(path, payload) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
    if (!res.ok) {
      throw new Error(`Dialogue request failed: ${res.status}`);
    }
    return res.json();
  }

  async start(setupPayload, npcId, sceneId) {
    return this._post("/api/rpg/dialogue/start", {
      setup_payload: setupPayload,
      npc_id: npcId,
      scene_id: sceneId,
    });
  }

  async sendMessage(setupPayload, npcId, sceneId, message) {
    return this._post("/api/rpg/dialogue/message", {
      setup_payload: setupPayload,
      npc_id: npcId,
      scene_id: sceneId,
      message,
    });
  }

  async end(setupPayload) {
    return this._post("/api/rpg/dialogue/end", {
      setup_payload: setupPayload,
    });
  }
}