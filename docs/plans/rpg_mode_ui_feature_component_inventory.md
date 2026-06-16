# RPG Mode UI Feature and Component Inventory

Status: planning source for the RPG mode redesign.
Scope: inventory the current and planned RPG gameplay features, then map each feature to the UI components needed before visual design work starts.
Branch target: `rpg`.

## Purpose

The current RPG workspace is a platform-style job form: choose a session, submit a command, watch an `rpg.turn` job, and browse sessions, reports, and assets. That is useful for plumbing, but it does not yet feel like a game client.

This document is the first redesign artifact. It should be updated before generating mockups so every design proposal can be checked against gameplay requirements instead of only aesthetic preference.

## Design principles

1. **Simulation remains authoritative.** UI components show state, explain validation, and submit commands. They must not invent gameplay truth.
2. **Narration is presentation, not state.** LLM text can enrich the scene, but deterministic turn results, legal actions, inventory, currency, objectives, combat state, and checkpoint data remain the source of truth.
3. **Game-first, diagnostics-available.** The default view should look like an RPG cockpit. Reports, traces, prompts, jobs, and validation panels should be available but not dominate normal play.
4. **Replay-preserving by default.** Session, checkpoint, command history, and report actions need clear provenance and safe restore/export affordances.
5. **Local-first transparency.** Provider/model/worker state should be visible enough to explain delays without making the player manage infrastructure during every turn.

## Existing web shell surfaces

Current `RpgWorkspace` surfaces:

- Session selector from replay persistence inventory.
- Command text area.
- `rpg.turn` job creation with `determinism_policy: replay_preserving`.
- Four job stages: load session, apply deterministic turn, generate narration, write checkpoint.
- RPG job list with status pill and progress.
- Session inventory list.
- Autoplay report list.
- RPG asset list.
- Shared submit feedback and validation message.

These should be retained as underlying capabilities, but reorganized into game-oriented panels.

## Primary screen model

The redesigned RPG mode should be treated as a game client with five persistent zones:

| Zone | Purpose | Primary components |
|---|---|---|
| Top game bar | Session, save/replay status, provider/worker state, mode, elapsed turn context | `RpgGameHeader`, `SessionStatusChip`, `DeterminismLock`, `ProviderStatusChip`, `CheckpointButton`, `ReportButton` |
| Center play canvas | Main narrative, scene, active turn result, command composer | `SceneViewport`, `NarrativeFeed`, `TurnComposer`, `SuggestedActions`, `TurnResultCard`, `SceneMediaRail` |
| Left player rail | Player-visible state and resources | `PlayerHud`, `CurrencyMeter`, `InventorySummary`, `PartySummary`, `TimeWeatherChip`, `WarningStack` |
| Right context rail | Context-sensitive gameplay panels | `ObjectiveJournal`, `NpcContextPanel`, `CombatPanel`, `ServicePanel`, `WorldEventsPanel`, `MemoryContinuityPanel` |
| Bottom drawer/tabs | Deep tools without crowding the main loop | `MapTravelDrawer`, `InventoryDrawer`, `JournalDrawer`, `ReportsDrawer`, `ReplayDrawer`, `DiagnosticsDrawer` |

## Feature-to-component inventory

### 1. Session, save/load, replay, and checkpoints

| Feature | Player need | UI components | Key states/data | Notes |
|---|---|---|---|---|
| New/current session | Start quickly or continue last run | `SessionPicker`, `NewSessionButton`, `ContinueButton` | none, current, selected, loading, invalid | Current selector becomes a richer session launcher. |
| Save/checkpoint write | Know when progress is durable | `CheckpointButton`, `CheckpointStatusToast`, `AutosaveIndicator` | clean, writing, written, failed, stale | Should show checkpoint digest/provenance in details. |
| Load/restore | Restore safely without corrupting replay | `CheckpointBrowser`, `RestorePreview`, `RestoreConfirmDialog` | selected checkpoint, digest, timestamp, compatibility | Confirm restore before changing active session. |
| Replay history | Inspect deterministic turn sequence | `CommandTimeline`, `TurnReplayStepper`, `ReplayDiffPanel` | turn index, command, result, digest, drift flags | Essential for debugging and player trust. |
| Export/share evidence | Produce report bundle or ZIP | `ExportReportButton`, `BundleStatusPanel` | available reports, ZIP members, missing artifacts | Must separate player-facing export from debug bundle. |

