# RPG Environment System 2.0 Roadmap

Environment System 2.0 treats environment as a deterministic simulation domain, not as cosmetic weather labels and not as narration-owned flavor. Weather is only one event type inside a broader environment model that also covers time, calendar, season, climate, temperature, wind, visibility, light, terrain conditions, natural hazards, environmental events, environmental memory, and later ecology/resources.

This roadmap is intentionally infrastructure-first. The first implementation slices establish authoritative state, deterministic derivation, UI truthfulness, migration, narration contracts, and simulation-domain boundaries. Travel, combat, stealth, tracking, survival, NPC schedules, agriculture, faction behavior, ecology, and economy systems should consume environment snapshots later, but they should not be mixed into the initial environment-state slice.

Related planning issue: #669.

## Core Principle

Environment is a simulation domain.

The backend simulation owns environment state and environment advancement. The LLM narrator may describe the current environment, emphasize it, and interpret it in prose, but may never create, modify, contradict, or advance environment state.

Weather is not the system. Weather is one class of environment event.

## Simulation Domain Boundary

Omnix RPG should treat major gameplay areas as simulation domains with explicit ownership rules:

- Environment Domain owns time, calendar, climate, weather events, environmental hazards, environmental memory, derived environmental snapshots, and environment advancement.
- Travel Domain reads environment snapshots and returns elapsed time or travel consequences; it does not mutate weather or climate.
- Combat Domain reads visibility, wind, light, terrain, exposure, and hazards; it does not mutate environment except through explicit simulation events requested from the Environment Domain.
- Social/NPC Domain reads weather, light, hazards, season, and exposure preferences; it does not mutate weather/time directly.
- Economy Domain reads season, drought, flood, frost, route conditions, and resource signals; it does not own environment state.
- Quest Domain reads environment state as context; it does not create weather/time changes through narration.
- Narration Domain reads snapshots and describes them; it never mutates simulation state.

This is a universal architecture rule, not just an environment rule: a domain may consume another domain's read model but should not write another domain's authoritative state without going through that domain's service/API.

## Responsibilities

Environment owns:

- Calendar and time progression.
- Season derivation.
- Climate profile assignment.
- Weather and weather-front events.
- Natural hazards and environmental anomaly events.
- Environmental event timers and deterministic event generation.
- Environmental memory, such as recent rain, snowpack, dry days, mud persistence, drought pressure, thaw state, storm history, and short event history.
- Temperature derivation.
- Wind derivation.
- Visibility derivation.
- Light-level derivation.
- Terrain-condition derivation.
- Future environmental resources such as water availability, vegetation, soil moisture, snowpack, drought pressure, and forage availability.

Environment does not own:

- NPC schedules.
- Travel speed.
- Combat modifiers.
- Stealth modifiers.
- Tracking modifiers.
- Quest behavior.
- Faction behavior.
- Economy behavior.
- Ecology behavior.
- Narration wording.

Those systems consume environment snapshots through a service API.

## Architecture Layers

### Layer 1: Authoritative Environment State

Persist only minimal source-of-truth state under `world.environment`.

E2.0.1 should include forward-compatible identifiers and versioning even if only one region exists and only one calendar style exists.

Example target shape:

```json
{
  "world": {
    "environment": {
      "environment_version": 1,
      "region_id": "starting_region",
      "climate_profile_id": "temperate_hills",
      "environment_seed": 482193,
      "calendar": {
        "year": 1,
        "day_of_year": 278,
        "days_per_year": 360
      },
      "absolute_minutes": 480,
      "active_events": [
        {
          "id": "weather_001",
          "type": "weather",
          "condition": "rain",
          "intensity": "moderate",
          "remaining_minutes": 840,
          "started_at_minute": 480
        }
      ],
      "recent_conditions": {
        "rain_minutes_24h": 180,
        "snow_minutes_24h": 0,
        "dry_minutes_72h": 0,
        "freezing_minutes_24h": 0
      },
      "event_history": []
    },
    "reputation": {
      "label": "Unknown",
      "score": 0
    }
  }
}
```

Do not persist temperature, visibility, light level, terrain condition, display weather, or mutable `season_id` as source-of-truth fields. Those are derived values. This prevents invalid state combinations such as snow at 25C or night at 14:00.

