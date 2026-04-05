/**
 * Phase 10 — RPG Presentation Client.
 *
 * Client-side helper for calling presentation API routes.
 */
export class RPGPresentationClient {
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
      throw new Error(`Presentation API error: ${res.status} at ${path}`);
    }
    return res.json();
  }

  async getScenePresentation(setupPayload, sceneState) {
    return this._post("/api/rpg/presentation/scene", {
      setup_payload: setupPayload,
      scene_state: sceneState,
    });
  }

  async getDialoguePresentation(setupPayload, dialogueState) {
    return this._post("/api/rpg/presentation/dialogue", {
      setup_payload: setupPayload,
      dialogue_state: dialogueState,
    });
  }

  async getSpeakerCards(setupPayload, sceneState) {
    return this._post("/api/rpg/presentation/speakers", {
      setup_payload: setupPayload,
      scene_state: sceneState,
    });
  }
}