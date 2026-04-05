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
