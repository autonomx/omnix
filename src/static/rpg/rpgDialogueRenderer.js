function safeArray(v) {
  return Array.isArray(v) ? v : [];
}

function esc(str) {
  const s = String(str ?? "");
  const map = { "&": "amp", "<": "lt", ">": "gt", '"': "quot", "'": "#39" };
  return s.replace(/[&<>"']/g, (c) => "&" + map[c] + ";");
}

export function renderDialogueState(dialogueState) {
  const root = document.getElementById("rpg-dialogue-history");
  if (!root) return;
  const history = safeArray(dialogueState?.history);
  root.innerHTML = history.map(item => `
    <div class="rpg-dialogue-line rpg-dialogue-${esc(item.speaker)}">
      <div class="rpg-dialogue-speaker">${esc(item.speaker)}</div>
      <div class="rpg-dialogue-text">${esc(item.text)}</div>
    </div>
  `).join("");
}

export function renderSuggestedReplies(dialogueState, onSelect) {
  const root = document.getElementById("rpg-dialogue-suggestions");
  if (!root) return;
  const replies = safeArray(dialogueState?.suggested_replies);
  root.innerHTML = "";
  replies.forEach((text) => {
    const btn = document.createElement("button");
    btn.className = "rpg-dialogue-suggestion";
    btn.textContent = text;
    btn.onclick = () => onSelect && onSelect(text);
    root.appendChild(btn);
  });
}

export function appendDialogueReply(reply) {
  const root = document.getElementById("rpg-dialogue-latest-reply");
  if (!root) return;
  root.innerHTML = `
    <div class="rpg-dialogue-reply-text">${esc(reply?.reply_text || "")}</div>
    <div class="rpg-dialogue-reply-meta">${esc(reply?.tone || "neutral")} &middot; ${esc(reply?.intent || "respond")}</div>
  `;
}

export function clearDialogueUI() {
  const ids = [
    "rpg-dialogue-history",
    "rpg-dialogue-suggestions",
    "rpg-dialogue-latest-reply",
  ];
  ids.forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = "";
  });
}

// ---- Phase 18.1.D — GM operations panel renderer ----

function _button(action, label, extra = "") {
  return `<button class="rpg-gm-action-btn" data-action="${action}" ${extra}>${label}</button>`;
}

export function renderGmOperationsPanel(gmTooling) {
  const payload = gmTooling || {};
  const operations = payload.operations || {};
  return `
    <div class="rpg-inspector-section">
      <div class="rpg-inspector-section-title">GM Operations</div>
      <div class="rpg-gm-ops-grid">
        ${_button("queue-normalize", "Normalize Queue")}
        ${_button("queue-run-one", "Run One Queue Job")}
        ${_button("queue-prune", "Prune Queue")}
        ${_button("asset-cleanup", "Cleanup Visual Assets")}
        ${_button("memory-decay", "Decay Memory")}
        ${_button("memory-reinforce", "Reinforce Memory")}
        ${_button("session-export", "Export Package")}
        ${_button("session-import", "Import Package")}
      </div>
      <div class="rpg-gm-ops-meta">
        <div>Visual route: ${operations.visual_inspector_route || ""}</div>
        <div>Memory route: ${operations.memory_decay_route || ""}</div>
      </div>
    </div>
  `;
}

// ---- Phase 18.1.F wiring — Inspector refresh and GM action handlers ----

import {
  cleanupVisualAssets,
  decayMemory,
  exportSessionPackage,
  fetchGmTooling,
  fetchMemoryInspector,
  fetchVisualInspector,
  importSessionPackage,
  normalizeVisualQueue,
  pruneVisualQueue,
  reinforceMemory,
  runOneVisualQueueJob,
} from "./rpgDialogueClient.js";
import {
  renderInspectorError,
  renderMemoryInspector,
  renderSessionPackagePanel,
  renderVisualInspector,
} from "./rpgPresentationRenderer.js";

export async function refreshInspectorPanels({ setupPayload, sessionData, packageData, rootEl }) {
  if (rootEl) {
    rootEl.innerHTML = `<div class="rpg-inspector-loading">Loading&hellip;</div>`;
  }

  const [visualRes, memoryRes, gmRes] = await Promise.all([
    fetchVisualInspector(setupPayload),
    fetchMemoryInspector(setupPayload),
    fetchGmTooling(setupPayload),
  ]);

  rootEl.innerHTML = [
    visualRes && visualRes.ok === false
      ? renderInspectorError("Visual", visualRes.error)
      : "",
    renderVisualInspector(visualRes.visual_inspector || {}),
    memoryRes && memoryRes.ok === false
      ? renderInspectorError("Memory", memoryRes.error)
      : "",
    renderMemoryInspector(memoryRes.memory_inspector || {}),
    gmRes && gmRes.ok === false
      ? renderInspectorError("GM", gmRes.error)
      : "",
    renderGmOperationsPanel(gmRes.gm_tooling || {}),
    renderSessionPackagePanel(sessionData || {}, packageData || {}),
  ].join("");
}

export function attachGmToolingHandlers({ rootEl, getContext, onPackageExported, onPackageImported, refresh }) {
  rootEl.addEventListener("click", async (event) => {
    const btn = event.target.closest("[data-action]");
    if (!btn) return;

    const action = btn.getAttribute("data-action");
    const ctx = getContext();
    const setupPayload = ctx.setupPayload || {};
    const sessionId = ctx.sessionId || "";
    const sessionData = ctx.sessionData || {};

    btn.disabled = true;
    try {
      if (action === "queue-normalize") {
        await normalizeVisualQueue();
      } else if (action === "queue-run-one") {
        await runOneVisualQueueJob(300);
      } else if (action === "queue-prune") {
        await pruneVisualQueue(200);
      } else if (action === "asset-cleanup") {
        await cleanupVisualAssets(sessionId);
      } else if (action === "memory-decay") {
        await decayMemory(setupPayload);
      } else if (action === "memory-reinforce") {
        const actorId = window.prompt("Actor ID to reinforce?");
        const text = window.prompt("Memory text?");
        if (actorId && text) {
          await reinforceMemory(setupPayload, actorId, text, 0.2);
        }
      } else if (action === "session-export") {
        const result = await exportSessionPackage(sessionData);
        if (result && result.package && typeof onPackageExported === "function") {
          onPackageExported(result.package);
        }
      } else if (action === "session-import") {
        const raw = window.prompt("Paste package JSON");
        if (raw) {
          let parsed = null;
          try {
            parsed = JSON.parse(raw);
          } catch (_err) {
            window.alert("Invalid JSON package payload");
          }
          if (parsed) {
            const result = await importSessionPackage(parsed);
            if (result && result.session && typeof onPackageImported === "function") {
              onPackageImported(result.session);
            }
          }
        }
      }
    } finally {
      btn.disabled = false;
      if (typeof refresh === "function") {
        await refresh();
      }
    }
  });
}