`season_id` may appear in compatibility projections and snapshots, but the long-term source should be calendar plus climate profile.

### Layer 2: Scene Environment Context

World environment and current scene exposure must remain separate.

Example target shape:

```json
{
  "scene": {
    "environment_context": {
      "exposure": "indoor",
      "shelter": "sheltered",
      "light_override": "tavern_lit",
      "region_id": "starting_region",
      "location_id": "rusty_flagon_tavern"
    }
  }
}
```

This allows the world to be snowing at -20C while the player is inside a warm inn. The world is not indoor or outdoor; the current scene is.

Scene context should not duplicate climate or weather state. It only describes how exposed the current scene is to the regional environment.

### Layer 3: Climate Profiles

Climate profiles are reusable world-generation primitives. Locations and generated regions reference profiles, but profiles should also be influenced by the Campaign Contract so genre, region, tone, and world setup can affect initial environment.

Example target shape:

```json
{
  "id": "northern_mountains",
  "display_name": "Northern Mountains",
  "temperature_ranges_c": {
    "early_spring": [-18, 2],
    "spring": [-8, 8],
    "summer": [-2, 16],
    "early_autumn": [-4, 10],
    "late_autumn": [-12, 4],
    "winter": [-40, -10]
  },
  "sunrise_minutes": {
    "summer": 300,
    "late_autumn": 450,
    "winter": 540
  },
  "sunset_minutes": {
    "summer": 1260,
    "late_autumn": 990,
    "winter": 900
  },
  "weather_weights": {
    "summer": {
      "clear": 0.25,
      "rain": 0.20,
      "fog": 0.20,
      "windy": 0.20,
      "storm": 0.15
    },
    "late_autumn": {
      "snow": 0.35,
      "rain": 0.20,
      "fog": 0.25,
      "clear": 0.10,
      "windy": 0.10
    },
    "winter": {
      "snow": 0.45,
      "blizzard": 0.20,
      "fog": 0.15,
      "clear": 0.10,
      "windy": 0.10
    }
  },
  "base_wind": "moderate",
  "terrain_defaults": {
    "outdoor": "firm_ground",
    "indoor": "dry_floor",
    "underground": "stone_floor"
  },
  "hazard_weights": {
    "avalanche_risk": 0.05,
    "flash_flood_risk": 0.01
  },
  "resource_baselines": {
    "water_availability": 70,
    "vegetation": 55,
    "soil_moisture": 40,
    "forage_availability": 45
  }
}
```

Climate profiles should support fantasy, post-apocalyptic, sci-fi, cyberpunk, and other genres without redesign. Genre-specific hazards such as arcane storms, toxic clouds, radiation fronts, solar flares, volcanic ash, or nanite fog should be represented as typed events.

### Layer 3.5: Calendar and Seasonal Model

Seasons should derive from calendar and climate profile instead of being stored as independently mutable state.

Target model:

```json
{
  "calendar": {
    "year": 1,
    "day_of_year": 278,
    "days_per_year": 360
  }
}
```

Derived values:

```json
{
  "season_id": "late_autumn",
  "season_label": "Late Autumn",
  "day_of_season": 38
}
```

Why this matters:

- Harvests derive from calendar.
- Migrations derive from calendar.
- Festivals derive from calendar.
- Trade-route patterns derive from calendar.
- Breeding seasons derive from calendar.
- Winter preparation and scarcity derive from calendar.
- Sunrise/sunset and temperature bands derive from calendar plus climate.

Recommended season IDs:

- early_spring
- spring
- summer
- early_autumn
- late_autumn
- winter

A simpler four-season model can be displayed, but the simulation benefits from early/late shoulder seasons.

### Layer 4: Environment Events

Environment events are the engine of the system. Weather fronts are events, not a standalone weather field.

Event examples:

```json
{
  "id": "weather_001",
  "type": "weather",
  "condition": "snow",
  "intensity": "moderate",
  "remaining_minutes": 960,
  "started_at_minute": 12000
}
```

```json
{
  "id": "hazard_001",
  "type": "natural_hazard",
  "condition": "avalanche_risk",
  "intensity": "low",
  "remaining_minutes": 240,
  "started_at_minute": 12240
}
```