### 2. Turn loop and command submission

| Feature | Player need | UI components | Key states/data | Notes |
|---|---|---|---|---|
| Free-form command | Type natural RPG action | `TurnComposer`, `CommandInput`, `SubmitTurnButton` | empty, dirty, submitting, blocked, accepted | Replaces the current plain text area. |
| Legal action suggestions | Avoid invalid commands and discover systems | `SuggestedActionChips`, `ActionCategoryTabs`, `ContextualActionMenu` | travel, dialogue, combat, service, inventory, inspect | Chips submit text commands or fill composer. |
| Runtime validation | Understand why a command is blocked | `ValidationBanner`, `CommandErrorDetails` | missing command, illegal in combat, cannot afford, no target | Must cite the runtime validator category. |
| Turn progress | See deterministic stage progress | `TurnStageTracker`, `JobProgressMiniTimeline` | load-session, apply-turn, narrate, checkpoint | Current job stages become inline turn-progress UI. |
| Recent commands | Repeat or inspect prior actions | `CommandHistoryDropdown`, `RetryLastCommandButton` | prior commands, turn IDs, status | Include no-op/loop warnings when available. |

### 3. Narrative, scene, and transcript

| Feature | Player need | UI components | Key states/data | Notes |
|---|---|---|---|---|
| Current scene narration | Read the latest resolved scene | `SceneNarrationCard`, `NarrativeFeed` | authoritative state summary, narration text, validation markers | Narration should be visibly attached to a turn. |
| Turn result summary | Understand mechanical effects | `TurnOutcomeCard`, `StateDeltaList` | gained/lost items, currency, XP, objective changes, location changes | Show mechanics separately from prose. |
| Transcript | Review story history | `TranscriptPanel`, `TurnAnchorLinks`, `SearchTranscriptInput` | turn number, action, category, NPC lines | Support report anchors later. |
| Grounding/validation notes | Trust the generated text | `GroundingStatusBadge`, `CorrectionNotice`, `AuditDrawer` | passed, corrected, fallback, audit pending | Default collapsed; debug accessible. |
| Recap/chronicle | Summarize what happened | `ChroniclePanel`, `WhatILearnedList`, `NextStepsList` | recent recap, discoveries, next objectives | Good for longer sessions and 100-turn runs. |

### 4. Player HUD and visible state

| Feature | Player need | UI components | Key states/data | Notes |
|---|---|---|---|---|
| Character identity | Know who/where the player is | `PlayerIdentityCard`, `LocationBadge` | player name, level, location, status | Top of left rail. |
| Stats and progression | See strength/charisma/archery/level/XP | `StatsPanel`, `XpProgressBar`, `SkillUseBadges` | level, XP, stats, skill usage | XP should only reflect deterministic reward events. |
| Currency | Understand gold/silver/copper | `CurrencyMeter`, `AffordabilityIndicator` | gold, silver, copper, pending cost | Must support canonical denominations. |
| Inventory | Know carried items and equipment | `InventorySummary`, `InventoryDrawer`, `ItemCard` | items, quantity, equipped, quest item | Summary in rail, full inventory in drawer. |
| Warnings | See blocked/missing/high-risk state | `WarningStack`, `CriticalStateBanner` | no objective, low funds, combat lock, stale checkpoint | Warnings should be compact but visible. |

### 5. Objectives, journal, quests, and story arcs

