(function () {
  "use strict";

  const DEFAULTS = {
    enabled: true,
    autonomous_ticks_enabled: false,
    show_ambient_conversations: true,
    frequency: "normal",
    min_ticks_between_conversations: 3,
    thread_cooldown_ticks: 8,
    max_active_threads: 2,
    max_beats_per_thread: 4,
    conversation_chance_percent: 30,
    allow_player_addressed: true,
    allow_player_invited: false,
    player_inclusion_chance_percent: 10,
    require_relevant_memory_to_address_player: true,
    pending_response_timeout_ticks: 3,
    allow_world_signals: true,
    allow_world_events: true,
    allow_relationship_effects: false,
    allow_quest_discussion: true,
    allow_event_discussion: true,
    allow_rumor_discussion: true,
    allow_memory_discussion: true,
    max_world_signals_per_thread: 2,
    max_world_events_per_thread: 4,
    signal_strength_cap: 1,
  };

  function loadSettings() {
    try {
      const raw = localStorage.getItem("rpg.conversationSettings");
      return Object.assign({}, DEFAULTS, raw ? JSON.parse(raw) : {});
    } catch (_) {
      return Object.assign({}, DEFAULTS);
    }
  }

  function saveSettings(settings) {
    localStorage.setItem("rpg.conversationSettings", JSON.stringify(settings || {}));
    window.dispatchEvent(
      new CustomEvent("rpg:conversation-settings-changed", { detail: settings })
    );
  }

  function boolInput(label, key, settings) {
    return `
      <label class="rpg-conv-setting">
        <input type="checkbox" data-conv-setting="${key}" ${settings[key] ? "checked" : ""}>
        <span>${label}</span>
      </label>
    `;
  }

  function numberInput(label, key, settings, min, max) {
    return `
      <label class="rpg-conv-setting">
        <span>${label}</span>
        <input type="number" min="${min}" max="${max}" value="${settings[key]}" data-conv-setting="${key}">
      </label>
    `;
  }

  function selectInput(label, key, settings, values) {
    return `
      <label class="rpg-conv-setting">
        <span>${label}</span>
        <select data-conv-setting="${key}">
          ${values
            .map(
              (value) =>
                `<option value="${value}" ${settings[key] === value ? "selected" : ""}>${value}</option>`
            )
            .join("")}
        </select>
      </label>
    `;
  }

  function findOrCreatePanel() {
    const host =
      document.getElementById("rpgSettingsPanel") ||
      document.getElementById("rpg-settings-panel") ||
      document.getElementById("rpgInspectorPanel") ||
      document.getElementById("rpg-top-panels") ||
      document.body;

    let panel = document.getElementById("rpgConversationSettingsPanel");
    if (!panel) {
      panel = document.createElement("section");
      panel.id = "rpgConversationSettingsPanel";
      panel.className = "rpg-conversation-settings-panel";
      host.appendChild(panel);
    }
    return panel;
  }

  function render() {
    const settings = loadSettings();
    const panel = findOrCreatePanel();
    panel.innerHTML = `
      <details>
        <summary><strong>Living Conversations</strong></summary>
        <div class="rpg-conv-settings-grid">
          ${boolInput("Enable NPC conversations", "enabled", settings)}
          ${boolInput("Enable autonomous ticks", "autonomous_ticks_enabled", settings)}
          ${boolInput("Show ambient conversations", "show_ambient_conversations", settings)}
          ${boolInput("NPCs can address player", "allow_player_addressed", settings)}
          ${boolInput("NPCs can invite player response", "allow_player_invited", settings)}
          ${boolInput("Require memory to address player", "require_relevant_memory_to_address_player", settings)}
          ${boolInput("Allow world signals", "allow_world_signals", settings)}
          ${boolInput("Allow conversation world events", "allow_world_events", settings)}
          ${boolInput("Allow quest discussion", "allow_quest_discussion", settings)}
          ${boolInput("Allow event discussion", "allow_event_discussion", settings)}
          ${boolInput("Allow rumor discussion", "allow_rumor_discussion", settings)}
          ${boolInput("Allow memory discussion", "allow_memory_discussion", settings)}
          ${selectInput("Frequency", "frequency", settings, ["off", "rare", "normal", "frequent", "always"])}
          ${numberInput("Min ticks between conversations", "min_ticks_between_conversations", settings, 0, 20)}
          ${numberInput("Thread cooldown ticks", "thread_cooldown_ticks", settings, 0, 50)}
          ${numberInput("Max active threads", "max_active_threads", settings, 1, 5)}
          ${numberInput("Max beats per thread", "max_beats_per_thread", settings, 1, 12)}
          ${numberInput("Conversation chance %", "conversation_chance_percent", settings, 0, 100)}
          ${numberInput("Player inclusion chance %", "player_inclusion_chance_percent", settings, 0, 100)}
          ${numberInput("Pending response timeout", "pending_response_timeout_ticks", settings, 1, 20)}
          ${numberInput("Max world signals/thread", "max_world_signals_per_thread", settings, 0, 10)}
          ${numberInput("Max world events/thread", "max_world_events_per_thread", settings, 0, 12)}
          ${numberInput("Signal strength cap", "signal_strength_cap", settings, 1, 5)}
        </div>
      </details>
    `;

    panel.querySelectorAll("[data-conv-setting]").forEach((input) => {
      input.addEventListener("change", () => {
        const next = loadSettings();
        const key = input.getAttribute("data-conv-setting");
        if (input.type === "checkbox") {
          next[key] = input.checked;
        } else if (input.type === "number") {
          next[key] = Number(input.value);
        } else {
          next[key] = input.value;
        }
        saveSettings(next);
      });
    });
  }

  function attachToPayload(payload) {
    payload = payload || {};
    payload.runtime_settings = payload.runtime_settings || {};
    payload.runtime_settings.conversation_settings = loadSettings();
    return payload;
  }

  window.RpgConversationSettings = {
    render,
    loadSettings,
    saveSettings,
    attachToPayload,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", render);
  } else {
    render();
  }
})();