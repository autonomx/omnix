/**
 * Phase 8.4.7 - RPG Inspector Causal Trace
 *
 * Builds and renders a causal trace chain that links:
 * - Events
 * - Consequences
 * - World consequences
 * - NPC reasoning
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

function buildCausalTrace(opts) {
  const optsSafe = safeObj(opts);
  const diff = safeObj(optsSafe.latestDiff);
  const timeline = safeObj(optsSafe.timeline);
  const npcReasoning = safeObj(optsSafe.npcReasoning);

  const chain = [];

  safeArray(diff.new_events).forEach(function(event) {
    chain.push({
      kind: "event",
      label: event.type || "event",
      text: event.summary || "",
    });
  });

  safeArray(diff.new_consequences).forEach(function(item) {
    chain.push({
      kind: "consequence",
      label: item.type || "consequence",
      text: item.summary || "",
    });
  });

  safeArray(timeline.recent_world_consequences).forEach(function(item) {
    chain.push({
      kind: "world",
      label: item.type || "world_consequence",
      text: item.summary || "",
    });
  });

  const why = safeObj(npcReasoning.why);
  if (Object.keys(why).length > 0) {
    chain.push({
      kind: "npc_reasoning",
      label: "npc_reasoning",
      text: why.decision_reason || JSON.stringify(why),
    });
  }

  return chain.slice(0, 20);
}

function renderCausalTrace(trace) {
  const root = document.getElementById("rpg-inspector-causal-trace");
  if (!root) return;
  const rows = safeArray(trace);
  if (rows.length === 0) {
    root.innerHTML = '<div class="rpg-inspector-title">Causal Trace</div><div class="rpg-inspector-meta">No causal trace yet</div>';
    return;
  }
  root.innerHTML = [
    '<div class="rpg-inspector-title">Causal Trace</div>',
  ].join("\n");

  rows.forEach(function(row, idx) {
    root.innerHTML += '<div class="rpg-inspector-trace-row">' +
      '<div class="rpg-inspector-trace-index">' + esc(idx + 1) + '</div>' +
      '<div class="rpg-inspector-trace-body">' +
        '<div><strong>' + esc(row.label || row.kind || "step") + '</strong></div>' +
        '<div>' + esc(row.text || "") + '</div>' +
      '</div>' +
    '</div>';
  });
}