```json
{
  "id": "anomaly_001",
  "type": "arcane_weather",
  "condition": "mana_storm",
  "intensity": "severe",
  "remaining_minutes": 120,
  "started_at_minute": 12300
}
```

Event fields should include:

- `id`: deterministic event id.
- `type`: weather, natural_hazard, anomaly, regional_effect, pollution, radiation, volcanic, ecology, etc.
- `condition`: rain, snow, fog, blizzard, heat_wave, cold_snap, dust_storm, toxic_cloud, solar_flare, etc.
- `intensity`: trace, light, moderate, heavy, severe, extreme.
- `remaining_minutes`: persistence timer.
- `started_at_minute`: absolute minute when the event began.
- `region_id`: mandatory once region-level simulation ships; E2.0.1 should still include `world.environment.region_id`.
- Optional `metadata` for genre-specific values.

E2 may keep one `active_events` list, but helpers should avoid assuming only one weather-like event can exist. Long-term indexing can expose:

```json
{
  "weather_events": [],
  "hazard_events": [],
  "anomaly_events": [],
  "regional_effect_events": []
}
```

These can be derived views over `active_events` or separate buckets if performance/clarity requires it.

Weather should persist through fronts/events. It should not reroll every turn. When an event expires, deterministic environment RNG generates the next event from climate profile, calendar-derived season, recent conditions, active region, and campaign/environment seed.

### Layer 4.5: Environment Event History

Short rolling history should be separate from recent-condition counters.

Target shape:

```json
{
  "event_history": [
    {
      "id": "weather_001",
      "type": "weather",
      "condition": "blizzard",
      "intensity": "severe",
      "started_at_minute": 12000,
      "ended_at_minute": 12960,
      "region_id": "northern_mountains"
    }
  ]
}
```

This enables future systems to reason about recent facts:

- The pass was closed after last week's blizzard.
- A flood happened three days ago.
- The road was damaged by ashfall.
- Bandits exploited the fog during a recent storm.
- Crops failed after a heat wave.

Keep history bounded. It is not a full immutable chronicle. Long-term lore/chronicle systems can summarize or archive it separately.

### Layer 5: Derivation Engine

The derivation engine computes snapshots from authoritative state, climate profile, scene context, active events, calendar, region, and recent history.

Example snapshot:

```json
{
  "environment_version": 1,
  "region_id": "starting_region",
  "year": 1,
  "day": 1,
  "day_of_year": 278,
  "minute_of_day": 480,
  "time_label": "Day 1 - 08:00",
  "time_block": "morning",
  "season_id": "late_autumn",
  "season_label": "Late Autumn",
  "weather": "rain",
  "weather_intensity": "moderate",
  "temperature_c": 9,
  "temperature_label": "Cool",
  "wind": "light",
  "visibility": "moderate",
  "light_level": "dim_indoor",
  "terrain_condition": "dry_floor",
  "exposure": "indoor",
  "shelter": "sheltered",
  "hazards": [],
  "resources": {
    "water_availability": 70,
    "vegetation": 55,
    "soil_moisture": 40,
    "forage_availability": 45
  }
}
```

Derived snapshot values are never the persisted source of truth. Systems should request snapshots through the environment service.

### Layer 6: Environment Service API

Consumers must not scatter weather logic throughout the codebase.

Target access pattern:

```python
snapshot = environment_service.get_snapshot(
    world_state=state["world"],
    scene_context=state.get("scene", {}).get("environment_context"),
    region_id=current_region_id,
)
```

Target advancement pattern:

```python
next_world = environment_service.advance(
    world_state=state["world"],
    elapsed_minutes=10,
    campaign_contract=contract,
)
```

Future consumers:

- Travel service consumes terrain condition, visibility, wind, hazards, and light.
- Combat consumes wind, visibility, terrain, exposure, and light.
- Stealth consumes light, weather noise, terrain, and visibility.
- Tracking consumes terrain history, precipitation, snowpack, mud, and visibility.
- NPC scheduling consumes weather, light, hazards, and exposure preferences.
- Economy/agriculture consumes season, weather history, drought, frost, floods, water availability, vegetation, and soil moisture.
- Ecology consumes season, weather history, temperature, water, vegetation, and hazards.
- Narration consumes a safe read-only snapshot.
- UI consumes display-ready snapshot fields.

