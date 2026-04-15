/**
 * Phase 8.4.7 - RPG Inspector Diff Renderer
 *
 * Renders a visual diff panel for the inspector, showing:
 * - Summary of what changed between ticks
 * - Changed NPC IDs
 * - Social and sandbox keys that changed
 * - New events and consequences
 */

function esc(str) {
  const s = String(str ?? "");
  return s
    .replaceAll("\u0026", "\u0026amp;")
    .replaceAll("\u003C", "\u0026lt;")
    .replaceAll("\u003E", "\u0026gt;")
    .replaceAll('"', "\u0026quot;")
    .replaceAll("'", "\u0026#39;");
}

function safeArray(v) {
  return Array.isArray(v) ? v : [];
}

function safeObj(v) {
  return v && typeof v === "object" ? v : {};
}

function renderInspectorDiff(diff) {
  const root = document.getElementById("rpg-inspector-diff-panel");
  if (!root) return;

  const data = safeObj(diff);
  const summary = safeObj(data.summary);
  const newEvents = safeArray(data.new_events);
  const newConsequences = safeArray(data.new_consequences);
  const changedNpcIds = safeArray(data.changed_npc_ids);
  const socialKeys = safeArray(data.social_keys_changed);
  const sandboxKeys = safeArray(data.sandbox_keys_changed);

  root.innerHTML = [
    '<div class="rpg-inspector-title">Visual Diff</div>',
    '<div class="rpg-inspector-meta">Tick ' + esc(data.tick_before) + ' \u2192 ' + esc(data.tick_after) + '</div>',
    '<div class="rpg-inspector-grid2">',
    '  <div class="rpg-inspector-chip">Events \u0394 ' + esc(summary.event_delta ?? 0) + '</div>',
    '  <div class="rpg-inspector-chip">Consequences \u0394 ' + esc(summary.consequence_delta ?? 0) + '</div>',
    '  <div class="rpg-inspector-chip">NPC changes ' + esc(summary.npc_changes ?? 0) + '</div>',
    '</div>',
    '<div class="rpg-inspector-subtitle">Changed NPCs</div>',
    '<div>' + changedNpcIds.map(function(id) { return '<span class="rpg-inspector-tag">' + esc(id) + '</span>'; }).join("") + (changedNpcIds.length ? "" : '<div class="rpg-inspector-meta">No NPC changes</div>') + '</div>',
    '<div class="rpg-inspector-subtitle">Social Keys Changed</div>',
    '<div>' + socialKeys.map(function(id) { return '<span class="rpg-inspector-tag">' + esc(id) + '</span>'; }).join("") + (socialKeys.length ? "" : '<div class="rpg-inspector-meta">No social changes</div>') + '</div>',
    '<div class="rpg-inspector-subtitle">Sandbox Keys Changed</div>',
    '<div>' + sandboxKeys.map(function(id) { return '<span class="rpg-inspector-tag">' + esc(id) + '</span>'; }).join("") + (sandboxKeys.length ? "" : '<div class="rpg-inspector-meta">No sandbox changes</div>') + '</div>',
    '<div class="rpg-inspector-subtitle">New Events</div>',
  ].join("\n");

  if (newEvents.length === 0) {
    root.innerHTML += '<div class="rpg-inspector-meta">No new events</div>';
  } else {
    newEvents.forEach(function(item) {
      root.innerHTML += '<div class="rpg-inspector-row"><div><strong>' + esc(item.type || "event") + '</strong></div><div>' + esc(item.summary || "") + '</div></div>';
    });
  }

  root.innerHTML += '<div class="rpg-inspector-subtitle">New Consequences</div>';
  if (newConsequences.length === 0) {
    root.innerHTML += '<div class="rpg-inspector-meta">No new consequences</div>';
  } else {
    newConsequences.forEach(function(item) {
      root.innerHTML += '<div class="rpg-inspector-row"><div><strong>' + esc(item.type || "consequence") + '</strong></div><div>' + esc(item.summary || "") + '</div></div>';
    });
  }
}