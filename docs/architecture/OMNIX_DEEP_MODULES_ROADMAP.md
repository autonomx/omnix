# Deep modules and simpler interfaces: roadmap

Started 2026-11-22 from a whole-app review: shallow modules, pass-through layers, knowledge copied between
callers, and helpers with more than one owner. Wave 1 (bugs and cheap drift) is done on branch
`deepen-modules-wave1`. Waves 2 and 3 are below, each item small enough for one session. Delete this file
when the last item lands.

Every item is now done or explained. What is left is not code to write on this branch:

- Moves that wait for a gate or a decision: the live-call speculative reply (the real-model gate), the play
  screen's remaining fields (a campaign document upgrade), the chat store split (a gateway that can be stopped
  and the real-model gate), and the prospective-gap phases (a v44).
- Two declined for cost against benefit, with the measurements recorded: the strategy pass hooks object and the
  two `AgentRunService` classes.

The two owner questions (wave 2, items 4 and 8) were answered on 2026-11-23 and are done. Delete this file once
those moves are either made or dropped.

## Wave 1: done

Each item names the one owner that callers now ask.

| Owner | Replaces | Notes |
| --- | --- | --- |
| `web/src/api/jobs.ts`: `isJobSettled`, `isJobActive`, `jobKeys` | status sets and `['platform','jobs', …]` keys written in each workspace | A waiting, retrying or paused job is not settled. |
| `web/src/shared/useJob.ts` | `useJobResult` (voice), VoiceWorkspace's playback poll, RpgWorkspace's submitted-turn poll | The RPG poll ran every 1.5 s forever after a turn finished. The voice playback poll stopped on a waiting or retrying job. |
| `web/src/api/errors.ts`: `GatewayCallError`, `isConflict` | status-code checks in callers | |
| `web/src/features/trading/format.ts` | four copies of `money`/`numeric`/`signed` | The Command Center showed a missing amount as `0.00 USD`. Initial risk no longer shows a `+`. |
| `app.apps.trading.canonical` | 27 copies of the digest, UTC and decimal helpers | The digest bytes are pinned by a test, because stored hashes depend on them. |
| `app.apps.trading.us_equity_calendar`: `is_trading_day`, session constants, `extended_close_time` | weekday-plus-holiday checks and clock literals in 43 modules | A guard test now rejects hard-coded session times. |
| `app.persistence.runtime.is_legacy_test_persistence` | 30 raw reads of `OMNIX_PERSISTENCE_MODE` | A guard test rejects new reads. |
| `events_by_types_between`, now required | `getattr` fallbacks in 7 strategy modules | |
| `TERMINAL_RUN_STATUSES` and the node and graph sets | status literals in agent runtime | |
| `provider_id_of` | per-module provider-id parsing | |
| `app.capabilities.approval_policy` | approval decisions made at each caller | The browser floor was tightened on purpose. |
| `app.providers.llm_admission` | per-provider admission checks | |
| `run_lifecycle.issue_start_spec` | spec assembly at each call site | Now `run_issuance.issue_run_spec` (wave 2, item 8). |

Deleted: `chat_speculative_tts`, `config/runtime_settings.py`, `config/models.py`, `load_config`.

`live_speech` (the opt-in `/v1/realtime` stub, 20 files, no callers) is deleted, along with the opt-in mechanism it
was the only user of. Its tombstone, `src/app/persistence/retired/live_speech/tombstone.py`, keeps a configuration
that still names `live-speech` starting. The owner decided on 2026-11-22 to leave the `regular_holidays` New Year's
Eve behavior as it is.

## Wave 2: interfaces that hide more

1. **Typed job handler.** Done; what stays on `handler` is explained below.
   - Done: `JobHandlerSpec.run` takes a `JobRun` (the validated input, the lease-bound store, the attempt and
     `final_attempt`). It returns a `JobResult` or raises a `JobFailure` (`RetryableJobError`, `PermanentJobError`).
     The registry then completes or fails the job. Another exception fails under the spec's `failure_code`, a final
     attempt is never retryable, and a lost lease (`JobClaimConflict`) publishes nothing.
   - Done: the worker's claim tells the observers "started". Handlers no longer mark a claimed job running.
     Nine handlers did: story, the five RPG jobs, dubbing, image and Voice Studio.
   - Done: the story, RPG and dubbing jobs are runs, and their copied `attempt < MAX_ATTEMPTS` checks are gone.
   - Kept on purpose: chat's live-call actions and research still call `mark_running`. They run on threads without
     a worker lease, so their job is not started by a claim.
   - Done: image and Voice Studio are runs. Their tests run a job through the feature's spec and the registry
     (`tests/support/image_jobs.py`, `tests/support/voice_jobs.py`). The image run still completes the job itself,
     because the avatar finisher reconciles a character's avatars only once its job reads as completed. Voice
     Studio settles a job itself only when it waits for an engine swap or a download was cancelled. A stored
     image payload that no longer validates is now refused before the run, as every run's is.
   - Done: audiobook's seven `run_*_once` loops share `leases.claimed_job`, which does the claim, the running
     mark and the heartbeat. The render loop passes its "a higher-priority TTS claim comes first" check as
     `wait`. Their bodies stay outside the registry: they pause jobs (a run has no paused outcome) and settle
     chapter state in the same transaction as the job.
   - Not done, by choice: `submit(job_type, payload)` taking module and resource class from the registry. A job's
     stored `module` is a display and filter name, not the feature that registered it. Voice Studio writes
     `voice`, `voice-cloning`, `models` and `stt`, image writes `image-generation` and `character-avatar`, and
     the web filters its lists by those names. A worker's store also has no registry, so the request's resource
     class is the one stored there. Deriving them would change stored rows.
   - Done: the strategy range backtest and the platform probe are runs. A cancel still fails the attempt, as it
     did when the exception reached the worker.
   - Still on `handler`, by choice:
     - Agent runtime's three jobs, which are authority-sensitive and settle under their own fencing.
     - Memory's three. `MemoryJobExecution` completes a job in the same transaction that writes the memories,
       and the same code also claims its own job after a turn, with no worker.
