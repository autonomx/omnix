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

// ---- Phase 18.1.A — Frontend client helpers ----

async function _postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  let data = {};
  try {
    data = await response.json();
  } catch (_err) {
    data = { ok: false, error: "invalid_json_response" };
  }
  if (!response.ok && !data.error) {
    data.error = `http_${response.status}`;
  }
  return data;
}

export async function fetchVisualInspector(setupPayload) {
  return _postJson("/api/rpg/visual/inspector", {
    setup_payload: setupPayload || {},
  });
}

export async function fetchMemoryInspector(setupPayload) {
  return _postJson("/api/rpg/memory/inspector", {
    setup_payload: setupPayload || {},
  });
}

export async function fetchGmTooling(setupPayload) {
  return _postJson("/api/rpg/gm/tooling", {
    setup_payload: setupPayload || {},
  });
}

export async function reinforceMemory(setupPayload, actorId, text, amount = 0.2) {
  return _postJson("/api/rpg/memory/reinforce", {
    setup_payload: setupPayload || {},
    actor_id: actorId || "",
    text: text || "",
    amount,
  });
}

export async function decayMemory(setupPayload) {
  return _postJson("/api/rpg/memory/decay", {
    setup_payload: setupPayload || {},
  });
}

export async function normalizeVisualQueue() {
  return _postJson("/api/rpg/visual/queue/normalize", {});
}

export async function runOneVisualQueueJob(leaseSeconds = 300) {
  return _postJson("/api/rpg/visual/queue/run_one", {
    lease_seconds: leaseSeconds,
  });
}

export async function pruneVisualQueue(keepLast = 200) {
  return _postJson("/api/rpg/visual/queue/prune", {
    keep_last: keepLast,
  });
}

export async function cleanupVisualAssets(sessionId) {
  return _postJson("/api/rpg/visual/assets/cleanup", {
    session_id: sessionId || "",
  });
}

export async function exportSessionPackage(session) {
  return _postJson("/api/rpg/session/export_package", {
    session: session || {},
  });
}

export async function importSessionPackage(pkg) {
  return _postJson("/api/rpg/session/import_package", {
    package: pkg || {},
  });
}
