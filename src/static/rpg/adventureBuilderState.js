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
            starting_npc_ids: []
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
        hasHistory: hasHistory
    };
})();