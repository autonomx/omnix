/**
 * Phase 9.0 — Inventory client for RPG frontend.
 * Communicates with the inventory API endpoints.
 */
export class RPGInventoryClient {
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
      throw new Error(`Inventory API error: ${res.status} at ${path}`);
    }
    return res.json();
  }

  async getInventory(setupPayload) {
    return this._post("/api/rpg/player/inventory", {
      setup_payload: setupPayload,
    });
  }

  async useItem(setupPayload, itemId) {
    return this._post("/api/rpg/player/inventory/use", {
      setup_payload: setupPayload,
      item_id: itemId,
    });
  }

  async getItemRegistry() {
    return this._post("/api/rpg/player/inventory/registry", {});
  }
}