### Layer 7: Time System

Use `absolute_minutes` internally.

Derive:

- Calendar year.
- Day number.
- Day of year.
- Minute of day.
- Hour/minute display.
- Time block: pre_dawn, dawn, morning, midday, afternoon, dusk, evening, night, deep_night.
- Season.
- Sunrise/sunset from climate profile and calendar-derived season.

Recommended first rules:

- Normal turn: +10 minutes.
- Wait action: +30 to +120 minutes, depending on command.
- Short rest: +60 minutes.
- Long rest/sleep: +480 minutes.
- Travel: explicit minutes from route, terrain, and later weather modifiers.

Do not expose minute precision everywhere in UI. Internally use minutes; display can stay readable.

### Layer 8: Environmental Memory

Track recent history so terrain and conditions feel persistent.

Target memory examples:

```json
{
  "recent_conditions": {
    "rain_minutes_24h": 240,
    "snow_minutes_24h": 0,
    "dry_minutes_72h": 600,
    "freezing_minutes_24h": 0,
    "storm_minutes_24h": 0,
    "snowpack_level": 0,
    "mud_level": 2,
    "dust_level": 0,
    "drought_level": 0
  }
}
```

Examples:

- Four days of rain creates mud and swollen roads.
- Twelve dry days creates dust.
- Twenty dry days creates drought pressure.
- Sustained freezing preserves snowpack.
- Warm rain after snow creates slush.
- Heavy snow plus wind can increase drift or avalanche risk.

Environmental memory should update only through deterministic simulation advancement.

### Layer 8.5: Environmental Resources

Environmental resources are longer-horizon environmental quantities derived from climate, season, events, and recent memory.

Examples:

```json
{
  "resources": {
    "water_availability": 80,
    "vegetation": 65,
    "soil_moisture": 40,
    "forage_availability": 55,
    "snowpack": 10,
    "drought_pressure": 0
  }
}
```

These bridge environment into economy, survival, ecology, agriculture, and world events.

Examples:

- Drought lowers soil moisture and water availability.
- Heavy rain raises soil moisture and flood pressure.
- Long winter lowers forage availability.
- Snowpack affects spring melt and river levels.
- Heat waves reduce vegetation and increase fire risk.

Do not attach economy mechanics in E2.0.1. Add the fields and derivation path only when the foundation is ready.

### Layer 9: Region-Level Simulation

Long-term architecture should support region-level environment state.

Target shape:

```json
{
  "world": {
    "regions": {
      "northern_mountains": {
        "environment": {}
      },
      "southern_coast": {
        "environment": {}
      },
      "sunfire_wastes": {
        "environment": {}
      }
    },
    "environment": {
      "active_region_id": "northern_mountains"
    }
  }
}
```

The first implementation may store one active-region environment under `world.environment`, but `region_id` should be mandatory in the active environment state from the beginning. Single-region to multi-region migration is one of the most expensive simulation-game migrations if identifiers are missing.

### Layer 10: Narration Contract 2.0

The narrator receives `environment_snapshot` and scene context.

Allowed:

- Describe current snow, rain, wind, darkness, mud, heat, fog, cold, or hazards.
- Emphasize environment in sensory prose.
- Interpret environment from NPC perspective.
- Mention practical implications already encoded in deterministic state.

Forbidden:

- Create a new storm.
- Clear the weather.
- Advance time.
- Change season.
- Invent temperature.
- Invent visibility changes.
- Invent hazards.
- Contradict current environment.

Bad narration example:

> A storm suddenly rolls in.

Good narration example when backend says snow, -15C, strong wind:

> Snow lashes across the pass, and the wind bites through every gap in your gloves.

### Layer 11: UI Contract

The UI should show only authoritative or derived environment values.

World State target fields:

- Calendar/season.
- Day/time.
- Region.
- Weather.
- Temperature.
- Wind.
- Visibility.
- Light.
- Terrain.
- Context: indoor, outdoor, sheltered, underground.
- Hazards, if active.
- Resource state later, when useful and supported.

Missing values should display `Not tracked yet`, not invented values. Temporary compatibility fields such as `world.weather` can remain during migration, but final UI should read from `environment_snapshot`.

Reputation should eventually move out of World State into a social/faction card because it is not environment.

