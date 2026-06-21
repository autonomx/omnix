# RPG Environment System 2.0 Roadmap

Environment System 2.0 treats environment as a deterministic simulation domain, not as cosmetic weather labels and not as narration-owned flavor. Weather is only one event type inside a broader environment model that also covers time, season, climate, temperature, wind, visibility, light, terrain conditions, natural hazards, and environmental events.

This roadmap is intentionally infrastructure-first. The first implementation slices establish authoritative state, deterministic derivation, UI truthfulness, and narration contracts. Travel, combat, stealth, tracking, survival, NPC schedules, agriculture, and economy systems should consume environment snapshots later, but they should not be mixed into the initial environment-state slice.

Related planning issue: #669.

## Core Principle

Environment is a simulation domain.

The backend simulation owns environment state and environment advancement. The LLM narrator may describe the current environment, emphasize it, and interpret it in prose, but may never create, modify, contradict, or advance environment state.

## Responsibilities

Environment owns:

- Time progression and display derivation.
- Season progression.
- Climate profile assignment.
- Weather and weather-front events.
- Temperature derivation.
- Wind derivation.
- Visibility derivation.
- Light-level derivation.
- Terrain-condition derivation.
- Natural hazards.
- Environmental events.
- Environmental memory, such as recent rain, snowpack, dry days, mud persistence, drought pressure, thaw state, and storm history.

Environment does not own:

- NPC schedules.
- Travel speed.
- Combat modifiers.
- Stealth modifiers.
- Tracking modifiers.
- Quest behavior.
- Faction behavior.
- Economy behavior.
- Narration wording.

Those systems consume environment snapshots through a service API.

## Architecture Layers

### Layer 1: Authoritative Environment State

Persist only minimal source-of-truth state under `world.environment`.

Example target shape:

```json
{
  "world": {
    "environment": {
      "absolute_minutes": 480,
      "season_id": "late_autumn",
      "climate_profile_id": "temperate_hills",
      "environment_seed": 482193,
      "active_events": [
        {
          "id": "weather_001",
          "type": "weather",
          "condition": "rain",
          "intensity": "moderate",
          "remaining_minutes": 840
        }
      ],
      "recent_conditions": {
        "rain_minutes_24h": 180,
        "snow_minutes_24h": 0,
        "dry_minutes_72h": 0,
        "freezing_minutes_24h": 0
      }
    },
    "reputation": {
      "label": "Unknown",
      "score": 0
    }
  }
}
```

Do not persist temperature, visibility, light level, terrain condition, or display weather as mutable source-of-truth fields. Those are derived values. This prevents invalid state combinations such as snow at 25C or night at 14:00.

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
      "region_id": "rusty_flagon_region",
      "location_id": "rusty_flagon_tavern"
    }
  }
}
```

This allows the world to be snowing at -20C while the player is inside a warm inn. The world is not indoor or outdoor; the current scene is.

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
  }
}
```

Climate profiles should support fantasy, post-apocalyptic, sci-fi, cyberpunk, and other genres without redesign. Genre-specific hazards such as arcane storms, toxic clouds, radiation fronts, solar flares, volcanic ash, or nanite fog should be represented as typed events.

### Layer 4: Environment Events

Environment events are the engine of the system. Weather fronts are events, not a standalone weather field.

Event examples:

```json
{
  "id": "weather_001",
  "type": "weather",
  "condition": "snow",
  "intensity": "moderate",
  "remaining_minutes": 960
}
```

```json
{
  "id": "hazard_001",
  "type": "natural_hazard",
  "condition": "avalanche_risk",
  "intensity": "low",
  "remaining_minutes": 240
}
```

```json
{
  "id": "anomaly_001",
  "type": "arcane_weather",
  "condition": "mana_storm",
  "intensity": "severe",
  "remaining_minutes": 120
}
```

Event fields should include:

- `id`: deterministic event id.
- `type`: weather, natural_hazard, anomaly, regional_effect, pollution, radiation, volcanic, etc.
- `condition`: rain, snow, fog, blizzard, heat_wave, cold_snap, dust_storm, toxic_cloud, solar_flare, etc.
- `intensity`: trace, light, moderate, heavy, severe, extreme.
- `remaining_minutes`: persistence timer.
- Optional `region_id` when regional simulation is introduced.
- Optional `metadata` for genre-specific values.

Weather should persist through fronts/events. It should not reroll every turn. When an event expires, a deterministic environment RNG generates the next event from climate profile, season, recent conditions, and campaign/environment seed.

### Layer 5: Derivation Engine

The derivation engine computes snapshots from authoritative state, climate profile, scene context, active events, and recent history.

Example snapshot:

```json
{
  "day": 1,
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
  "hazards": []
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

Future consumers:

- Travel service consumes terrain condition, visibility, wind, hazards, and light.
- Combat consumes wind, visibility, terrain, exposure, and light.
- Stealth consumes light, weather noise, terrain, and visibility.
- Tracking consumes terrain history, precipitation, snowpack, mud, and visibility.
- NPC scheduling consumes weather, light, hazards, and exposure preferences.
- Economy/agriculture consumes season, weather history, drought, frost, and floods.
- Narration consumes a safe read-only snapshot.
- UI consumes display-ready snapshot fields.

### Layer 7: Time System

Use `absolute_minutes` internally.

Derive:

- Day number.
- Minute of day.
- Hour/minute display.
- Time block: pre_dawn, dawn, morning, midday, afternoon, dusk, evening, night, deep_night.
- Season.
- Sunrise/sunset from climate profile and season.

Recommended first rules:

- Normal turn: +10 minutes.
- Wait action: +30 to +120 minutes, depending on command.
- Short rest: +60 minutes.
- Long rest/sleep: +480 minutes.
- Travel: explicit minutes from route, terrain, and later weather modifiers.

Do not expose minute precision everywhere in UI. Internally use minutes; display can stay readable.

### Layer 8: Season Progression

Season should derive from absolute day and campaign calendar configuration.

Initial season can come from:

- Campaign Contract.
- Region or starting location.
- Genre/tone.
- Explicit player setup option.
- Deterministic default from campaign seed.

Recommended season IDs:

- early_spring
- spring
- summer
- early_autumn
- late_autumn
- winter

A simpler four-season model can be displayed, but the simulation benefits from early/late shoulder seasons.

### Layer 9: Environmental Memory

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

### Layer 10: Region-Level Simulation

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

The first implementation may store one active-region environment under `world.environment`, but APIs and data naming should avoid blocking later regionalization.

### Layer 11: Narration Contract 2.0

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

### Layer 12: UI Contract

The UI should show only authoritative or derived environment values.

World State target fields:

- Season.
- Day/time.
- Weather.
- Temperature.
- Wind.
- Visibility.
- Light.
- Terrain.
- Context: indoor, outdoor, sheltered, underground.
- Hazards, if active.

Missing values should display `Not tracked yet`, not invented values. Temporary compatibility fields such as `world.weather` can remain during migration, but final UI should read from `environment_snapshot`.

Reputation should eventually move out of World State into a social/faction card because it is not environment.

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
- Add `absolute_minutes` time base.
- Add `environment_seed` generated from campaign seed and campaign contract.
- Add initial typed weather event.
- Add initial `recent_conditions` object with deterministic defaults.
- Add `scene.environment_context` for starting locations.
- Preserve existing compatibility fields `world.time`, `world.weather`, and `world.temperature` as read-only projections where needed.

Out of scope:

- Travel penalties.
- Combat penalties.
- Survival penalties.
- NPC schedule changes.
- Stealth/tracking modifiers.

Acceptance criteria:

- Same campaign seed and contract produce identical `world.environment`.
- Different seeds can produce different initial events within the same climate profile.
- Stored state does not persist derived temperature, visibility, light, or terrain as mutable fields.
- Scene context can be indoor while world weather remains outdoor/global.
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
- Map existing starting locations to climate profiles.

Acceptance criteria:

- Every starting location resolves to a climate profile.
- Climate profile lookup is pure and deterministic.
- Missing profile falls back to a deterministic safe default and records a warning/metadata flag.
- Tests cover profile lookup and seasonal ranges.

### E2.0.3 - Derived Environment Snapshot

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
- Add display labels.

Acceptance criteria:

- Snapshot is deterministic for same state and seed.
- Snapshot is not persisted as source of truth.
- Snapshot supports indoor tavern during outdoor rain/snow.
- Tests prevent invalid derived combinations where possible.

### E2.0.4 - API and Session Surface

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

### E2.0.5 - UI World State 2.0

Purpose: replace shallow world-state display with snapshot-backed truth.

Scope:

- Render Season, Day/Time, Weather, Temperature, Wind, Visibility, Light, Terrain, Context, and Hazards.
- Move or separate Reputation from Environment when practical.
- Mark unavailable values as `Not tracked yet` only when snapshot truly lacks them.
- Avoid decorative controls.

Acceptance criteria:

- New campaign displays snapshot-backed environment values.
- Indoor context displays clearly without hiding outdoor weather.
- UI tests ensure no fake/inferred values outside backend snapshot.
- No unwired environment controls are visible.

### E2.0.6 - Deterministic Time Advancement

Purpose: make turns advance time through simulation.

Scope:

- Add environment time advancement helper.
- Normal turn advances +10 minutes by default.
- Travel/rest/wait can pass explicit elapsed minutes when those systems are ready.
- Decrement active event timers.
- Update recent condition counters.
- Roll next event only when needed.

Acceptance criteria:

- 10 normal turns advance 100 minutes.
- Expired events generate deterministic replacements.
- Save/load preserves event timers and absolute time.
- Replay with same inputs produces same environment state.

### E2.0.7 - Weather Event Generation

Purpose: replace static initial weather with persistent generated fronts.

Scope:

- Generate next weather event from climate profile, season, recent conditions, and environment RNG.
- Support event durations in minutes.
- Support intensity.
- Support no-weather/clear as a weather event or lack of weather event, whichever is cleaner.
- Prevent rapid unrealistic weather churn.

Acceptance criteria:

- Weather persists for meaningful durations.
- Event generation is deterministic.
- Climate weights influence generated events.
- Tests cover rain, snow, fog, clear, windy, and storm fronts.

### E2.0.8 - Environmental Memory and Terrain Derivation

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

### E2.0.9 - Scene Context Transitions

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

### E2.0.10 - Narration Guardrails

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

### E2.0.11 - Travel Consumer Integration

Purpose: let travel consume environment without owning it.

Scope:

- Travel reads terrain, visibility, hazards, wind, and light through environment service.
- Travel estimates can include environmental notes.
- Travel can pass elapsed minutes back to environment advancement.

Acceptance criteria:

- Mud/deep snow can affect travel estimates.
- Night/low visibility can surface risk warnings.
- Environment state remains owned by environment helpers.

### E2.0.12 - Tracking and Exploration Consumer Integration

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

### E2.0.13 - Combat and Stealth Consumer Integration

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

### E2.0.14 - NPC Schedule Consumer Integration

Purpose: make living-world behavior environment-aware.

Scope:

- NPC schedules consume weather, light, hazards, season, and context preferences.
- NPCs may stay indoors during storms.
- Night/day activity differences become deterministic.

Acceptance criteria:

- NPC behavior reads environment snapshot, not narrator text.
- Storms affect outdoor activity in tests.
- NPC changes do not mutate environment.

### E2.0.15 - Survival, Economy, and Long-Horizon Effects

Purpose: turn environment history into long-lived world consequences.

Scope:

- Survival reads temperature, exposure, shelter, weather, and terrain.
- Economy/agriculture reads season, drought, frost, rain history, and hazards.
- Regional events can affect prices, food supply, road safety, and faction activity.

Acceptance criteria:

- Cold exposure can be represented without narrator invention.
- Drought/flood/frost state can influence local economy through deterministic signals.
- Effects remain consumers of environment state.

### E2.0.16 - Region-Level Environment Simulation

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

## Testing Strategy

Minimum test categories:

- Pure environment state creation from campaign contract and seed.
- Climate profile lookup and fallback.
- Derived snapshot determinism.
- Time advancement and event expiration.
- Weather event generation and persistence.
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
3. Infer starting absolute minutes from known time labels where possible.
4. Assign climate profile from current location when possible.
5. Convert known weather string into an initial weather event only if safe.
6. Mark migrated state with metadata for debugging.

No migration should invent precise values that look authoritative unless produced by deterministic profiles.

## Open Design Decisions

- Whether clear weather should be represented as an explicit weather event or absence of a weather event.
- Whether `environment_seed` should be a standalone stream seed or derived from campaign seed plus domain labels per event generation.
- How many season IDs to support in v1: four seasons or early/mid/late variants.
- Whether environmental memory stores raw minute counters, normalized levels, or both.
- How much offscreen region environment should advance before region-level simulation ships.
- Whether climate profiles should be JSON data, Python constants, or repository-backed content files.

## Non-Goals for Initial Infrastructure Slice

Do not include these in E2.0.1:

- Combat penalties.
- Travel penalties.
- Survival damage.
- NPC schedule changes.
- Economy/farming impact.
- LLM-authored weather changes.
- Region-wide offscreen simulation.
- Procedural climate map generation.

## Definition of Done for Environment 2.0 Foundation

The foundation is complete when:

- New campaigns persist authoritative `world.environment` state.
- New campaigns persist separate `scene.environment_context` state.
- Environment snapshots are derived, deterministic, and exposed to UI/narration.
- Existing sessions migrate safely.
- UI displays snapshot-backed environment truth without decorative or fake values.
- Narration cannot create or mutate weather/time/season.
- Save/load/replay preserve deterministic environment evolution.
- Consumer systems have a central environment service API ready for mechanics integration.
