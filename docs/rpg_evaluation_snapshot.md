# RPG Evaluation Snapshot

Date: 2026-05-30
Branch: `rpg-v1.36`
Purpose: baseline evaluation snapshot to revisit later and measure improvement.

## 1. Executive Summary

The RPG project is architecturally strong but not yet production-ready as a game. It is best described as a serious AI RPG engine prototype or vertical-slice framework. The core boundary is correct: deterministic simulation is authoritative, while the LLM is advisory or presentational unless deterministic runtime code explicitly resolves state.

The project has unusually strong observability for this stage: matrix tests, manual scenarios, source fields, diagnostics, performance traces, and report artifacts. The recent CE.2.12 and CE.2.13 work significantly improved fast combat and removed harness/app drift in fast-direct gameplay routing.

The main weakness is not architecture. The main weakness is game depth: combat, economy, quests, travel, party, world simulation, NPC schedules, faction consequences, and player-facing UX are still closer to testable prototypes than production-quality RPG systems.

## 2. Current Scorecard

Scores are from 1 to 10. Target for production readiness is 8/10 or better across all major categories.

| Category | Current Score | Production Target | Notes |
|---|---:|---:|---|
| Architecture / system design | 8.0 | 8.5+ | Correct deterministic/LLM boundary and runtime-first design. Needs modular cleanup as runtime grows. |
| LLM grounding / hallucination control | 7.5 | 8.5+ | Strong principles, source fields, and grounding packets. Needs broader final claim validator and long-run proof. |
| Runtime performance architecture | 7.0 | 8.5+ | Fast combat/survival/travel are strong. First-call provider turns remain slower. |
| Testability / diagnostics | 8.0 | 9.0+ | Matrix, traces, source fields, reports, and regressions are a major strength. |
| Core gameplay mechanics | 4.5 | 8.0+ | Many systems exist, but most need depth and balance. |
| Game design / player experience | 4.0 | 8.0+ | Strong engine direction, but current game likely feels scenario-shaped. |
| NPC roleplay potential | 6.5 | 8.5+ | Good grounding/profile/memory architecture; needs content, schedules, agency, and evolution depth. |
| Long-run 100-turn readiness | 5.0 | 8.0+ | Plausible with focused work. Needs save/load, loop detection, progression, and richer mechanics. |
| Long-run 1000-turn readiness | 2.5 | 8.0+ | Needs robust world systems, compression, memory aging, factions, schedules, and end-state handling. |
| Production readiness | 3.0 | 8.0+ | Not ready for real players outside internal testing/prototype use. |
| Commercial/game-quality readiness | 2.5 | 8.0+ | Strong R&D foundation, not yet a polished game. |

## 3. Current Validated Strengths

### 3.1 Architecture Boundary

The most important design choice is correct: runtime is the source of truth. LLM output may classify, advise, or narrate, but cannot directly decide combat damage, prices, inventory, XP, quests, travel success, or final state.

### 3.2 Two-Call Interactive Runtime

The interactive design is strong:

```text
player input
  -> grounded first-call advisory
  -> deterministic runtime resolution
  -> narration contract
  -> deterministic/deferred/provider presentation
```

This is the right shape for a grounded AI RPG.

### 3.3 CE.2.12 Fast Combat

Fast combat now skips synchronous combat narration. Validated behavior from recent matrix runs:

```text
Matrix: 8/8 passed
Combat avg: ~0.06-0.10s
Combat llm_turn_count: 0
Combat slow turns: 0
```

This solved a major performance and grounding issue.

### 3.4 CE.2.13 Runtime/Harness Convergence

Manual harness fast-direct gameplay routing was removed. Fast-direct combat/survival/travel now route through `interactive_first_call_runtime.apply_turn`, reducing the risk that tests pass through behavior the real app does not use.

### 3.5 Observability and Regression Culture

The project has strong testing and reporting culture:

- Interactive intent matrix.
- Manual service scenarios.
- Autoplay campaign reports.
- Provider call diagnostics.
- Token usage tracking.
- Turn/performance traces.
- Narration sources.
- First-call grounding diagnostics.
- Scenario warnings and regression warnings.

This is a major advantage for AI-game development.

## 4. Current Weaknesses

### 4.1 Mechanics Are Broad But Shallow

The engine has many systems, but most are still shallow. Current mechanics are good enough for validation scenarios but not yet enough for a compelling multi-hour RPG loop.

Priority systems needing depth:

1. Combat lifecycle.
2. Economy/inventory.
3. Quest lifecycle.
4. Travel/location graph.
5. Party/companions.
6. NPC memory/evolution.
7. Factions/reputation.

### 4.2 Combat Is Fast But Not Yet Deep

Current fast combat is excellent technically, but game-quality combat still needs:

- Initiative.
- Enemy turns.
- Hit/miss/crit.
- Armor and weapons.
- Skills and stats affecting outcomes.
- Status effects.
- Multiple enemies.
- Companion actions.
- Escape/surrender/social resolution.
- XP and loot hooks.
- Clear combat log UI.

### 4.3 Economy Is Scenario-Capable, Not Yet Systemic

The economy needs:

- Canonical item database.
- Merchant stock and quantities.
- Buy/sell rules.
- Room/rest effects.
- Food/water consumption.
- Price modifiers from charisma/reputation.
- Loot economy.
- Quest rewards.
- UI/report tables for inventory and transactions.

### 4.4 Travel and World Simulation Are Early

Travel needs:

- Full location graph.
- Distance/time costs.
- Random/seeded encounters.
- Discovery state.
- Regional danger.
- Weather/season/time.
- NPC schedules by location.
- Travel supplies and fatigue impact.
- Map UI.

### 4.5 NPCs Need Content, Schedules, and Agency

NPC grounding is promising, but the game needs actual content and long-run behavior:

- File-backed profiles for major NPCs.
- Memory aging and importance.
- Relationship scoring.
- Dialogue style consistency.
- NPC schedules.
- NPC-to-NPC conversations.
- Faction membership.
- Evolution arc persistence.
- Companion personality changes over time.

### 4.6 Player-Facing UX Is Not Yet Production Quality

A production RPG needs clear UI for:

- Current objective.
- Suggested actions.
- Inventory/currency.
- Combat log.
- Party panel.
- Journal.
- Map/location view.
- NPC relationship view.
- Save/load.
- Narration/provider/media settings.

### 4.7 Runtime Modularity Risk

`session/runtime.py` appears to own many responsibilities: persistence, turn execution, gameplay resolution, frontend payloads, narration selection, stale text repair, and provider narration coordination. This is acceptable for prototype speed but should be decomposed before production.

## 5. Readiness Tier Assessment

### Tier 1: Engineering Prototype

Status: mostly achieved.

The engine has a serious architecture, tests, matrix validation, and strong diagnostics.

### Tier 2: Internal Playable Vertical Slice

Status: partially achieved, not complete.

A real vertical slice needs 30-60 minutes of coherent play with a complete loop:

- Intro scene.
- 3-5 locations.
- 3-5 NPCs with profiles.
- One complete quest chain.
- One shop/inn loop.
- One combat loop.
- One companion path.
- One travel route.
- Journal and save/load.
- Stable UI.

### Tier 3: Alpha Game

Status: not yet.

Alpha requires several hours of stable play, balanced systems, save/load reliability, UI polish, quest variety, world persistence, crash handling, and player onboarding.

### Tier 4: Production / Commercial Release

Status: far away.

Production requires packaging, settings UX, error recovery, content volume, QA matrix, performance consistency, provider fallback UX, privacy/security review, mod/content tools, tutorials, and polish.

## 6. Biggest Improvement Levers

### 6.1 Build One Strong Vertical Slice

Recommended vertical slice:

```text
Rusty Flagon -> road -> old mill -> bandit conflict -> Bran/Elara/Aldric -> food + room -> rumor + quest -> combat -> companion -> journal -> save/load
```

This will force combat, economy, travel, NPC, quest, party, journal, and save/load to work together.

### 6.2 Deepen Existing Mechanics Before Adding New Categories

The project should now prioritize system depth over adding more broad systems.

### 6.3 Add a Grounded Claim Validator

Every final visible response should be auditable for hard state claims. This is essential for long-run trust.

### 6.4 Strengthen Save/Load and Long-Run Determinism

Save/load, checkpoint validation, and replay determinism are required before 100-turn and 1000-turn readiness can be trusted.

### 6.5 Improve Player UX

A strong backend will still feel weak if the player cannot see objectives, inventory, party, journal, map, and combat state clearly.

## 7. Baseline Metrics To Track Over Time

| Metric | Baseline | Target |
|---|---:|---:|
| Interactive matrix pass rate | 8/8 | 8/8 and expanding |
| Fast combat avg | ~0.06-0.10s | <0.15s |
| Fast combat LLM calls | 0 | 0 |
| First-call provider turn avg | ~4-5s | <2.5s, then <1.5s |
| 100-turn critical warnings | not yet final | 0 |
| 100-turn save/load checkpoints | incomplete | pass |
| 1000-turn completion | not ready | pass with bounded report size |
| Combat lifecycle coverage | shallow | full lifecycle |
| Quest lifecycle coverage | shallow | complete quest chain coverage |
| NPC memory/evolution coverage | partial | long-run persistent evolution |
| UI feature completeness | early | production-useful panels |

## 8. Revisit Checklist

When revisiting this document, answer:

1. Did scores improve by category?
2. Did the matrix remain 8/8 or expand without regressions?
3. Are first-call provider turns faster?
4. Does 100-turn autoplay pass with no critical warnings?
5. Does save/load checkpoint validation pass?
6. Does combat include enemy turns, initiative, XP, loot, and logs?
7. Does economy include canonical item/shop/price/stock data?
8. Does at least one quest chain complete end-to-end?
9. Do NPCs persist memory and evolve across sessions?
10. Does the UI support normal human play without reading debug reports?

## 9. Summary Judgment

Current state: **excellent prototype foundation, not yet production-ready game**.

Best current identity:

```text
A well-instrumented deterministic AI RPG engine prototype with grounded LLM interpretation and narration.
```

Target identity:

```text
A production-quality AI-assisted RPG where natural-language play, deterministic mechanics, persistent NPCs, and rich world progression work together for hours of stable play.
```
