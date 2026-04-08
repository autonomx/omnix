/**
 * Adventure Builder — State Module
 *
 * Owns:
 * - draft persistence
 * - setup default shape
 * - top-level builder state container
 *
 * Does NOT own rendering or API calls.
 */
var AdventureBuilderState = (function () {
    'use strict';

    var STORAGE_KEY = 'omnix_rpg_adventure_builder_v1';

    function _defaultSetup() {
        return {
            setup_id: '',
            title: '',
            genre: '',
            setting: '',
            premise: '',
            hard_rules: [],
            soft_tone_rules: [],
            lore_constraints: [],
            factions: [],
            locations: [],
            npc_seeds: [],
            themes: [],
            forbidden_content: [],
            canon_notes: [],
            metadata: {},
            difficulty_style: null,
            mood: null,
            pacing: null,
            safety: null,
            content_balance: null,
            starting_location_id: null,
            starting_npc_ids: [],
            // Phase A — Player & Campaign
            player_role: '',
            player_archetype: '',
            player_background: '',
            campaign_objective: '',
            opening_hook: '',
            starter_conflict: '',
            core_world_laws: [],
            genre_rules: [],
            desired_content_mix: {
                combat: 0.25,
                exploration: 0.25,
                intrigue: 0.20,
                mystery: 0.15,
                survival: 0.05,
                romance: 0.05,
                humor: 0.05
            },
            starting_gear: [],
            starting_resources: {
                gold: 0,
                supplies: 0,
                ammo: 0,
                rations: 0
            },
            // Phase B — Opening
            opening: {
                location_id: '',
                scene_frame: '',
                present_npc_ids: [],
                immediate_problem: '',
                player_involvement_reason: '',
                first_choices: [],
                tension_level: 'medium',
                time_of_day: '',
                weather: ''
            },
            // Phase E — Generated World
            generated_package: {
                status: 'idle',
                seed_hint: '',
                generation_notes: '',
                characters: [],
                locations: [],
                factions: [],
                lore_entries: [],
                rumors: [],
                opening_patch: null,
                warnings: [],
                provenance: {
                    used_llm: false,
                    model: '',
                    generated_at: ''
                }
            },
            generation_preferences: {
                enabled: true,
                character_count: 5,
                location_count: 4,
                faction_count: 3,
                lore_count: 6,
                keep_existing_seeds: true,
                creativity_profile: 'balanced'
            },
            locked_generated_ids: []
        };
    }

    function _defaultState() {
        return {
            open: false,
            step: 1,
            loading: false,
            validating: false,
            previewing: false,
            regenerating: null,
            dirty: false,
            templates: [],
            setup: _defaultSetup(),
            validation: null,
            preview: null,
            lastError: null,
            /** Phase 1.4D — Undo stack for regeneration rollbacks */
            history: [],
            regen: {
                target: null,
                preview: null,
                modalOpen: false,
                loading: false
            },
            /** Phase 1.5 — Multi-select, constraints, tone */
            selection: {
                items: [],
                activeTarget: null
            },
            constraints: {},
            tone: "neutral",
            /** Phase 2 — World inspection (graph, simulation, inspector) */
            worldInspection: {
                loading: false,
                graph: null,
                simulation: null,
                inspector: null,
                selectedNodeId: null,
                hoveredNodeId: null,
                activeTab: 'summary',
                previousGraph: null,
                graphDiff: null,
                layoutMode: 'auto',
                /** Phase 2.5 — Snapshot timeline + compare */
                snapshots: [],
                selectedSnapshotIndex: null,
                compareMode: false,
                entityHistory: null,
                diffFilters: {
                    nodeType: 'all',
                    changeType: 'all'
                },
                /** Phase 3A — Simulation runtime */
                simulationRuntime: {
                    state: null,
                    lastDiff: null,
                    lastSummary: [],
                    stepping: false,
                    lastEvents: [],
                    lastConsequences: [],
                    lastEffectDiff: null,
                    /** Phase 3D — Incidents & Policy Reactions */
                    lastIncidentDiff: null,
                    lastReactionDiff: null,
                    /** Phase 4 — Scenes / Encounters */
                    lastScenes: []
                }
            }
        };
    }

    function _clone(obj) {
        return JSON.parse(JSON.stringify(obj));
    }

    function _safeParse(raw, fallback) {
        try {
            return JSON.parse(raw);
        } catch (err) {
            return fallback;
        }
    }

    function loadDraft() {
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return _defaultSetup();
            var parsed = _safeParse(raw, _defaultSetup());
            if (!parsed || typeof parsed !== 'object') return _defaultSetup();
            return Object.assign(_defaultSetup(), parsed);
        } catch (err) {
            console.warn('[AdventureBuilderState] Failed to load draft', err);
            return _defaultSetup();
        }
    }

    function saveDraft(setup) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(setup || _defaultSetup()));
        } catch (err) {
            console.warn('[AdventureBuilderState] Failed to save draft', err);
        }
    }

    function clearDraft() {
        try {
            localStorage.removeItem(STORAGE_KEY);
        } catch (err) {
            console.warn('[AdventureBuilderState] Failed to clear draft', err);
        }
    }

    function buildInitialState() {
        var state = _defaultState();
        state.setup = loadDraft();
        return state;
    }

    function resetState(state) {
        var next = _defaultState();
        next.setup = _defaultSetup();
        Object.keys(state).forEach(function (k) { delete state[k]; });
        Object.assign(state, next);
        saveDraft(state.setup);
        return state;
    }

    function hydrateFromTemplate(state, templatePayload, templateName) {
        var nextSetup = Object.assign(_defaultSetup(), _clone(templatePayload || {}));
        if (!nextSetup.setup_id) {
            nextSetup.setup_id = 'adventure_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 6);
        }
        if (!nextSetup.metadata) nextSetup.metadata = {};
        if (templateName) nextSetup.metadata.template_name = templateName;
        state.setup = nextSetup;
        state.dirty = true;
        saveDraft(state.setup);
        return state.setup;
    }

    function markDirty(state) {
        state.dirty = true;
        saveDraft(state.setup);
    }

    /** Phase 1.4D — Push a snapshot onto the undo stack before applying a regeneration. */
    var MAX_HISTORY = 10;

    function pushHistory(state, entry) {
        if (!state.history) state.history = [];
        state.history.push(_clone(entry));
        if (state.history.length > MAX_HISTORY) {
            state.history = state.history.slice(-MAX_HISTORY);
        }
    }

    function popHistory(state) {
        if (!state.history || !state.history.length) return null;
        return state.history.pop();
    }

    function hasHistory(state) {
        return !!(state.history && state.history.length);
    }

    function normalizeDesiredContentMix(mix) {
        var out = {};
        var keys = Object.keys(mix || {});
        var sum = 0;
        keys.forEach(function (k) {
            var v = parseFloat(mix[k]) || 0;
            v = Math.max(0, Math.min(1, v));
            out[k] = v;
            sum += v;
        });
        if (sum > 0) {
            keys.forEach(function (k) { out[k] = out[k] / sum; });
        }
        return out;
    }

    function normalizeStartingResources(resources) {
        var out = {};
        Object.keys(resources || {}).forEach(function (k) {
            var v = parseInt(resources[k], 10) || 0;
            out[k] = Math.max(0, Math.min(999999, v));
        });
        return out;
    }

    function normalizeStringList(list, maxItems, maxLen) {
        if (!Array.isArray(list)) return [];
        var result = [];
        for (var i = 0; i < list.length && result.length < (maxItems || 50); i++) {
            var s = (typeof list[i] === 'string' ? list[i] : '').trim();
            if (!s) continue;
            if (maxLen && s.length > maxLen) s = s.substring(0, maxLen);
            result.push(s);
        }
        return result;
    }

    function normalizeGearItems(list) {
        if (!Array.isArray(list)) return [];
        var result = [];
        for (var i = 0; i < list.length && result.length < 16; i++) {
            var item = list[i];
            if (typeof item === 'string') {
                var t = item.trim();
                if (t) result.push({ name: t, description: '' });
            } else if (item && typeof item === 'object') {
                var name = (item.name || '').trim();
                if (!name) continue;
                result.push({
                    name: name.substring(0, 100),
                    description: (item.description || '').trim().substring(0, 300)
                });
            }
        }
        return result;
    }

    return {
        STORAGE_KEY: STORAGE_KEY,
        defaultSetup: _defaultSetup,
        defaultState: _defaultState,
        buildInitialState: buildInitialState,
        loadDraft: loadDraft,
        saveDraft: saveDraft,
        clearDraft: clearDraft,
        resetState: resetState,
        hydrateFromTemplate: hydrateFromTemplate,
        markDirty: markDirty,
        pushHistory: pushHistory,
        popHistory: popHistory,
        hasHistory: hasHistory,
        normalizeDesiredContentMix: normalizeDesiredContentMix,
        normalizeStartingResources: normalizeStartingResources,
        normalizeStringList: normalizeStringList,
        normalizeGearItems: normalizeGearItems
    };
})();