### Layer 12: Ecology 3.0

Ecology is not part of E2.0.1, but the environment architecture should leave room for it.

Future ecology consumers can derive:

- Wildlife activity.
- Fish activity.
- Plant growth.
- Migration pressure.
- Predator presence.
- Pest pressure.
- Forage quality.
- Disease/vector risk.

Examples:

- Winter plus heavy snow can push wolves closer to settlements.
- Spring thaw can increase fish movement.
- Drought can reduce forage and increase predator encounters near water.
- Long rain can increase mushroom growth or disease pressure.
- Bloom season can change herb availability.

Ecology should consume environment and resource snapshots. It should not own weather, climate, calendar, or environment memory.

## Campaign Contract Integration

Environment should be generated from the Campaign Contract, not only from hand-authored starting locations.

Inputs may include:

- Genre.
- Tone.
- Region or biome.
- Campaign template.
- World activity.
- Starting location.
- Seed.
- Story setup options.
- Origin/background when relevant.

Target pipeline:

```text
Campaign Contract
  -> World Generation
  -> Region and climate assignment
  -> Calendar initialization
  -> Initial environment state
  -> Derived environment snapshot
  -> UI and narration context
```

This prevents climate from becoming disconnected from campaign generation.

## Implementation Roadmap

### E2.0.0 - Roadmap and UI Truthfulness

Purpose: remove fake environment UI and establish the durable plan.

Scope:

- Document Environment System 2.0.
- Record Environment 3.0 guardrails: calendar, environment versioning, mandatory region IDs, event history, resources, domain boundaries, and ecology.
- Ensure current UI does not infer fake temperature.
- Mark missing environment values as `Not tracked yet`.
- Keep current weather/time fields as compatibility values until E2.0.1.

Acceptance criteria:

- A new session does not show invented temperature.
- Existing static weather/time remain visible when present.
- Roadmap document exists and links to planning issue #669.

### E2.0.1 - Infrastructure-Only Environment Seed State

Purpose: introduce authoritative state without mechanics changes.

Scope:

- Add pure data helpers for `world.environment`.
- Add `environment_version`.
- Add mandatory `region_id` even for single-region campaigns.
- Add `absolute_minutes` time base.
- Add `calendar` with `year`, `day_of_year`, and `days_per_year`.
- Add `environment_seed` generated from campaign seed and campaign contract.
- Add initial typed weather event.
- Add initial `recent_conditions` object with deterministic defaults.
- Add bounded `event_history` array, initially empty.
- Add `scene.environment_context` for starting locations.
- Preserve existing compatibility fields `world.time`, `world.weather`, and `world.temperature` as read-only projections where needed.

Out of scope:

- Travel penalties.
- Combat penalties.
- Survival penalties.
- NPC schedule changes.
- Stealth/tracking modifiers.
- Economy/resource mechanics.
- Ecology mechanics.

Acceptance criteria:

- Same campaign seed and contract produce identical `world.environment`.
- Different seeds can produce different initial events within the same climate profile.
- Stored state does not persist derived temperature, visibility, light, terrain, or season as mutable source-of-truth fields.
- `environment_version`, `region_id`, `calendar`, and `environment_seed` are present in new sessions.
- Scene context can be indoor while world weather remains outdoor/regional.
- Tests cover classic fantasy tavern and mountain pass starts.

### E2.0.2 - Climate Profiles

Purpose: make climate reusable and deterministic.

Scope:

- Add climate profile registry.
- Add profiles for current starting areas, at minimum:
  - temperate_town or temperate_hills.
  - northern_mountains.
  - quarry_hills or rocky_temperate.
  - road_lowlands.
- Add temperature ranges by season.
- Add sunrise/sunset by season.
- Add weather weights by season.
- Add base wind and hazard weights.
- Add resource baselines where useful.
- Map existing starting locations to climate profiles.

Acceptance criteria:

- Every starting location resolves to a climate profile.
- Climate profile lookup is pure and deterministic.
- Missing profile falls back to a deterministic safe default and records a warning/metadata flag.
- Tests cover profile lookup and seasonal ranges.

### E2.0.3 - Calendar and Season Derivation

Purpose: make season a calendar-derived value.

Scope:

