function safeArray(v) {
  return Array.isArray(v) ? v : [];
}

function esc(str) {
  const s = String(str ?? "");
  return s.replace(/&/g, "\x26amp;").replace(/</g, "\x26lt;").replace(/>/g, "\x26gt;").replace(/"/g, "\x26quot;").replace(/'/g, "\x26#39;");
}

export function renderEncounterState(encounterState, onAction) {
  renderEncounterHeader(encounterState);
  renderEncounterParticipants(encounterState);
  renderEncounterLog(encounterState);
  renderEncounterActions(encounterState, onAction);
}

function renderEncounterHeader(encounterState) {
  const root = document.getElementById("rpg-encounter-header");
  if (!root) return;
  const type = esc(encounterState?.encounter_type || "encounter");
  const rnd = esc(encounterState?.round || 0);
  const actor = esc(encounterState?.active_actor_id || "\u2014");
  const status = esc(encounterState?.status || "inactive");
  root.innerHTML = '\x3cdiv\x3e\x3cstrong\x3e' + type + '\x3c/strong\x3e\x3c/div\x3e\x3cdiv\x3eRound ' + rnd + ' \u00b7 Active: ' + actor + '\x3c/div\x3e\x3cdiv\x3eStatus: ' + status + '\x3c/div\x3e';
}

function renderEncounterParticipants(encounterState) {
  const root = document.getElementById("rpg-encounter-participants");
  if (!root) return;
  const participants = safeArray(encounterState?.participants);
  root.innerHTML = participants
    .map(function(p) {
      var name = esc(p.name || p.actor_id);
      var side = esc(p.side);
      var hp = esc(p.hp);
      var mhp = esc(p.max_hp);
      var stress = esc(p.stress);
      return '\x3cdiv class="rpg-encounter-participant"\x3e\x3cdiv\x3e' + name + '\x3c/div\x3e\x3cdiv\x3e' + side + ' \u00b7 HP ' + hp + '/' + mhp + ' \u00b7 Stress ' + stress + '\x3c/div\x3e\x3c/div\x3e';
    })
    .join("");
}

function renderEncounterLog(encounterState) {
  const root = document.getElementById("rpg-encounter-log");
  if (!root) return;
  const log = safeArray(encounterState?.log);
  root.innerHTML = log
    .slice(-20)
    .map(function(item) {
      var r = esc(item.round);
      var t = esc(item.text);
      return '\x3cdiv class="rpg-encounter-log-line"\x3e\x3cspan\x3eR' + r + '\x3c/span\x3e ' + t + '\x3c/div\x3e';
    })
    .join("");
}

function renderEncounterActions(encounterState, onAction) {
  const root = document.getElementById("rpg-encounter-actions");
  if (!root) return;
  const actions = safeArray(encounterState?.available_actions);
  root.innerHTML = "";
  actions.forEach(function(action) {
    var btn = document.createElement("button");
    btn.className = "rpg-encounter-action";
    btn.textContent = action.label || action.action_id;
    btn.onclick = function() { if (onAction) onAction(action); };
    root.appendChild(btn);
  });
}