| Feature | Player need | UI components | Key states/data | Notes |
|---|---|---|---|---|
| Active objective | Know what to do next | `ActiveObjectiveCard`, `ObjectiveProgressPips` | active, completed, blocked, failed | Should be always visible or one click away. |
| Quest log | Browse all objectives | `ObjectiveJournal`, `QuestFilterTabs` | active/available/completed/blocked | Current objective/journal panel becomes a right-rail panel. |
| Journal entries | Read discoveries and outcomes | `JournalEntryList`, `JournalEntryCard` | turn, source, text, tags | Include source turn/action for replay. |
| Story arcs/director | Track campaign pressure without spoilers | `StoryArcMeter`, `DirectorBeatTimeline` | arc state, escalation, unresolved hooks | Keep spoiler-sensitive details collapsed. |
| Hints/next actions | Reduce dead-end loops | `NextActionHints`, `ProgressQualityNotice` | suggested next, stuck/loop status | Hints should be grounded in objectives, not invented by UI. |

### 6. NPCs, dialogue, persona, and memory

| Feature | Player need | UI components | Key states/data | Notes |
|---|---|---|---|---|
| NPC presence | Know who is nearby | `NpcRoster`, `NpcPresenceCard` | NPC id, name, role, location, disposition | Right rail or scene sidebar. |
| Direct dialogue | Speak to an NPC | `DialogueTargetPicker`, `DialogueComposerMode`, `NpcReplyCard` | target, conversation thread, last reply | Composer can switch from action to dialogue mode. |
| Ambient/group conversation | See living-world chatter | `AmbientDialogueFeed`, `ConversationThreadCard` | directed, ambient, group, active/idle | Keep separate from player-command transcript. |
| Persona/biography | Understand character style and relationship | `NpcProfileSheet`, `SpeakingStyleBadge`, `RelationshipMeter` | biography, personality, speaking style, relationship | Profile sheet opens from NPC card. |
| Memory continuity | Inspect remembered facts | `MemoryContinuityPanel`, `RememberedFactCard`, `MemoryGroundingBadge` | actor/world memory, public/private, salience, source turn | Normal UI shows only useful memories; debug shows IDs. |
| Rumors/social state | Track gossip and tension | `RumorBoard`, `TensionMeter`, `GuardAttentionBadge` | rumor, source, visibility, faction/location scope | Useful for guards/intervention/social consequences. |

### 7. Party and companions

| Feature | Player need | UI components | Key states/data | Notes |
|---|---|---|---|---|
| Party roster | Know companions and roles | `PartySummary`, `PartyRosterDrawer` | member, role, status, relationship | Compact in left rail. |
| Recruitment | Invite eligible NPCs | `RecruitmentPrompt`, `JoinPartyButton`, `EligibilityReasonList` | eligible, blocked, accepted, declined | Must show why a companion can/cannot join. |
| Companion actions | Use party capabilities | `CompanionActionChips`, `PartyTacticsPanel` | assist, guard, scout, talk | Submit commands through existing turn flow. |
| Companion memory | See relationship continuity | `CompanionMemoryCard` | shared history, recent events, trust | Grounded by memory system. |

### 8. Combat and danger state

| Feature | Player need | UI components | Key states/data | Notes |
|---|---|---|---|---|
| Combat lock | Know when non-combat actions are blocked | `CombatStateBanner`, `CombatLockBadge` | in combat, awaiting player, resolving NPC turn, ended | Must be prominent. |
| Initiative/order | Understand turn order | `InitiativeTracker`, `CombatantChip` | player/NPC/enemy order, active actor | Good for avoiding spam. |
| Legal combat actions | Choose attack/defend/flee/items/talk | `CombatActionPanel`, `TargetPicker`, `ActionValidityBadge` | legal/illegal, selected target, stamina/resources | Should replace generic suggestions during combat. |
| Enemy and ally status | See health/condition/threat | `CombatantStatusCard`, `ThreatMeter` | health, condition, distance, role | Use only deterministic visible info. |
| Combat results | See damage, loot, XP, quest changes | `CombatLog`, `RewardSummary`, `DefeatOutcomePanel` | hit/miss, damage, XP, loot, death/flee | Rewards must match simulation outputs. |