- Add calendar helper functions.
- Derive day, day_of_year, year, minute_of_day, season_id, and season label from `absolute_minutes` plus calendar config.
- Keep compatibility with existing display labels.
- Support deterministic initial day_of_year from Campaign Contract and seed.

Acceptance criteria:

- `season_id` is derived, not independently mutable.
- Same absolute minute and calendar produce same season.
- Initial season can be influenced by campaign contract or starting region.
- Tests cover season boundaries.

### E2.0.4 - Derived Environment Snapshot

Purpose: expose environment safely to UI, narration, and future systems.

Scope:

- Implement `derive_environment_snapshot(...)` as a pure helper.
- Derive day, minute_of_day, time label, time block, season label.
- Derive active weather from events.
- Derive temperature from climate profile, season, minute, weather event, and seed.
- Derive wind from climate profile and event modifiers.
- Derive visibility from weather, intensity, light, and context.
- Derive light level from time, sunrise/sunset, and scene overrides.
- Derive terrain condition from scene context, weather, and recent conditions.
- Derive initial environmental resource read model if resource baselines are available.
- Add display labels.

Acceptance criteria:

- Snapshot is deterministic for same state and seed.
- Snapshot is not persisted as source of truth.
- Snapshot supports indoor tavern during outdoor rain/snow.
- Tests prevent invalid derived combinations where possible.

### E2.0.5 - API and Session Surface

Purpose: make environment snapshots available consistently.

Scope:

- Include `environment_snapshot` in RPG session responses.
- Include snapshot in turn contract/narration context.
- Keep compatibility fields during migration.
- Add schema/type coverage for web client.

Acceptance criteria:

- UI can render world state from snapshot only.
- Narration payload includes snapshot but not mutation authority.
- Existing sessions without `world.environment` migrate through safe defaults.
- API tests cover old sessions and new sessions.

### E2.0.6 - UI World State 2.0

Purpose: replace shallow world-state display with snapshot-backed truth.

Scope:

- Render Calendar/Season, Day/Time, Region, Weather, Temperature, Wind, Visibility, Light, Terrain, Context, and Hazards.
- Move or separate Reputation from Environment when practical.
- Mark unavailable values as `Not tracked yet` only when snapshot truly lacks them.
- Avoid decorative controls.

Acceptance criteria:

- New campaign displays snapshot-backed environment values.
- Indoor context displays clearly without hiding outdoor weather.
- UI tests ensure no fake/inferred values outside backend snapshot.
- No unwired environment controls are visible.

### E2.0.7 - Deterministic Time Advancement

Purpose: make turns advance time through simulation.

Scope:

- Add environment time advancement helper.
- Normal turn advances +10 minutes by default.
- Travel/rest/wait can pass explicit elapsed minutes when those systems are ready.
- Decrement active event timers.
- Move expired events into bounded history.
- Update recent condition counters.
- Roll next event only when needed.

Acceptance criteria:

- 10 normal turns advance 100 minutes.
- Expired events generate deterministic replacements.
- Save/load preserves event timers, absolute time, calendar, and event history.
- Replay with same inputs produces same environment state.

### E2.0.8 - Weather Event Generation

Purpose: replace static initial weather with persistent generated fronts.

Scope:

- Generate next weather event from climate profile, calendar-derived season, recent conditions, region, and environment RNG.
- Support event durations in minutes.
- Support intensity.
- Support no-weather/clear as a weather event or lack of weather event, whichever is cleaner.
- Prevent rapid unrealistic weather churn.
- Avoid assuming weather is the only active event type.

Acceptance criteria:

- Weather persists for meaningful durations.
- Event generation is deterministic.
- Climate weights influence generated events.
- Tests cover rain, snow, fog, clear, windy, and storm fronts.

### E2.0.9 - Environmental Memory and Terrain Derivation

Purpose: make recent history affect terrain.

Scope:

- Track rain, snow, dry, freezing, storm, mud, snowpack, dust, drought, and thaw signals.
- Derive terrain condition from current event plus memory.
- Support indoor/underground terrain overrides.

Acceptance criteria:

- Sustained rain creates mud.
- Sustained dry weather creates dust/drought pressure.
- Snow plus freezing creates snowpack/deep snow.
- Warm rain after snow creates slush.
- Terrain derivation is deterministic and covered by tests.

