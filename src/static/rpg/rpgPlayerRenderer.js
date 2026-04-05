/**
 * Phase 8 — Player View Renderer
 *
 * Renders player-facing view from narrator's player_view into the UI.
 * Core UX loop: simulation -> scene -> narrator -> player_view -> UI render
 */

export function renderPlayerView(playerView) {
  if (!playerView) return;

  renderSceneHeader(playerView);
  renderActors(playerView);
  renderChoices(playerView);
  renderWorldSignals(playerView);
}

function renderSceneHeader(view) {
  const el = document.getElementById("rpg-scene-title");
  if (!el) return;
  el.textContent = view.scene_title || view.title || "Scene";
}

function renderActors(view) {
  const el = document.getElementById("rpg-actors");
  if (!el) return;
  el.innerHTML = "";

  const actors = (view.encounter && view.encounter.actors) || view.actors || [];

  actors.forEach((a) => {
    const div = document.createElement("div");
    div.className = "actor";
    div.textContent = `${a.name || a.id} (${a.role || "unknown"})`;
    el.appendChild(div);
  });
}

function renderChoices(view) {
  const el = document.getElementById("rpg-choices");
  if (!el) return;
  el.innerHTML = "";

  const choices = (view.encounter && view.encounter.choices) || view.choices || [];

  choices.forEach((choice) => {
    const btn = document.createElement("button");
    btn.className = "choice-btn";
    btn.textContent = choice.label || choice.text || "Choose";
    btn.onclick = () => {
      window.dispatchEvent(
        new CustomEvent("rpg:choice", { detail: choice })
      );
    };
    el.appendChild(btn);
  });
}

function renderWorldSignals(view) {
  const el = document.getElementById("rpg-world-signals");
  if (!el) return;
  el.innerHTML = "";

  const rumors = view.active_rumors || [];
  const alliances = view.active_alliances || [];

  rumors.forEach((r) => {
    const div = document.createElement("div");
    div.textContent = `Rumor: ${r.text || r.type || r.id}`;
    el.appendChild(div);
  });

  alliances.forEach((a) => {
    const div = document.createElement("div");
    div.textContent = `Alliance: ${a.alliance_id || a.id || a.name}`;
    el.appendChild(div);
  });
}