2. **Provider config.** Done.
   - `app.providers.model_route` is the one parser for `llm:<provider>:<model>` references: `model_name_of`,
     `model_provider_of`, and `ModelRoute.parse(provider_id, model_id)`. A route has `own_model` (a model that names
     another provider is dropped) and `model_led()` (a selected model moves the route to its provider). It is not
     called `ModelRef`, because agent runtime's contract already has a `ModelRef`.
   - It replaces 20 copies: chat's `_model_key` (imported privately by eight live-call modules), story, research,
     the semantic classifiers, planning review, RPG's route and World Forge, desktop vision, rich-UI levels, the agent
     gateway's `normalize_llm_*` and budget's `normalize_budget_provider_id`. Provider-id strippers now call
     `provider_id_of`.
   - Settings: `model_route.task_override_route(profile, key)` and `effective_model_route(...)` replace the
     override rows that Trading and Memory read by hand, and `route_model_name`. They parse what settings stores
     (`effective_defaults.task_override` and `effective_llm_route`, which still return the stored strings, because
     chat sessions and story payloads persist them). They live in providers because settings is a kernel package:
     a first version put them in settings, which made a settings-providers cycle (AL001, AL002, AL015).
   - Malformed text: an `llm:` value without a model (`llm:lmstudio`) is no model, so the provider's own choice
     serves. Two copies used to pass the text on as a model name.
   - Instead of `GenerationOptions`: only the reasoning level was read by hand from option dicts, three times with
     different precedence. `providers.base.configured_reasoning_effort(provider)` owns it now. Temperature and token
     limits are not copied, so a type for them would hide nothing.
3. **Agent run endings.** Done.
   - `agent_runtime.run_settlement` owns how a run ends: `fail_run` (failed, desired cancelled, error cut to
     2,000 characters), `complete_run` and `cancel_run` (with an optional error, for a cancel command that failed).
     Each writes through `repository.update_state`, so the lease-bound repository still adds the worker's lease and
     the revision check still refuses a stale writer.
   - 23 hand-written endings in nine modules now call it. Two of them stored an uncut error. A guard test rejects a
     terminal status literal in any other `update_state` call.
   - The other 22 `update_state` calls move a run between live states (starting, running, waiting, pause and resume
     requests) or mirror the runtime's status. They are not endings, so they stay as they are.
4. **Chat routing.** Done.
   - `chat.turn_routing.route_typed_turn(store, session, message, ...)` is how chat asks the agent runtime about a
     typed turn. It owns the turn deadline, the routing context the router may read (the store's
     `build_routing_context`), and dropping the unused prompt snapshot when the router settles the turn. Before,
     the three callers (the chat store, the stream boundary and the live agent store) each did this their own way.
   - `ROUTING_METADATA_KEYS`, `persist_routing_metadata` and `patch_user_message_metadata` replace the key list
     copied in `generation_jobs` and `prompt_store`, and three hand-written user-message patchers.
   - `LiveVoiceChatPort` goes from 16 members to 12. `route_reply` resolves and logs the call's route (it replaces
     `resolve_generation_route`, `resolve_stream_route` and `log_provider_route`). `generate_reply` and
     `stream_reply` pick the LM Studio or low-latency path inside live voice (they replace `is_lmstudio_provider` and
     three reply methods).
   - Decided by the owner 2026-11-23: a non-streamed chat turn (the generation job) routes on memory, history and
     summary, as a streamed turn does. `reuse_chat_context` is gone. The reply reuses the prompt the router built
     (`_pop_cached_prompt_context`), so the prompt is still built once, and `_generate_reply` discards a routed
     prompt that the reply did not use (agent mode, a failure). Tested in `test_routing_context.py`
     (`test_a_non_streamed_turn_routes_on_chat_context_and_builds_its_prompt_once`, and the agent-mode case).
   - Left: the speculative reply in `live_chat_speculation.py` still drives four live-voice helpers (thinking
     options, stream observer, text chunker, request gate). It belongs in live voice, but moving it is a live-call
     change that needs the real-model gate.
