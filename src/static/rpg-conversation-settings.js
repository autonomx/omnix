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
    // Bundle N-O-P — NPC Biography Roleplay
    npc_roleplay_use_llm: false,
    npc_roleplay_max_line_chars: 240,
    npc_roleplay_fallback_on_invalid: true,
    // Bundle H
    allow_npc_response_beats: true,
    npc_response_style_influence: true,
    // Bundle J
    allow_rumor_propagation: true,
    max_rumor_seeds: 24,
    max_rumor_mentions_per_location: 3,
    max_signal_age_ticks: 80,
    // Bundle K-L-M
    avoid_repeated_npc_response_lines: true,
    allow_npc_goal_influence: true,
    goal_player_invitation_bias_cap: 20,
    allow_scene_activities: true,
    scene_activity_interval_ticks: 2,
    scene_activity_cooldown_ticks: 3,
    allow_scene_activity_world_events: true,
    allow_scene_activity_world_signals: true,
    // Bundle BM-BN-BO — NPC Profile Auto-creation
    auto_create_npc_profiles_on_introduction: true,
    // N122 — Climate + Survival
    climate_time_enabled: true,
    day_night_cycle_enabled: true,
    seasons_enabled: true,
    weather_enabled: true,
    temperature_enabled: true,
    survival_enabled: true,
    survival_hunger_enabled: true,
    survival_thirst_enabled: true,
    survival_sleep_enabled: true,
    survival_auto_care_enabled: true,
    survival_hunger_per_day: 28,
    survival_thirst_per_day: 40,
    survival_fatigue_per_day: 32,
    survival_hungry_threshold: 55,
    survival_thirsty_threshold: 50,
    survival_tired_threshold: 60,
    survival_sleep_start_hour: 22,
    survival_wake_hour: 6,
    weather_volatility: "normal",
    climate_season_start: "spring",
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
          ${boolInput("Allow NPC response beats", "allow_npc_response_beats", settings)}
          ${boolInput("NPC response style influence", "npc_response_style_influence", settings)}
          ${boolInput("Allow rumor propagation", "allow_rumor_propagation", settings)}
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
          ${boolInput("Use LLM for NPC roleplay lines", "npc_roleplay_use_llm", settings)}
          ${numberInput("NPC roleplay max chars", "npc_roleplay_max_line_chars", settings, 80, 600)}
          ${boolInput("Fallback when roleplay invalid", "npc_roleplay_fallback_on_invalid", settings)}
          ${numberInput("Max rumor seeds", "max_rumor_seeds", settings, 0, 64)}
          ${numberInput("Max rumors/location", "max_rumor_mentions_per_location", settings, 0, 12)}
          ${numberInput("Signal expiry ticks", "max_signal_age_ticks", settings, 1, 100)}
          ${boolInput("Avoid repeated NPC lines", "avoid_repeated_npc_response_lines", settings)}
          ${boolInput("NPC goal influence", "allow_npc_goal_influence", settings)}
          ${numberInput("Goal bias cap", "goal_player_invitation_bias_cap", settings, 0, 50)}
          ${boolInput("Scene activities", "allow_scene_activities", settings)}
          ${numberInput("Scene activity interval", "scene_activity_interval_ticks", settings, 1, 20)}
          ${numberInput("Scene activity cooldown", "scene_activity_cooldown_ticks", settings, 0, 20)}
          ${boolInput("Scene activity world events", "allow_scene_activity_world_events", settings)}
          ${boolInput("Scene activity world signals", "allow_scene_activity_world_signals", settings)}
          ${boolInput("Auto-create NPC profiles when first introduced", "auto_create_npc_profiles_on_introduction", settings)}
        </div>
      </details>
      <details>
        <summary><strong>Climate + Survival</strong></summary>
        <div class="rpg-conv-settings-grid">
          ${boolInput("Enable climate/time system", "climate_time_enabled", settings)}
          ${boolInput("Day/night cycle", "day_night_cycle_enabled", settings)}
          ${boolInput("Seasons", "seasons_enabled", settings)}
          ${boolInput("Weather", "weather_enabled", settings)}
          ${boolInput("Temperature", "temperature_enabled", settings)}
          ${selectInput("Season start", "climate_season_start", settings, ["spring", "summer", "autumn", "winter"])}
          ${selectInput("Weather volatility", "weather_volatility", settings, ["calm", "normal", "harsh"])}
          ${boolInput("Enable survival pressure", "survival_enabled", settings)}
          ${boolInput("Hunger", "survival_hunger_enabled", settings)}
          ${boolInput("Thirst", "survival_thirst_enabled", settings)}
          ${boolInput("Sleep/fatigue", "survival_sleep_enabled", settings)}
          ${boolInput("Auto-care in campaign/autoplay", "survival_auto_care_enabled", settings)}
          ${numberInput("Hunger gain/day", "survival_hunger_per_day", settings, 0, 100)}
          ${numberInput("Thirst gain/day", "survival_thirst_per_day", settings, 0, 120)}
          ${numberInput("Fatigue gain/day", "survival_fatigue_per_day", settings, 0, 120)}
          ${numberInput("Eat when hunger >=", "survival_hungry_threshold", settings, 0, 100)}
          ${numberInput("Drink when thirst >=", "survival_thirsty_threshold", settings, 0, 100)}
          ${numberInput("Sleep when fatigue >=", "survival_tired_threshold", settings, 0, 100)}
          ${numberInput("Sleep starts hour", "survival_sleep_start_hour", settings, 0, 23)}
          ${numberInput("Wake hour", "survival_wake_hour", settings, 0, 23)}
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
    const settings = loadSettings();
    payload.runtime_settings.conversation_settings = settings;
    payload.runtime_settings.climate_survival_settings = {
      climate_time_enabled: settings.climate_time_enabled !== false,
      day_night_cycle_enabled: settings.day_night_cycle_enabled !== false,
      seasons_enabled: settings.seasons_enabled !== false,
      weather_enabled: settings.weather_enabled !== false,
      temperature_enabled: settings.temperature_enabled !== false,
      survival_enabled: settings.survival_enabled !== false,
      hunger_enabled: settings.survival_hunger_enabled !== false,
      thirst_enabled: settings.survival_thirst_enabled !== false,
      sleep_enabled: settings.survival_sleep_enabled !== false,
      auto_care_enabled: settings.survival_auto_care_enabled !== false,
      hunger_per_day: Number(settings.survival_hunger_per_day || 0),
      thirst_per_day: Number(settings.survival_thirst_per_day || 0),
      fatigue_per_day: Number(settings.survival_fatigue_per_day || 0),
      hungry_threshold: Number(settings.survival_hungry_threshold || 0),
      thirsty_threshold: Number(settings.survival_thirsty_threshold || 0),
      tired_threshold: Number(settings.survival_tired_threshold || 0),
      sleep_start_hour: Number(settings.survival_sleep_start_hour || 22),
      wake_hour: Number(settings.survival_wake_hour || 6),
      season_start: settings.climate_season_start || "spring",
      weather_volatility: settings.weather_volatility || "normal",
    };
    payload.runtime_settings.npc_profile_generation = {
      auto_create_on_introduction: !!document.getElementById("rpgAutoCreateNpcProfilesToggle")
        ? document.getElementById("rpgAutoCreateNpcProfilesToggle").checked
        : settings.auto_create_npc_profiles_on_introduction !== false,
      allow_manual_create: true,
      draft_with_llm_on_create: false,
    };
    return payload;
  }

  function ensureSurvivalInspectorScript() {
    if (window.RpgSurvivalInspector || document.getElementById("rpg-survival-inspector-script")) return;
    const script = document.createElement("script");
    script.id = "rpg-survival-inspector-script";
    script.src = "/static/rpg/rpg-survival-inspector.js";
    script.defer = true;
    document.head.appendChild(script);
  }

  window.RpgConversationSettings = {
    render,
    loadSettings,
    saveSettings,
    attachToPayload,
    ensureSurvivalInspectorScript,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      render();
      ensureSurvivalInspectorScript();
    });
  } else {
    render();
    ensureSurvivalInspectorScript();
  }
})();