### E2.0.10 - Scene Context Transitions

Purpose: keep player exposure accurate as location changes.

Scope:

- Add helpers for entering indoor, outdoor, sheltered, underground, and vehicle-like contexts.
- Ensure travel/location changes update `scene.environment_context` rather than mutating world weather.
- Add context metadata to starting locations.

Acceptance criteria:

- Tavern start is indoor/sheltered.
- Road/quarry/pass starts are outdoor or exposed as appropriate.
- Moving indoors changes exposure but not regional weather.
- Tests cover context transitions independently from weather.

### E2.0.11 - Narration Guardrails

Purpose: enforce environment authority boundary.

Scope:

- Add environment snapshot to narrator prompt/contract.
- Add explicit forbidden mutation rules.
- Add soft validator checks for narration contradicting current environment.
- Add deterministic correction/fallback for obvious contradictions.

Acceptance criteria:

- Narration may describe but not mutate environment.
- A prompt cannot cause the narrator to invent a sudden storm unless simulation already did.
- Tests cover common contradiction cases.

### E2.0.12 - Travel Consumer Integration

Purpose: let travel consume environment without owning it.

Scope:

- Travel reads terrain, visibility, hazards, wind, and light through environment service.
- Travel estimates can include environmental notes.
- Travel can pass elapsed minutes back to environment advancement.

Acceptance criteria:

- Mud/deep snow can affect travel estimates.
- Night/low visibility can surface risk warnings.
- Environment state remains owned by environment helpers.

### E2.0.13 - Tracking and Exploration Consumer Integration

Purpose: make investigation/exploration environment-aware.

Scope:

- Tracking reads terrain, precipitation history, visibility, snowpack, mud, and light.
- Exploration descriptions receive snapshot context.
- Evidence persistence can be influenced by environment memory.

Acceptance criteria:

- Mud/snow improves footprint visibility.
- Rain can wash away tracks over time.
- Fog/low light reduces long-distance perception.
- Tests consume environment through service only.

### E2.0.14 - Combat and Stealth Consumer Integration

Purpose: make tactical systems environment-aware.

Scope:

- Combat reads wind, visibility, terrain, exposure, and light.
- Stealth reads light level, weather noise, terrain, and visibility.
- Initial integration should annotate modifiers before changing balance deeply.

Acceptance criteria:

- Ranged attack context can include wind/visibility.
- Stealth context can include darkness/rain noise.
- Indoor combat ignores outdoor rain except for indirect context.
- Modifiers remain deterministic and testable.

### E2.0.15 - NPC Schedule Consumer Integration

Purpose: make living-world behavior environment-aware.

Scope:

- NPC schedules consume weather, light, hazards, season, and context preferences.
- NPCs may stay indoors during storms.
- Night/day activity differences become deterministic.

Acceptance criteria:

- NPC behavior reads environment snapshot, not narrator text.
- Storms affect outdoor activity in tests.
- NPC changes do not mutate environment.

### E2.0.16 - Environmental Resources and Economy Bridge

Purpose: turn environment history into long-lived world signals.

Scope:

- Add resource derivations for water availability, vegetation, soil moisture, forage, snowpack, drought pressure, and flood pressure.
- Economy/agriculture reads season, drought, frost, rain history, and hazards.
- Regional events can affect prices, food supply, road safety, and faction activity later.

Acceptance criteria:

- Drought/flood/frost state can influence local economy through deterministic signals in later consumers.
- Effects remain consumers of environment state.
- Resources are derived or domain-owned through explicit helpers, not narration.

### E2.0.17 - Survival and Exposure Consumer Integration

Purpose: make exposure deterministic without narrator invention.

Scope:

- Survival reads temperature, exposure, shelter, weather, wind, and terrain.
- Cold/heat risk is represented as deterministic context before any damage tuning.
- Rest quality can consume shelter and exposure later.

Acceptance criteria:

- Cold exposure can be represented without narrator invention.
- Indoor/sheltered context reduces outdoor exposure effects.
- Survival remains a consumer of environment snapshots.

### E2.0.18 - Region-Level Environment Simulation

Purpose: support multiple simultaneous regional environments.

Scope:

- Store per-region environment state.
- Active player region determines current snapshot.
- Offscreen regions can advance at coarser granularity.
- Travel between regions switches active snapshot.