5. **Trading monitor switches.** Done.
   - `monitor_task.monitor_switch(name)` is a monitor's on/off switch. The monitor is on unless `name` turns it
     off. Under legacy test persistence (pytest) it stays off unless `<name>_IN_TESTS` turns it on.
   - 23 monitors used to copy that check, each with its own flag parser. They now bind their public
     `*_enabled` name to a switch, so the operations API and status payloads read the same thing as before.
   - The breadth and SEC fundamentals monitors ignored `_IN_TESTS`. They now accept it like the rest; it is off by
     default.
   - The configuration registry reads a `monitor_switch` call as both names. That added the breadth and fundamentals
     switches, which the scanner had missed.
   - Four monitors keep their own check, because it is not this switch:
     - the Alpaca status stream also needs its credentials;
     - the local-model monitor has no flag;
     - the Stoch sweep follows the strategy monitor;
     - the IBKR monitor reads its settings.
   - Registration itself was already one path (`TradingMonitorTask`, then `scheduled_task_spec`), so it needed no
     new `register_monitor`.
6. **RPG.** Done; the published-world golden did not move.
   - `foundation/safe_values.py` owns the text readers: `clean_text`, `stripped_text`, `string_text`,
     `folded_text`, `optional_text` and `collapsed_text`. They replace the private `_text` helpers copied in 43
     modules, and in the World Forge modules that imported them.
   - The edge builds a turn's `TurnRequest` once (`turn_pipeline.turn_request`). It names the kind from the
     action's `turn_kind` and gives an unnamed turn its own submission (`foreground_context.new_submission_id`).
     `TurnDelivery` says how the answer goes back: the delivery mode, the trace, and whether the narration follows
     the commit on the stream.
   - `turn_scope` holds the scopes every turn runs in: the authority snapshot, the narration draft (only for a
     client-named submission; never for Hermes), model-call counting and the pipeline trace. The HTTP route,
     Hermes and the after-commit narration each used to open these by hand.
   - `session/committed_narration.py` owns a committed turn's narration: `narrate_committed_turn` runs the six
     steps (replay hydration, present, delivery, consumer projection, certification, shadow) under the same span
     names, and `narrate_turn_after_commit` adds the session load and canonical patch for the stream path.
     Refusals are `NarrationRefused` with a status and detail; the edge alone turns them into HTTP.
   - `narrative_replay` moved from `edge` to `narration`, since it imports only narration. The narrative
     retirement audit (`legacy_retirement.py`) now reads `committed_narration.py` for the presenter and publisher
     calls, and still scans the gateway for retired tokens.
7. **Hermes.** Done.
   - `edge/hermes/approved_command.run_approved_command` is the one way an approved command reaches the game. In
     one call it checks that the flow is on (the feature flag and the payload's `enabled`), that the step is ready
     and the replay entry passed, submits on the turn path, and records the result in the ledger.
   - It replaces 11 modules (`approved_flow`, `pipeline_handoff`, `command_request`, `request_guard`,
     `ready_packet`, `submit_adapter`, `submit_bridge`, `pipeline_result`, `flow_audit`, `flow_error`,
     `flow_readout`). They passed one packet along a chain, and the guard re-checked what the packet had already
     checked. The route and the sequence executor both call `run_approved_command`.
   - The response shape the web reads (`flow.result.rpg_result`, `readout`, `ledger_entry`) is unchanged. One
     deliberate change: a turn the game refuses now reads out the game's error (for example
     `rpg_state_revision_conflict`) instead of always `rpg_result_not_ok`.
