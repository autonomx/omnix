/**
 * Phase 8.4.6 — RPG Inspector Renderer
 *
 * Renders the inspector panels: timeline, tick view, NPC reasoning, and GM audit.
 */

function esc(str) {
  const s = String(str ?? "");
  return s.replace(/&/g, "\u0026amp;").replace(/</g, "\u0026lt;").replace(/>/g, "\u0026gt;").replace(/"/g, "\u0026quot;").replace(/'/g, "\u0026#39;");
}

function safeArray(v) {
  return Array.isArray(v) ? v : [];
}

function safeObj(v) {
  return v && typeof v === "object" ? v : {};
}

export function renderInspectorShell(isOpen) {
  const root = document.getElementById("rpg-inspector-shell");
  if (!root) return;
  root.style.display = isOpen ? "grid" : "none";
  root.dataset.loading = "false";
}

export function setInspectorLoading(isLoading) {
  const root = document.getElementById("rpg-inspector-shell");
  if (!root) return;
  root.dataset.loading = isLoading ? "true" : "false";
}

export function renderTimelinePanel(timeline, latestDiff, onSelectTick) {
  setInspectorLoading(true);
  const root = document.getElementById("rpg-inspector-timeline");
  if (!root) { setInspectorLoading(false); return; }

  const t = safeObj(timeline);
  const snaps = safeArray(t.snapshots);
  const recentConsequences = safeArray(t.recent_world_consequences);
  const diff = safeObj(latestDiff);

  root.innerHTML = [
    '<div class="rpg-inspector-section">',
    '  <div class="rpg-inspector-title">Timeline</div>',
    '  <div class="rpg-inspector-meta">Current tick: ' + esc(t.current_tick ?? "0") + '</div>',
    '  <div class="rpg-inspector-meta">Snapshots: ' + esc(t.snapshot_count ?? "0") + '</div>',
    '</div>',
    '<div class="rpg-inspector-section">',
    '  <div class="rpg-inspector-title">Latest Diff</div>',
    '  <div class="rpg-inspector-meta">Tick ' + esc(diff.tick_before ?? "\u2014") + " \u2192 " + esc(diff.tick_after ?? "\u2014") + '</div>',
    '  <div class="rpg-inspector-meta">Event \u0394: ' + esc(safeObj(diff.summary).event_delta ?? "0") + '</div>',
    '  <div class="rpg-inspector-meta">Consequence \u0394: ' + esc(safeObj(diff.summary).consequence_delta ?? "0") + '</div>',
    '  <div class="rpg-inspector-meta">NPC changes: ' + esc(safeObj(diff.summary).npc_changes ?? "0") + '</div>',
    '</div>',
    '<div class="rpg-inspector-section">',
    '  <div class="rpg-inspector-title">Recent Ticks</div>',
    '  <div id="rpg-inspector-timeline-list"></div>',
    '</div>',
    '<div class="rpg-inspector-section">',
    '  <div class="rpg-inspector-title">Recent World Consequences</div>',
    '  <div>',
    ...recentConsequences.map(item => {
      const npcHtml = item.npc_id 
        ? ' <button class="rpg-inspector-npc-quick-link" data-npc="' + esc(item.npc_id) + '">Inspect NPC</button>'
        : '';
      return '<div class="rpg-inspector-row">' +
        '<div><strong>' + esc(item.type || "consequence") + '</strong>' + npcHtml + '</div>' +
        '<div>' + esc(item.summary || "") + '</div>' +
        '</div>';
    }),
    '  </div>',
    '</div>',
  ].join("\n");

  // Bind quick NPC inspect links
  root.querySelectorAll(".rpg-inspector-npc-quick-link").forEach(btn => {
    btn.onclick = () => {
      const npcId = btn.dataset.npc;
      if (npcId && typeof onSelectTick === "function") {
        // Trigger inspect NPC via a custom event that RPGInspectorUI can listen for
        window.dispatchEvent(new CustomEvent("rpg-inspector:inspectNpc", { detail: npcId }));
      }
    };
  });

  const list = document.getElementById("rpg-inspector-timeline-list");
  if (!list) { setInspectorLoading(false); return; }

  list.innerHTML = "";
  snaps.slice().reverse().forEach((snap) => {
    const btn = document.createElement("button");
    btn.className = "rpg-inspector-tick-btn";
    if (snap.tick === (timeline?._selectedTick ?? null)) {
      btn.classList.add("active");
    }
    btn.textContent = "Tick " + snap.tick;
    btn.onclick = () => onSelectTick && onSelectTick(snap.tick);
    list.appendChild(btn);
  });
  setInspectorLoading(false);
}

export function renderTickView(tickView) {
  const root = document.getElementById("rpg-inspector-tick-view");
  if (!root) return;

  const tv = safeObj(tickView);
  const snapshot = safeObj(tv.snapshot);

  root.innerHTML = [
    '<div class="rpg-inspector-title">Tick View</div>',
    '<div class="rpg-inspector-meta">Requested tick: ' + esc(tv.requested_tick ?? "0") + '</div>',
    '<div class="rpg-inspector-meta">Found: ' + esc(tv.found ? "yes" : "no") + '</div>',
    '<pre class="rpg-inspector-pre">' + esc(JSON.stringify(snapshot, null, 2)) + '</pre>',
  ].join("\n");
}

export function renderNpcReasoning(npcReasoning) {
  const root = document.getElementById("rpg-inspector-npc-reasoning");
  if (!root) return;
  const data = safeObj(npcReasoning);
  const npc = safeObj(data.npc);
  const reasoning = safeObj(data.reasoning);
  const why = safeObj(data.why);

  root.innerHTML = [
    '<div class="rpg-inspector-title">NPC Reasoning</div>',
    '<div class="rpg-inspector-meta"><strong>' + esc(npc.name || npc.npc_id || "NPC") + '</strong></div>',
    '<div class="rpg-inspector-meta">Role: ' + esc(npc.role || "") + '</div>',
    '<div class="rpg-inspector-meta">Faction: ' + esc(npc.faction_id || "") + '</div>',
    '<div class="rpg-inspector-meta">Location: ' + esc(npc.location_id || "") + '</div>',
    '<div class="rpg-inspector-subtitle">Why</div>',
    '<pre class="rpg-inspector-pre">' + esc(JSON.stringify(why, null, 2)) + '</pre>',
    '<div class="rpg-inspector-subtitle">Top Goals</div>',
    '<pre class="rpg-inspector-pre">' + esc(JSON.stringify(reasoning.top_goals || [], null, 2)) + '</pre>',
    '<div class="rpg-inspector-subtitle">Recent Memories</div>',
    '<pre class="rpg-inspector-pre">' + esc(JSON.stringify(reasoning.recent_memories || [], null, 2)) + '</pre>',
    '<div class="rpg-inspector-subtitle">Last Decision</div>',
    '<pre class="rpg-inspector-pre">' + esc(JSON.stringify(reasoning.last_decision || {}, null, 2)) + '</pre>',
  ].join("\n");
}

export function renderGmAudit(debugMeta) {
  const root = document.getElementById("rpg-inspector-gm-audit");
  if (!root) return;
  const audit = safeArray(safeObj(debugMeta).gm_audit);
  const notes = safeArray(safeObj(debugMeta).gm_notes);

  const actionsHtml = audit.slice().reverse().map(item => {
    return '<div class="rpg-inspector-row">' +
      '<div><strong>' + esc(item.action || "action") + '</strong></div>' +
      '<div>' + esc(JSON.stringify(item)) + '</div>' +
      '</div>';

  });

  const notesHtml = notes.slice().reverse().map(item => {
    return '<div class="rpg-inspector-row">' + esc(item.note || "") + '</div>';
  });

  root.innerHTML = [
    '<div class="rpg-inspector-title">GM Audit</div>',
    '<div class="rpg-inspector-subtitle">Actions</div>',
    ...actionsHtml,
    '<div class="rpg-inspector-subtitle">Notes</div>',
    ...notesHtml,
  ].join("\n");
}

/* ─── Inventory helpers (Phase 9) ─── */

function numOrZero(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function renderInventoryStackList(items, emptyLabel) {
  emptyLabel = emptyLabel || "None";
  var list = safeArray(items);
  if (!list.length) {
    return '<div class="rpg-inspector-muted">' + esc(emptyLabel) + '</div>';
  }
  return '<div class="rpg-inspector-kv-list">' +
    list.map(function(item) {
      return '<div class="rpg-inspector-kv-row">' +
        '<span class="rpg-inspector-kv-key">' + esc(item.name || item.item_id || "item") + '</span>' +
        '<span class="rpg-inspector-kv-value">x' + numOrZero(item.qty || 1) + '</span>' +
        '</div>';
    }).join("") +
    '</div>';
}

function renderCurrencyMap(currency) {
  var map = safeObj(currency);
  var keys = Object.keys(map).sort();
  if (!keys.length) {
    return '<div class="rpg-inspector-muted">None</div>';
  }
  return '<div class="rpg-inspector-kv-list">' +
    keys.map(function(key) {
      return '<div class="rpg-inspector-kv-row">' +
        '<span class="rpg-inspector-kv-key">' + esc(key) + '</span>' +
        '<span class="rpg-inspector-kv-value">' + numOrZero(map[key]) + '</span>' +
        '</div>';
    }).join("") +
    '</div>';
}

function renderEquipmentMap(equipment) {
  var map = safeObj(equipment);
  var keys = Object.keys(map).sort();
  if (!keys.length) {
    return '<div class="rpg-inspector-muted">None</div>';
  }
  return '<div class="rpg-inspector-kv-list">' +
    keys.map(function(slot) {
      var item = safeObj(map[slot]);
      return '<div class="rpg-inspector-kv-row">' +
        '<span class="rpg-inspector-kv-key">' + esc(slot) + '</span>' +
        '<span class="rpg-inspector-kv-value">' + esc(item.name || item.item_id || "empty") + '</span>' +
        '</div>';
    }).join("") +
    '</div>';
}

function renderInventorySummaryCard(summary, title) {
  title = title || "Inventory Summary";
  var s = safeObj(summary);
  return '<div class="rpg-inspector-subcard">' +
    '<div class="rpg-inspector-subcard-title">' + esc(title) + '</div>' +
    '<div class="rpg-inspector-kv-list">' +
    '<div class="rpg-inspector-kv-row">' +
      '<span class="rpg-inspector-kv-key">Slots Used</span>' +
      '<span class="rpg-inspector-kv-value">' + numOrZero(s.slots_used) + '</span>' +
    '</div>' +
    '<div class="rpg-inspector-kv-row">' +
      '<span class="rpg-inspector-kv-key">Capacity</span>' +
      '<span class="rpg-inspector-kv-value">' + numOrZero(s.capacity) + '</span>' +
    '</div>' +
    '<div class="rpg-inspector-kv-row">' +
      '<span class="rpg-inspector-kv-key">Total Item Qty</span>' +
      '<span class="rpg-inspector-kv-value">' + numOrZero(s.total_item_qty) + '</span>' +
    '</div>' +
    '<div class="rpg-inspector-kv-row">' +
      '<span class="rpg-inspector-kv-key">Last Loot Count</span>' +
      '<span class="rpg-inspector-kv-value">' + numOrZero(s.last_loot_count) + '</span>' +
    '</div>' +
    '</div></div>';
}

function renderInventoryDeltaCard(beforeInventory, afterInventory, changedKeys) {
  var beforeInv = safeObj(beforeInventory);
  var afterInv = safeObj(afterInventory);
  var keys = safeArray(changedKeys);
  var changedLabel = keys.length ? keys.join(", ") : "none";

  return '<div class="rpg-inspector-card">' +
    '<div class="rpg-inspector-card-header">' +
      '<h4>Inventory Delta</h4>' +
      '<span class="rpg-inspector-badge">' + esc(changedLabel) + '</span>' +
    '</div>' +
    '<div class="rpg-inspector-diff-grid">' +
      '<div class="rpg-inspector-subcard">' +
        '<div class="rpg-inspector-subcard-title">Before</div>' +
        '<div class="rpg-inspector-section-label">Items</div>' +
        renderInventoryStackList(beforeInv.items, "No items") +
        '<div class="rpg-inspector-section-label">Equipment</div>' +
        renderEquipmentMap(beforeInv.equipment) +
        '<div class="rpg-inspector-section-label">Currency</div>' +
        renderCurrencyMap(beforeInv.currency) +
        '<div class="rpg-inspector-section-label">Last Loot</div>' +
        renderInventoryStackList(beforeInv.last_loot, "No recent loot") +
      '</div>' +
      '<div class="rpg-inspector-subcard">' +
        '<div class="rpg-inspector-subcard-title">After</div>' +
        '<div class="rpg-inspector-section-label">Items</div>' +
        renderInventoryStackList(afterInv.items, "No items") +
        '<div class="rpg-inspector-section-label">Equipment</div>' +
        renderEquipmentMap(afterInv.equipment) +
        '<div class="rpg-inspector-section-label">Currency</div>' +
        renderCurrencyMap(afterInv.currency) +
        '<div class="rpg-inspector-section-label">Last Loot</div>' +
        renderInventoryStackList(afterInv.last_loot, "No recent loot") +
      '</div>' +
    '</div></div>';
}

function renderTimelineRow(row, isSelected) {
  isSelected = isSelected || false;
  var timelineRow = row || {};
  var sandboxSummary = timelineRow.sandbox_summary || {};
  var inventorySummary = timelineRow.inventory_summary || {};

  return '<div class="rpg-inspector-tick-row' + (isSelected ? " selected" : "") + '" data-tick="' + Number(timelineRow.tick || 0) + '">' +
    '<div class="rpg-inspector-tick-main">' +
      '<div class="rpg-inspector-tick-title">Tick ' + Number(timelineRow.tick || 0) + '</div>' +
      '<div class="rpg-inspector-tick-meta">' +
        '<span>Events: ' + Number(timelineRow.event_count || 0) + '</span>' +
        '<span>Consequences: ' + Number(timelineRow.consequence_count || 0) + '</span>' +
        '<span>Inv: ' + Number(inventorySummary.slots_used || 0) + '/' + Number(inventorySummary.capacity || 0) + '</span>' +
        '<span>Qty: ' + Number(inventorySummary.total_item_qty || 0) + '</span>' +
      '</div>' +
    '</div>' +
  '</div>';
}

function renderTickDiffPanel(diffPayload) {
  var diff = diffPayload || {};
  var summary = diff.summary || {};
  var socialKeysChanged = Array.isArray(diff.social_keys_changed) ? diff.social_keys_changed : [];
  var sandboxKeysChanged = Array.isArray(diff.sandbox_keys_changed) ? diff.sandbox_keys_changed : [];
  var playerKeysChanged = Array.isArray(diff.player_keys_changed) ? diff.player_keys_changed : [];
  var inventoryKeysChanged = Array.isArray(diff.inventory_keys_changed) ? diff.inventory_keys_changed : [];
  var inventoryBefore = diff.inventory_before || {};
  var inventoryAfter = diff.inventory_after || {};

  return '<div class="rpg-inspector-diff-panel">' +
    '<div class="rpg-inspector-card">' +
      '<div class="rpg-inspector-card-header">' +
        '<h4>Tick Diff</h4>' +
      '</div>' +
      '<div class="rpg-inspector-meta">Tick ' + esc(diff.tick_before ?? "\u2014") + ' \u2192 ' + esc(diff.tick_after ?? "\u2014") + '</div>' +
      '<div class="rpg-inspector-chip-row">' +
        '<span class="rpg-inspector-chip">Events \u0394 ' + Number(summary.event_delta || 0) + '</span>' +
        '<span class="rpg-inspector-chip">Consequences \u0394 ' + Number(summary.consequence_delta || 0) + '</span>' +
        '<span class="rpg-inspector-chip">NPC Changes ' + Number(summary.npc_changes || 0) + '</span>' +
        '<span class="rpg-inspector-chip">Inventory Before ' + Number(summary.inventory_item_kinds_before || 0) + '</span>' +
        '<span class="rpg-inspector-chip">Inventory After ' + Number(summary.inventory_item_kinds_after || 0) + '</span>' +
      '</div>' +
    '</div>' +
    '<div class="rpg-inspector-card">' +
      '<div class="rpg-inspector-card-header">' +
        '<h4>Changed Domains</h4>' +
      '</div>' +
      '<div class="rpg-inspector-chip-row">' +
        socialKeysChanged.map(function(key) { return '<span class="rpg-inspector-chip">' + esc(key) + '</span>'; }).join("") +
        sandboxKeysChanged.map(function(key) { return '<span class="rpg-inspector-chip">' + esc(key) + '</span>'; }).join("") +
        playerKeysChanged.map(function(key) { return '<span class="rpg-inspector-chip">' + esc(key) + '</span>'; }).join("") +
      '</div>' +
    '</div>' +
    renderInventoryDeltaCard(inventoryBefore, inventoryAfter, inventoryKeysChanged) +
  '</div>';
}

function renderTimelineRowDiff(rowDiff) {
  var diff = rowDiff || {};
  var sandboxBefore = diff.sandbox_before || {};
  var sandboxAfter = diff.sandbox_after || {};
  var inventoryBefore = diff.inventory_before || {};
  var inventoryAfter = diff.inventory_after || {};

  return '<div class="rpg-inspector-row-diff">' +
    '<div class="rpg-inspector-card">' +
      '<div class="rpg-inspector-card-header">' +
        '<h4>Row Diff</h4>' +
      '</div>' +
      '<div class="rpg-inspector-chip-row">' +
        '<span class="rpg-inspector-chip">Events \u0394 ' + Number(diff.event_delta || 0) + '</span>' +
        '<span class="rpg-inspector-chip">Consequences \u0394 ' + Number(diff.consequence_delta || 0) + '</span>' +
      '</div>' +
    '</div>' +
    '<div class="rpg-inspector-diff-grid">' +
      '<div class="rpg-inspector-subcard">' +
        '<div class="rpg-inspector-subcard-title">Sandbox Before</div>' +
        '<pre class="rpg-inspector-json">' + esc(JSON.stringify(sandboxBefore, null, 2)) + '</pre>' +
      '</div>' +
      '<div class="rpg-inspector-subcard">' +
        '<div class="rpg-inspector-subcard-title">Sandbox After</div>' +
        '<pre class="rpg-inspector-json">' + esc(JSON.stringify(sandboxAfter, null, 2)) + '</pre>' +
      '</div>' +
    '</div>' +
    '<div class="rpg-inspector-diff-grid">' +
      renderInventorySummaryCard(inventoryBefore, "Inventory Before") +
      renderInventorySummaryCard(inventoryAfter, "Inventory After") +
    '</div>' +
  '</div>';
}

function renderCausalTrace(tracePayload) {
  var trace = tracePayload || {};
  var events = Array.isArray(trace.events) ? trace.events : [];

  return '<div class="rpg-inspector-trace">' +
    (events.length ? events.map(function(event) {
      var loot = Array.isArray(event.loot) ? event.loot : [];
      var isInventoryEvent = String(event.origin || "") === "inventory" || String(event.type || "") === "encounter_loot_awarded";
      return '<div class="rpg-inspector-trace-event' + (isInventoryEvent ? " inventory-event" : "") + '">' +
        '<div class="rpg-inspector-trace-header">' +
          '<span class="rpg-inspector-trace-type">' + esc(event.type || "event") + '</span>' +
          '<span class="rpg-inspector-trace-origin">' + esc(event.origin || "") + '</span>' +
        '</div>' +
        '<div class="rpg-inspector-trace-summary">' + esc(event.summary || "") + '</div>' +
        (loot.length ? '<div class="rpg-inspector-trace-loot">' +
          loot.map(function(item) {
            return '<span class="rpg-inspector-chip">' + esc(item.name || item.item_id || "item") + ' x' + Number(item.qty || 1) + '</span>';
          }).join("") +
        '</div>' : "") +
      '</div>';
    }).join("") : '<div class="rpg-inspector-muted">No causal trace events</div>') +
  '</div>';
}

function renderTimelineRowTooltip(row) {
  var timelineRow = row || {};
  var inventorySummary = timelineRow.inventory_summary || {};
  return '<div class="rpg-inspector-tooltip">' +
    '<div>Tick ' + Number(timelineRow.tick || 0) + '</div>' +
    '<div>Events: ' + Number(timelineRow.event_count || 0) + '</div>' +
    '<div>Consequences: ' + Number(timelineRow.consequence_count || 0) + '</div>' +
    '<div>Inventory Slots: ' + Number(inventorySummary.slots_used || 0) + '/' + Number(inventorySummary.capacity || 0) + '</div>' +
    '<div>Total Items: ' + Number(inventorySummary.total_item_qty || 0) + '</div>' +
  '</div>';
}
