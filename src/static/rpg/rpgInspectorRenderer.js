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