8. **`issue_run_spec` / `IssuedRunSpec`.** Done. Capabilities stay narrowed, and profiles stay ceilings.
   - `platform/agent_runtime/run_issuance.py` owns how a run's authority is issued:
     - `issue_run_spec` applies the process policy, then the default limits, then the authority and evidence checks;
     - `issue_child_spec` narrows a child to its parent (`derive_child_spec`), then runs the same checks under the
       run id its caller names (the reviewer's slot id);
     - `bind_run_workspace` binds the GitHub repository authority, then the workspace.
   - `IssuedRunSpec` (in `contracts.py`) is a `NewType` over `AgentRunSpec`. `repository.create_run` and
     `_persist_starting_run` take only an issued spec, so mypy refuses a start path that skips the issuer.
   - The paths that used to assemble this themselves now call the issuer: `start_with_context`, `submit_start`,
     the child start, the superseding revision (start and submit) and the reviewer attempt. The reviewer used to
     derive its child and then call the two checks by hand.
   - A durable spec read back for `prepare_workspace_job` counts as issued, since it was issued when its run was
     created. `start_prepared_run` still re-checks the durable spec, on purpose.
   - One logging change: `service.start.requested` now logs the caller's spec before it is issued, not after.
   - `test_run_issuance.py` covers the order of the steps, a refused spec, a child's narrowing, and a scan that
     no other module calls the issuing steps.
   - mypy also needed `is_approval_policy` to be a `TypeGuard`. `request_policy` now refuses an unknown policy on
     either side before `only_tightens` compares them.
   - Decided by the owner 2026-11-23: a child's external ceiling stays `external | optional_external`. It does
     not get the operator MCP tools that `profile_external_ceiling` adds for a top-level run, even when its parent
     holds them. `subagents.py` names the decision, and
     `test_child_does_not_inherit_operator_mcp_tools_its_parent_holds` pins it.
9. **Broker execution protocol.** Done. This item was the agent-runtime capability broker (`broker_api`), not a
   trading broker: the plan's earlier wording ("paper, IBKR and shadow brokers") misread the review. Trading has
   one order path already (`order_gateway.OrderGateway`), and IBKR is market data only.
   - `platform/agent_runtime/capability_call.CapabilityCall` is one broker call as durable state records it: the
     run, capability, execution key and task revision.
   - `open` scopes an evidence query's key to its task revision (`_revision_scoped_evidence_execution_key` before).
   - `settle` finishes the execution and, when the call holds one, its evidence query, with what the result used.
     The pair used to be written out four times (rejected approval, policy refusal, spent budget, result), with
     the `task_revision_id and is_evidence_capability` guard each time.
   - `park_for_approval` does the three parking steps; `ensure`, `claim` and `under_key` (an approval's recorded
     identity) round it out.
   - `execute_agent_capability` keeps the order of the steps. The helpers no longer return a `_CONTINUE`
     sentinel or take 8 to 11 positional arguments; a refused call returns through `_settled`. The broker is 162
     lines shorter.
   - `test_capability_call.py` covers settling with and without an evidence query, parking once, and a scan that
     only `capability_call` finishes an execution or an evidence query.
10. **Browser exemption.** Done.
    - `Capability.session_scoped` declares a capability that runs in a task-scoped session adapter. The 18
      `browser.*` capabilities set it. `run_approval_floor(run_policy, session_scoped=...)` reads it instead of
      the tool name (`_SESSION_SCOPED_TOOLS` is gone).
    - The broker computes the floor once from the capability it resolved. That floor is used both for the review
      and for the grant's `policy_floor`, so the two can no longer disagree.
    - The field is in the definition hash, since it bounds authority. Every definition hash changes once, so an
      approval still pending when this ships is refused as `capability_definition_changed` and must be asked
      again. That is the designed fail-closed behavior (PA-1.4).
    - A test checks that the governed browser alone declares itself session-scoped.
    - The `tool-catalog` characterization golden is re-recorded. Its diff is only the 59 definition hashes and
      the new `session_scoped` field (true for the 18 browser capabilities).
11. **Required `recovered_bars`.** Done.
    - Every caller asks the market service's shared recovery directly: the prospective-gap runtime (two sites),
      the operational formal outcome, evaluability, the candidate, protection, economic and stoch monitors, the
      shadow proxy, and the tape prefetch. The `getattr(..., "recovered_bars")` checks and their `bars()` branches
      are gone. A scan in `test_market_data_recovery.py` rejects a new probe for `recovered_bars` or
      `prefetch_recovered_bars`.
    - Two fallbacks were real runtime behavior and stay: the operational formal outcome retries `bars()` when
      recovery returns nothing, and evaluability falls through to configured history and IEX when recovery raises.
    - `_CurrentSessionMarketDataProxy` lost its post-open dead path, reached only by fakes: the
      `execution_indicator_bars` fallback and `_merge_current_session_bars`. Before the open it still cuts the
      configured history to today's causal prefix.
    - Bug fixed: the economic monitor asked for the 60-minute outcome with `as_of` at the horizon end. For an
      entry in mid-minute, the 60th bar ends after that, so the outcome never completed and was recorded as
      `data_incomplete` after the grace period. It now asks up to the next whole minute (`_minute_ceiling`).
    - `src/tests/trading/recovering_market_service.RecoveringMarketService` is the one test fake. It runs
      `reconcile_recovery` over the fake's own `bars()`, so tests see the live filtering. Seven test modules use it; the prospective-gap end-to-end fakes already
      had their own `recovered_bars`.
      A probe of every bars-only fake in the trading, persistence and characterization suites found no other
      fake that reaches recovery.
    - Two tests now state the live contract instead of the old proxy's:
      - `test_shadow_proxy_does_not_serve_an_iex_only_recovery_of_a_primary_failure`: an IEX-only recovery is
        partial-market and is refused for shadow OHLC and volume. The old test claimed the proxy served it.
      - The stoch RSI fixture now puts its 60 bars in the current session, before the clock. The shared recovery
        drops previous-session bars and future bars.
    - `session_window` was not part of this item. It came from the calendar finding and went with wave 1.
    - Follow-up, not from the review, done: `chat/generation_jobs.py` calls `get_session_window` directly. The
      file store (`chat/store.py`) has it too and returns the whole session, since it keeps whole sessions.

## Wave 3: larger splits

- **The chat session store.** Done for live-voice routing; the split is explained below. This is the backend stack, not a web store: `store.ChatSessionStore`,
  `prompt_store.ChatSessionStore`, `character_store`'s session mixin and in-memory store, and
  `persistence/chat_runtime`'s two PostgreSQL stores. Each layer adds behavior by overriding the one below.
  - Done: live-voice routing (`live_voice/llm/routing.begin_routed_user_message`) no longer reaches the store's
    private `_save_session`. Both stores' own `persist` write the route with the turn. When one did not, routing
    now patches it through `update_user_message_metadata`, which every chat store has, and still fails the turn
    if the store refuses. `test_a_route_the_persist_left_off_is_patched_through_the_store_or_the_turn_fails`
    covers both outcomes. Live voice may import only chat's contracts (AL001), so it calls the store's method
    rather than `turn_routing.patch_user_message_metadata`.
  - Not done, by choice: the review's split into a `ChatRepository` (reads and writes) and a `ChatTurnService`
    (begin, stream, complete).
    - Measured: the turn methods are overridden at three layers, and each override wraps the one below with
      `super()`. The character mixin (`character_store.py`) adds the scene and member turn around
      `begin_user_message`, `stream_provider_reply_chunks` and `complete_streamed_reply`. The PostgreSQL character
      store (`chat_runtime.PostgresCharacterChatSessionStore`) wraps `begin_user_message`,
      `complete_streamed_reply` and `append_assistant_message` in its transaction. The prompt store
      (`prompt_store.py`) owns the prompt and the provider stream underneath.
    - A `ChatTurnService` would need the same three layers as wrapped collaborators, so the inheritance moves
      rather than goes away. That buys little for its cost: 8 app modules and 27 test files call the turn
      methods on the store, on the typed path and on the live call.
    - A change on the live-call path needs the real-model gate and a gateway that can be stopped, and
      the PostgreSQL transaction has to keep enclosing the character layer's work, whatever shape replaces them.
    - Worth doing together with the next change that adds a store layer. The `super(ChatSessionStore, self)`
      calls in `prompt_store` are plain `super()` inside closures; they do not skip a layer.
- **Chart-panel state, one concern at a time.** Done.
  - The 9 hooks in `useTradingChartPanel*.ts` pass one growing bag between them. `useChartPanelState` returned
    about 118 values.
  - Done: the custom date range is `useChartCustomRange` (`useTradingChartPanelCustomRange.ts`). It owns the
    popover, its dates and error, its outside-press close, and open and apply. It reads eight named values, and
    the footer reads one `customRange` slice. The lifecycle effect now closes only the timezone menu.
    `useChartPanelState` lost nine values, and the range actions lost open and apply.
  - Tests: `useTradingChartPanelCustomRange.test.ts` covers opening, refusals, apply and the outside press. There
    was no coverage before. A real-browser test in `tests/e2e/trading-terminal.spec.ts` covers the refusal, the
    apply, an outside press and the timezone button.
  - Fixed while here: with an RSI pane open, its resize handle (z-index 100 in the panel's stacking context) sat
    over the popover's Apply button and took the click. The footer is now its own layer above the stage
    (`TradingChartTimeControls.css`), and the e2e test clicks Apply.
  - Done: replay, indicator panes and the context menu each take named inputs and return one slice.
    - `useChartReplayActions` reads 13 values and returns `replay` (stage click, select start, reset, step,
      play and exit). The footer and the stage click read it. The workflow no longer receives replay's actions.
    - `useChartIndicatorActions` reads 14 values and returns `panes` (fullscreen, minimize, reset view, close
      and resize). The header, legend, stage, context menu and the double-click workflow read it.
    - The context menu's actions left `useChartRangeActions` for `useChartContextMenu`
      (`useTradingChartPanelContextMenu.ts`). It reads 13 values and returns `contextMenuActions` (open, the
      stage's right click, copy and paste price, templates and the alert). The range actions keep the range,
      the right offset and the pointer.
    - Tests: `useTradingChartPanelReplay.test.ts` checks that a click while a replay runs does not restart it,
      that choosing a start sets the shared clock to the clicked bar's close, and stepping and exit.
      `useTradingChartPanelContextMenu.test.ts` checks the clamped position and pane indicator, the templates,
      and the alert. The footer and workflow tests read the slices.
- **The play screen reads what the rules decide from the campaign's view.** Done for the needs; the rest waits
  on a document upgrade.
  - `player_view.player_session_view` is the play screen's read model. Beside `here`, it now carries `needs`:
    hunger, thirst and fatigue from the survival record (`survival_persistence.current_survival`), each with
    its level and the most pressing one.
  - The thresholds are the survival rules' (`NEED_WARNING_AT` 60 and `NEED_CRITICAL_AT` 85, `need_level`).
    `rpgUiState.ts` no longer reads `simulation_state` or holds a number. It used to read an older campaign's
    `climate_survival` copy ahead of the record the turns change; the view reads the record.
  - The view still sends `simulation_state.survival`, because the intent eval and `rpg_autoplay` read it from
    the turn response.
  - Not done, by choice: the rest of the 25 fields. The hero's sheet, party, quests and the session summary's turn
    count and scene read the document through long fallback chains over older shapes.
    - The scene (`runtime_state.current_scene`) has five writers with different shapes. Its reader's fallbacks
      are what keeps those shapes readable.
    - The turn count's fallback, the larger of the count and the `recent_interactions` length, exists because the
      July campaigns' counts lag. All 52 live campaigns predate the engine.
    - Settling either shape means a campaign document upgrade: a new `CURRENT_SCHEMA_VERSION`, its upgrade in
      `session/upgrades/` and the §6 gate set. That is an owner decision under the RPG roadmap, not a read-model
      change. When it is made, each field moves to the view, and the engine's count is already
      `turn_count_of` / `TimeSection`.
    - The session routes return untyped payloads, so no contract is generated yet.
- **`StrategyRunHost` keeps its counters in one value and names its hooks.** Done; the hooks object is explained below.
  - The 23 pass counters are a `PassMetrics` value (`host.metrics`). The pass modules, the entry path and the
    runner add to it. The monitor's diagnostics keys and trade-log fields are unchanged.
  - The strategy operations status reads the strategy monitor's counters from `metrics`
    (`counters_attribute`). Its test now sets two of them, so a status that reads zeros fails.
  - `StrategyRunHost.PASS_HOOKS` names the five steps a pass calls back into its host.
    `test_strategy_runner_ownership` checks two things: `RunnerParityHost` overrides exactly those steps except
    candidate evaluation, and the pass calls each one.
  - Not done, by choice: a `ConfigPass` value and a `PassHooks` object.
    - The hooks do not share one argument set. `_reconcile_protections` runs before the pass builds its
      universe and takes the paper repository. `_proposals_evaluated` takes proposals. The other three take a
      universe. A shared value would carry a universe that the first hook runs without.
    - `RunnerParityHost` overriding four methods is already the one seam, and `PASS_HOOKS` plus
      `test_strategy_runner_ownership` pin it. A hooks object would move the same four functions without
      making the pass simpler.
    - The cost is about 35 test call and patch sites on the trading entry path, which carries order
      authority. That is too much churn for a rename.
  - The order gateway keeps authorization. Leases and scheduling stay with the monitor and the runner.
- **Agent-runtime forwarding modules.** Done for the facades, the lease and the dead forwarders; the service
  classes are explained below.
  - `review_orchestration` was a `__getattr__` facade over `review_orchestration_core`. They are now one module
    (`review_orchestration.py`). The public `launch_reviewer_children` still proves candidate-derived test
    execution first and then calls the private `_spawn_reviewer_children`. The core never launched reviewers
    itself, so every launch still passes through the proof step.
  - `pi_runtime` was a subclass layer over `pi_runtime_core` that changed four behaviors. Those behaviors now
    live in the one module (`pi_runtime.py`), unchanged:
    - `pi_rpc_argv` adds `omnix_plan` to `--tools` when coding quality is on, and appends the trusted `--skill`
      paths. The argv is the same, in the same order.
    - `normalize_pi_event` turns a provider failure reported in `message_end`/`turn_end` into `run.failed`. It
      then drops the repeated turn and the `agent_settled` that follow.
    - `_initial_prompt` adds the execution profile, repository guidance, skills digest, path roots and the
      engineering or review-mode text.
    - `command_with_context` sends a restarted-recovery `resume` as a steer of the fresh turn
      (`_dispatch_restarted_recovery`).
  - Prompt ids are unchanged, including the five `agent_runtime.pi_runtime_core.*` ids. The facade's
    `INITIAL_PROMPT_TEMPLATE` is now `REVIEW_MODE_PROMPT_TEMPLATE` in Python. Its id is unchanged.
  - Two one-shot scripts (`apply_pi_engineering_tools_once.py`, `prepare_pi_engineering_carrier_once.py`) still
    name `pi_runtime_core.py`. They are historical patches and are not run again.
  - The fold exposed a typed return that the facade's untyped wrapper had hidden:
    `reconcile_review_progress_in_repository` returns a 3-tuple or a 2-tuple. `quality_recovery` now checks the
    tuple's length before reading a launch action.
  - **One lease mechanism.** `_LeaseBoundRunRepository` was a `__getattr__` proxy that stamped one lease on each
    `update_state`. It is replaced by `PostgresAgentRunRepository.bound_to_lease(worker_id=, lease_token=)`.
    The repository now owns both ways a state change gets its lease: a bound lease, or the service's
    `lease_token_provider` for its own runs. A PostgreSQL test checks that a bound repository writes under its
    lease and that a stale token is refused.
  - Removed dead forwarders:
    - `AgentRunService.start_child` and `run_lifecycle.start_child`. Children start through
      `submit_child_start`.
    - The service's `_review_snapshot_id_from_child` and `_review_result_from_child`, and their
      `quality_state_machine` bodies (a "compatibility reader" nothing called).
    - The middle hop of `_launch_reviewer_children`.
  - **Not done, by choice: the two `AgentRunService` classes.**
    - Measured: `service_core.AgentRunService` has 48 one-line methods that forward to `run_lifecycle`,
      `run_steering`, `run_acceptance`, `run_workspace` and `run_supervision`. The `service.AgentRunService`
      subclass has 23 more that forward to `quality_state_machine` and `quality_acceptance`.
    - These methods are not dead. They are the protocol that the quality modules call back through
      (`service._quality_fail(...)` and so on). Test fakes implement them. For example, the coding-quality
      integration test's `_RecoveryService` asserts that `_launch_reviewer_children` is never called.
    - Folding them needs narrow collaborator protocols, so each `run_*`/`quality_*` module takes the few
      collaborators it uses instead of the whole service. It also means rewriting the fakes. That is a separate
      change.
    - Why not here: these methods are where acceptance, quality failure and recovery reach lease-bound state.
      Narrowing them changes which collaborator each authority-sensitive step can call, so it needs its own
      review against the run-lifecycle and recovery tests rather than riding along with a fold.
- **The prospective-gap prediction versions have one registry.** Done for what the versions share; the
  per-version phases are explained below.
  - `trading/prospective_prediction_versions.py` has `PredictionVersion` and the ordered `PREDICTION_VERSIONS`
    (v41, v42, v43). Each entry names its spec, its action policy and the versions it consumes (v43 consumes
    v42). Importing the module fails if a version comes before one it consumes.
  - `spec_records()` lists the five records a premarket freeze writes first. `freeze_premarket` loops over them
    instead of making five hand-written `append` calls.
  - `ProspectiveGapSessionLedger.latest_model(model, kind=, instrument_id=)` reads the latest record of a kind
    as its model. It replaces the runtime's five `_v4*_record`/`_v4*_watch` readers and the post-close inline
    reads. The repository's `latest_model` had no callers and is gone.
  - The six None-guarded "matched v42/v43 minus v3" deltas in `finalize_postclose` use one `_matched_delta`.
  - Frozen records are byte-identical. The 130 ledger appends the prospective-gap tests make were captured
    before and after the change, and the files hash the same. Research only: no order or authorization path
    changed.
  - Not done, by choice: a per-version phase interface for the freeze, confirmation and post-close blocks. The versions
    differ in more than their names: v42 is per-instrument; v43 needs the whole cohort's v42 forecasts for its
    regime, and it reads v42's action and authorization. A shared `freeze`/`confirm`/`score` protocol would have
    to carry the cohort and the upstream records. It is worth doing when a v44 is added, not before.
  - Tests: `src/tests/trading/test_prospective_prediction_versions.py`.
- **Genesis graph audits share one error, one registry entry and their traversal helpers.** Done.
  - `worlds/graph_audit.py` has `GraphAuditError` and `GraphAudit`. The error names its `code` and the issue
    `fields` its message lists. A field is an attribute path (`claim.subject_id`) with an optional format
    (`entity_ratio:.4f`). Three audits override `render`: cross-topic duplicates, entity contamination and
    profile dossiers.
  - 27 `*CompilationError` classes are now subclasses, each two to four lines. A snapshot of every message and
    `as_dict` before and after the change is byte-identical. The 12 errors that had no `as_dict` gain the shared
    one.
  - `_graph_audits()` and `extension_audits()` return `GraphAudit` entries. It is a `NamedTuple`, so the tests'
    tuple monkeypatches and `extension_audits()[0][2]` still work. The duplicated `ReportFn`/`RequireFn` aliases
    live in `graph_audit.py`.
  - Not changed: `DuplicateCanonCompilationError` lists duplicates rather than issues, and the report-based errors
    (`AuthorshipValidationError`, `ExactArtifactBindingError`, `WorldGenerationCertificationError`, and others)
    carry a whole report.
  - Done: the traversal helpers that read the same way. `worlds/topic_graph.py` has `mapping`, `rows`,
    `candidate`, `topic_entities` and `fingerprint`. 22 audit modules import them in place of 60 private copies
    (18 `_mapping`/`_map`, 19 `_rows`, 14 `_candidate`, 4 `_entities`, 5 `_fingerprint`). A copy was folded only
    when it returned the same value as the shared helper on a corpus of rows, mappings, strings, `None` and
    non-ASCII text. The private names stay as import aliases, so the audit bodies are unchanged.
  - Kept local, because they read differently and folding them would change an audit's reading:
    - the `_fingerprint` in `information_locality`, `local_markets` and `route_effects`, which hashes ASCII-escaped
      JSON (the shared one keeps non-ASCII text), so their digests differ;
    - two `_candidate`s: `strict_integrity`'s accepts a bare row only when it carries a collection id field, and
      `audit_stages`' returns `None` (not the row) when there is no candidate;
    - the `_rows` and `_entities` in the authoring, import and play-section modules (`dossier_quality_service`,
      `entity_authoring`, `legacy_bible_import`, `topic_entries`, `world_play_sections`, `published_*`,
      `lore_sections`, `runtime_seed`), and `naming_portfolio._entities`. They filter strings, accept a mapping as
      one row, or read other keys;
    - the six `_domains`, each of which reads its own audit's domain list.
  - The nine `forge/world_forge_*` vocabularies that the audits read stay where they are, because the forge's
    profile builders import them too.
  - Tests: `src/tests/rpg/worlds/test_graph_audit.py` checks the message, attribute paths and formats, the
    registry entries, and that every audit module's error is a `GraphAuditError` except the duplicate-canon gate.
- **The RPG turn counter has one reader.** Done.
  - `foundation/state/access.turn_count_of(document)` is the one reader, with one precedence: the sheet's
    `state.turn_count` first, then `manifest.turn_count`. That was already the "next turn" rule's precedence in six
    copies. The reducer still writes the count to all four places (`TurnCounted`), and the stored shape is unchanged.
  - `session/turn/resolution.py` now has the public `next_turn(document)` and `timed_changes(document, changes,
    minutes)`, which were the private `_counted` and `_timed`. The loadout and grid turns in `run.py` use
    `timed_changes` instead of re-deriving the ticks and the `TurnCounted`.
  - Moved to the reader: `resolvers`, `trade`, `travel`, `rules/ability_use` and `run.py` (the next turn);
    `run.py`'s card, knowledge and tick reads; `direction_call`, `encounters`, `exploration`, `inventions`, the game
    master job, `world/map_projection` (it read `current_turn` first) and `TimeSection` (it read the manifest
    only).
  - The published-world golden did **not** move. The roadmap expected it to, but the sources disagree only for an
    opening already under way (`published_launch` sets the sheet alone) before its first turn. After that turn the
    reducer has written all four places.
  - Left as they are:
    - the v13 upgrade in `session/campaign_state.py`, because a published upgrade's reading is frozen;
    - the replay adapter, the debug snapshot, the turn response's report field and the last-10 report, which read
      stored records and their older layouts;
    - the conversation engine's own `turn_count`, which counts a conversation's turns, not the campaign's.
  - Tests: `test_state_access.py` checks the precedence, `next_turn` and `timed_changes`. It also fails if a rule,
    `session/turn`, `world` or the game master reads `turn_count` or `current_turn` by key again.

## Pre-existing, found during wave 1 (not caused by it): all fixed

- From `5f137b4208` (camera share and FlashHead) and `269782b3a6`:
  - `architecture_metrics.py --check`: `camera_glance.py`'s two maps are capped at `_MAX_CHATS` (oldest chat goes
    first) and its four entries are in `process-local-state.json`; `LiveVideoLoadProgress.tsx` uses the shared
    `useNow` clock instead of its own `setInterval`; the shimmer's white is `--c-neutral-1000`.
  - Re-recorded for the new fields, with nothing else moving: the stored settings documents (`livePortraitEngine`),
    the `chat-live-sse-turn` golden (`camera_shared`), the Voice Studio model list (FlashHead and LivePortrait's
    idle-loop models) and the desktop live-portrait plan (the `live-portrait-flashhead` bundle).
  - The LivePortrait idle test's fake has `released`.
  - The chart footer's popovers sit above an open indicator pane's resize handle; the e2e test clicks Apply.
- `postgres_local_identity` (`src/tests/conftest.py`) opens a freshly migrated scratch database for writes once per
  worker, as the persistence suite's session fixture does, so chat tests no longer fail on a workspace foreign key.
  It changes only an untouched `legacy_preflight` database with no rows; a cutover test's state is kept.
- The endurance-script and phase-9 analysis tests find their files from the repository root, wherever pytest runs.
- Unused imports (F401) removed from the trading modules; nothing imported them through those modules.
- Explained, not changed:
  - PostgreSQL tests that truncate shared tables accept only `omnix_test` and `omnix_refactor_baseline` (and their
    `_gw<n>` copies). That guard is the point: it keeps them off any other database. It now fails with a message
    naming the allowed names instead of a bare `assert`.
  - Role separation: `MIGRATION_POLICY.md` says nothing enforces it at startup and that a deployment needing it
    configures the two roles; the dead `OMNIX_REQUIRE_ROLE_SEPARATION` setting was removed. Enforcing it would be
    an owner decision about deployments, not a code fix.
