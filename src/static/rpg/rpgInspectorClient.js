/**
 * Phase 8.4.6 — RPG Inspector Client
 *
 * API client for the RPG inspection layer.
 * Provides methods for timeline, tick diff, NPC reasoning, and GM controls.
 */

class RPGInspectorClient {
  async _post(path, payload) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
    if (!res.ok) {
      throw new Error(`Inspector request failed: ${res.status}`);
    }
    return res.json();
  }

  async getTimeline(setupPayload) {
    return this._post("/api/rpg/inspect/timeline", {
      setup_payload: setupPayload,
    });
  }

  async getTimelineTick(setupPayload, tick) {
    return this._post("/api/rpg/inspect/timeline_tick", {
      setup_payload: setupPayload,
      tick,
    });
  }

  async getTickDiff(beforeState, afterState) {
    return this._post("/api/rpg/inspect/tick_diff", {
      before_state: beforeState,
      after_state: afterState,
    });
  }

  async getNpcReasoning(setupPayload, npcId) {
    return this._post("/api/rpg/inspect/npc_reasoning", {
      setup_payload: setupPayload,
      npc_id: npcId,
    });
  }

  async forceNpcGoal(setupPayload, npcId, goal) {
    return this._post("/api/rpg/gm/force_npc_goal", {
      setup_payload: setupPayload,
      npc_id: npcId,
      goal,
    });
  }

  async forceFactionTrend(setupPayload, factionId, trendPatch) {
    return this._post("/api/rpg/gm/force_faction_trend", {
      setup_payload: setupPayload,
      faction_id: factionId,
      trend_patch: trendPatch,
    });
  }

  async addDebugNote(setupPayload, note) {
    return this._post("/api/rpg/gm/debug_note", {
      setup_payload: setupPayload,
      note,
    });
  }
}