Acceptance criteria:

- Northern Mountains can have snow while Southern Coast has rain.
- Player movement changes active environment without rewriting global weather.
- Save/load and replay remain deterministic.

### E3.0.0 - Ecology Consumer Layer

Purpose: make climate, season, weather history, and resources influence living-world ecology.

Scope:

- Derive wildlife activity.
- Derive fish activity.
- Derive plant growth and herb availability.
- Derive migration pressure.
- Derive predator pressure.
- Derive pest/disease risk.
- Feed ecology signals into encounters, economy, travel, and NPC behavior.

Acceptance criteria:

- Ecology reads environment/resource snapshots.
- Ecology does not own environment state.
- Winter plus heavy snow can deterministically raise predator pressure near settlements.
- Drought can deterministically lower forage and increase water-point encounters.

## Testing Strategy

Minimum test categories:

- Pure environment state creation from campaign contract and seed.
- Environment versioning and migration.
- Mandatory region id in new environment state.
- Calendar initialization and season derivation.
- Climate profile lookup and fallback.
- Derived snapshot determinism.
- Time advancement and event expiration.
- Weather event generation and persistence.
- Event history bounding and recording.
- Environmental memory and terrain derivation.
- Scene context separation.
- Compatibility migration for old sessions.
- UI rendering from snapshot.
- Narration contract guardrails.
- Replay determinism across save/load.

Required properties:

- Same seed + same contract + same action sequence = same environment state.
- Derived values are pure functions of authoritative state and profiles.
- LLM output never mutates environment.
- Consumer systems access environment through service helpers, not scattered ad hoc condition checks.
- Single-region state can migrate to multi-region state without losing region identity.

## Migration Plan

Existing sessions may only have:

```json
{
  "world": {
    "time": "Day 1 - Morning",
    "weather": "Rainy",
    "temperature": null
  }
}
```

Migration approach:

1. Preserve old fields for display compatibility.
2. On load or next write, create `world.environment` with deterministic fallback seed.
3. Set `environment_version`.
4. Assign `region_id`, defaulting to `starting_region` or a location-derived region.
5. Initialize `calendar` from campaign contract, location, or deterministic fallback.
6. Infer starting absolute minutes from known time labels where possible.
7. Assign climate profile from current location when possible.
8. Convert known weather string into an initial weather event only if safe.
9. Initialize recent conditions and bounded event history.
10. Mark migrated state with metadata for debugging.

No migration should invent precise values that look authoritative unless produced by deterministic profiles.

## Open Design Decisions

- Whether clear weather should be represented as an explicit weather event or absence of a weather event.
- Whether `environment_seed` should be a standalone stream seed or derived from campaign seed plus domain labels per event generation.
- Whether `active_events` remains a single typed list or evolves into indexed event buckets.
- How many season IDs to support in v1: four seasons or early/mid/late variants.
- Whether environmental memory stores raw minute counters, normalized levels, or both.
- How much event history to retain in the active save.
- Which environmental resources belong in Environment Domain versus Economy/Ecology read models.
- How much offscreen region environment should advance before region-level simulation ships.
- Whether climate profiles should be JSON data, Python constants, or repository-backed content files.

## Non-Goals for Initial Infrastructure Slice

Do not include these in E2.0.1:

- Combat penalties.
- Travel penalties.
- Survival damage.
- NPC schedule changes.
- Economy/farming impact.
- Ecology simulation.
- LLM-authored weather changes.
- Region-wide offscreen simulation.
- Procedural climate map generation.

## Definition of Done for Environment 2.0 Foundation

The foundation is complete when:

- New campaigns persist authoritative `world.environment` state.
- New campaigns persist `environment_version`, `region_id`, `calendar`, `absolute_minutes`, and `environment_seed`.
- New campaigns persist separate `scene.environment_context` state.
- Environment snapshots are derived, deterministic, and exposed to UI/narration.
- Existing sessions migrate safely.
- UI displays snapshot-backed environment truth without decorative or fake values.
- Narration cannot create or mutate weather/time/season.
- Save/load/replay preserve deterministic environment evolution.
- Consumer systems have a central environment service API ready for mechanics integration.
- The design remains compatible with future regional resources, event history, ecology, and multi-region simulation.