### 9. Travel, map, time, weather, and location

| Feature | Player need | UI components | Key states/data | Notes |
|---|---|---|---|---|
| Current location | Know where the scene is | `LocationHeader`, `PlaceCard` | location id/name, region, safety, services | In header and map drawer. |
| Travel options | Move without guessing valid exits | `TravelOptionList`, `DestinationCard`, `TravelButton` | valid destinations, cost/time, danger | Submit deterministic travel commands. |
| Map/world graph | Understand geography | `WorldMapDrawer`, `RoutePreview` | nodes, edges, current node, known/unknown | Can start as list/map hybrid. |
| Time/day/season | Track world progression | `TimeWeatherChip`, `CalendarPanel` | day, time of day, season | User requested day/night/time/season visibility. |
| Weather | Understand travel/combat modifiers | `WeatherBadge`, `WeatherDetailPopover` | weather, severity, forecast if known | Do not invent forecasts unless runtime provides them. |

### 10. Economy, shops, inns, and services

| Feature | Player need | UI components | Key states/data | Notes |
|---|---|---|---|---|
| Service discovery | Know available services at location | `ServicePanel`, `ServiceCard` | inn, shop, healer, travel, quest board | Contextual right rail. |
| Shop buy/sell | Purchase/sell items with prices | `ShopPanel`, `ShopItemRow`, `BuySellToggle`, `QuantityStepper` | price, stock, owned quantity, affordability | Must use deterministic prices and currency. |
| Inn/room rental | Rest/pay for room | `InnPanel`, `RoomOfferCard`, `RestButton` | price, room state, paid/unpaid, duration | Canonical example: 5 silver/night. |
| Transaction outcomes | See money/item deltas | `TransactionSummary`, `CurrencyDeltaToast` | cost, change, item added/removed | Should be clear and replayable. |
| Pay enforcement | Explain blocked service | `AffordabilityWarning`, `ServiceLockNotice` | insufficient funds, debt, not available | Must avoid UI-only service grants. |

### 11. Reports, autoplay, endurance, and evidence

| Feature | Player/operator need | UI components | Key states/data | Notes |
|---|---|---|---|---|
| Autoplay reports | Review campaign evidence | `AutoplayReportList`, `ReportCard`, `ReportViewer` | report id, path, kind, status | Current report list becomes richer. |
| 100-turn certification | Validate campaign coverage | `CertificationPanel`, `CoverageMatrix` | turn count, blockers, warnings, progress, loops | Operator/debug view, not default player path. |
| 1000-turn endurance | Watch long-run status | `EnduranceRunPanel`, `RunHealthMeter` | elapsed, p95, failures, artifact status | For later production testing. |
| Artifact bundles | Verify outputs are complete | `ArtifactBundlePanel`, `ZipMemberList`, `MissingArtifactNotice` | summary/transcript/report/checkpoint files | Evidence-first. |
| Performance metrics | Track blocking turn time | `PerformanceSparkline`, `LatencyBudgetBadge` | avg, p95, max, final drain | Helps tune sub-5s target. |

### 12. Provider, model, jobs, and local services

| Feature | Player/operator need | UI components | Key states/data | Notes |
|---|---|---|---|---|
| Provider/model status | Know whether narration can run | `ProviderStatusChip`, `ModelBadge`, `ProviderPopover` | provider, model, health, latency | Integrate with shared Providers/Models modules. |
| Job status | See active/failed turn jobs | `TurnStageTracker`, `JobDrawer`, `JobLogSnippet` | queued/running/completed/failed/cancelled | Current RPG jobs panel can move to drawer. |
| Inline/local execution | Avoid stuck queued jobs | `LocalFirstExecutionBadge`, `WorkerStatusNotice` | inline, worker-backed, unavailable | Should explain local-first behavior. |
| TTS/STT hooks | Optional voice play/input | `NarrationPlayButton`, `VoiceInputButton`, `VoiceStatusChip` | ready, recording, transcribing, speaking | Optional, not blocking turn loop. |
| Image hooks | Optional scene/portrait generation | `SceneImageButton`, `PortraitButton`, `ImageJobCard` | available, queued, completed, failed | Should use Image Generation module assets. |

### 13. Debug, diagnostics, and developer panels

| Feature | Operator need | UI components | Key states/data | Notes |
|---|---|---|---|---|
| Prompt visibility | Inspect LLM prompt/context | `PromptDebugDrawer`, `PromptBlock` | current action, persona, memory, state packet | Collapsed by default. |
| Grounding audit | Understand validation/fallback | `GroundingAuditPanel`, `FallbackBadge` | primary, safe fallback, deterministic fallback, soft audit | Should match validator taxonomy. |
| Runtime state | Inspect authoritative state | `RuntimeStateInspector`, `StateJsonViewer` | current state, state delta, digest | Debug-only. |
| Memory debug | Inspect writes/retrieval | `MemoryDebugPanel`, `MemoryTraceList` | memory writes, retrieved memory, backed IDs | Based on memory debug report payload. |
| CI/operator diagnostics | Troubleshoot runs | `DiagnosticsDrawer`, `ArtifactErrorPanel` | workflow, failure artifact, logs | Link to reports/jobs/assets modules. |

## Component priority for first mockups

### Required in the first design pass

1. `RpgGameHeader`
2. `SceneViewport`
3. `NarrativeFeed`
4. `TurnComposer`
5. `SuggestedActions`
6. `TurnStageTracker`
7. `PlayerHud`
8. `ObjectiveJournal`
9. `CombatPanel`
10. `ServicePanel`
11. `NpcRoster`
12. `SessionPicker`
13. `ReportsDrawer`
14. `DiagnosticsDrawer`

### Can be second-pass or drawer-only initially

1. `WorldMapDrawer`
2. `InventoryDrawer`
3. `PartyRosterDrawer`
4. `MemoryContinuityPanel`
5. `PromptDebugDrawer`
6. `ArtifactBundlePanel`
7. `PerformanceSparkline`
8. `SceneMediaRail`
9. `NarrationPlayButton`
10. `VoiceInputButton`

## Default layouts to generate for approval

Generate these design variants after this inventory is accepted:

1. **Player-first layout:** cinematic center narrative, left player HUD, right objective/NPC context, bottom command composer.
2. **Tactical layout:** combat-first right rail, initiative tracker, target cards, legal action grid.
3. **Town/service layout:** shop/inn/service panel, currency meter, inventory drawer, NPC/service provider context.
4. **Operator/debug layout:** report/certification/job/diagnostics panels for autoplay and replay evidence.
5. **Compact layout:** single-column responsive mobile or narrow desktop mode.

## Acceptance checklist for any proposed design

A proposed RPG UI design should not be approved unless it has visible answers for:

- What session am I in?
- Has the current turn been checkpointed?
- What is the current location and objective?
- What can I legally do next?
- Is the game waiting on simulation, narration, checkpointing, or provider work?
- What changed mechanically after the last command?
- If a command is blocked, why?
- If combat is active, whose turn is it and what actions are legal?
- If I am buying/resting/traveling, what does it cost and can I afford it?
- Where can I inspect reports, replay history, prompts, memory, and diagnostics without cluttering normal play?

## Open questions before visual design

- Should the default command composer always be free-form, or should it switch into mode-specific command builders for combat, shop, inn, dialogue, and travel?
- Should diagnostics be available to every user by default, or hidden behind an Advanced toggle?
- Should scene image generation be manual-only buttons, automatic per location, or disabled by default to preserve speed?
- Should TTS narration auto-play per turn or stay manual-only?
- Should memory continuity be shown as a player-facing trust feature, or mostly as a debug/report feature?
- How much of the autoplay/certification surface belongs inside RPG mode versus the global Reports module?
