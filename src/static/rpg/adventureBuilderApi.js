/**
 * Adventure Builder — API Client
 *
 * Thin wrappers around the creator endpoints.
 * Consumed by adventureBuilder.js.
 *
 * Phase 1.4 additions:
 * - regenerateSection supports mode, apply_token, apply_strategy
 * - regenerateItem for single-entity regeneration
 *
 * Phase 2.5 additions:
 * - inspectWorldSnapshot for snapshot wrapper
 * - compareWorld for graph diff between setups
 * - compareEntity for per-entity field diff
 */

/* global */

var AdventureBuilderApi = (function () {
    'use strict';

    var BASE = '/api/rpg/adventure';

    function _json(res) {
        if (!res.ok) throw new Error('API error at ' + res.url + ' (' + res.status + ')');
        return res.json();
    }

    function getTemplates() {
        return fetch(BASE + '/templates').then(_json);
    }

    function buildTemplate(templateName) {
        return fetch(BASE + '/template', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ template_name: templateName }),
        }).then(_json);
    }

    function validateSetup(payload) {
        return fetch(BASE + '/validate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        }).then(_json);
    }

    function previewSetup(payload) {
        return fetch(BASE + '/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        }).then(_json);
    }

    /**
     * Regenerate a full section of the adventure setup.
     *
     * @param {string} target         - Section target (e.g. 'npc_seeds')
     * @param {Object} setup          - Current setup payload
     * @param {Object} [opts]         - Optional overrides
     * @param {string} [opts.mode]    - 'preview' or 'apply' (default: 'apply')
     * @param {string} [opts.apply_token]    - Token from a previous preview
     * @param {string} [opts.apply_strategy] - 'replace', 'merge', or 'append'
     */
    function regenerateSection(target, setup, opts) {
        var body = {
            target: target,
            setup: setup
        };
        if (opts) {
            if (opts.mode) body.mode = opts.mode;
            if (opts.apply_token) body.apply_token = opts.apply_token;
            if (opts.apply_strategy) body.apply_strategy = opts.apply_strategy;
            if (opts.tone) body.tone = opts.tone;
            if (opts.constraints) body.constraints = opts.constraints;
        }
        return fetch(BASE + '/regenerate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        }).then(_json);
    }

    /**
     * Regenerate multiple entities within a section (Phase 1.5).
     *
     * @param {string} target   - Section target (e.g. 'npc_seeds')
     * @param {string[]} itemIds - Array of entity ids to regenerate
     * @param {Object} setup    - Current setup payload
     */
    function regenerateMultiple(target, itemIds, setup) {
        return fetch(BASE + '/regenerate-multiple', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                target: target,
                item_ids: itemIds,
                setup: setup
            }),
        }).then(_json);
    }

    /**
     * Regenerate a single entity within a section.
     *
     * @param {string} target  - Section target (e.g. 'npc_seeds')
     * @param {string} itemId  - Entity id to regenerate
     * @param {Object} setup   - Current setup payload
     */
    function regenerateItem(target, itemId, setup) {
        return fetch(BASE + '/regenerate-item', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                target: target,
                item_id: itemId,
                setup: setup
            }),
        }).then(_json);
    }

    function startAdventure(payload) {
        return fetch(BASE + '/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        }).then(_json);
    }

    /**
     * Fetch world graph, simulation summary, and entity inspector (Phase 2).
     *
     * @param {Object} setup - Current setup payload
     */
    function inspectWorld(setup) {
        return fetch(BASE + '/inspect-world', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ setup: setup }),
        }).then(_json);
    }

    /**
     * Build a full snapshot wrapper from a setup payload (Phase 2.5).
     *
     * @param {Object} setup - Current setup payload
     * @param {string} [label] - Optional snapshot label
     */
    function inspectWorldSnapshot(setup, label) {
        var body = { setup: setup };
        if (label) body.label = label;
        return fetch(BASE + '/inspect-world-snapshot', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        }).then(_json);
    }

    /**
     * Compare two setup payloads and return a graph diff (Phase 2.5).
     *
     * @param {Object} beforeSetup - Previous setup payload
     * @param {Object} afterSetup  - Current setup payload
     */
    function compareWorld(beforeSetup, afterSetup) {
        return fetch(BASE + '/compare-world', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ before_setup: beforeSetup, after_setup: afterSetup }),
        }).then(_json);
    }

    /**
     * Compare a specific entity between two setup payloads (Phase 2.5).
     *
     * @param {Object} beforeSetup - Previous setup payload
     * @param {Object} afterSetup  - Current setup payload
     * @param {string} entityId    - Entity id to compare
     */
    function compareEntity(beforeSetup, afterSetup, entityId) {
        return fetch(BASE + '/compare-entity', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ before_setup: beforeSetup, after_setup: afterSetup, entity_id: entityId }),
        }).then(_json);
    }

    /**
     * Advance the world simulation by one tick (Phase 3A).
     *
     * @param {Object} setup - Current setup payload
     */
    function simulateStep(setup) {
        return fetch(BASE + '/simulate-step', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ setup: setup }),
        }).then(_json);
    }

    /**
     * Get the current simulation state without advancing (Phase 3A).
     *
     * @param {Object} setup - Current setup payload
     */
    function getSimulationState(setup) {
        return fetch(BASE + '/simulation-state', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ setup: setup }),
        }).then(_json);
    }

    /**
     * Generate world details from setup and preferences (Phase E).
     *
     * @param {Object} setup       - Current setup payload
     * @param {Object} preferences - Generation preferences
     */
    function generateWorld(setup, preferences) {
        return fetch(BASE + '/generate-world', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ setup: setup, preferences: preferences }),
        }).then(_json);
    }

    /**
     * Regenerate a single section of the generated world (Phase E).
     *
     * @param {Object} setup       - Current setup payload
     * @param {string} section     - Section to regenerate (e.g. 'characters')
     * @param {Object} preferences - Generation preferences
     */
    function regenerateWorldSection(setup, section, preferences) {
        return fetch(BASE + '/regenerate-world-section', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ setup: setup, section: section, preferences: preferences }),
        }).then(_json);
    }

    /**
     * Regenerate a single entity in the generated world (Phase E).
     *
     * @param {Object} setup      - Current setup payload
     * @param {string} entityType - Entity type (e.g. 'characters')
     * @param {string} entityId   - Entity id to regenerate
     */
    function regenerateWorldEntity(setup, entityType, entityId) {
        return fetch(BASE + '/regenerate-world-entity', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ setup: setup, entity_type: entityType, entity_id: entityId }),
        }).then(_json);
    }

    /**
     * Apply generated package content into the setup (Phase E).
     *
     * @param {Object} setup     - Current setup payload
     * @param {Object} generated - Generated package to apply
     * @param {string[]} lockedIds - IDs of locked entities to preserve
     */
    function applyGeneratedPackage(setup, generated, lockedIds) {
        return fetch(BASE + '/apply-generated', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ setup: setup, generated: generated, locked_ids: lockedIds }),
        }).then(_json);
    }

    return {
        getTemplates: getTemplates,
        buildTemplate: buildTemplate,
        validateSetup: validateSetup,
        previewSetup: previewSetup,
        regenerateSection: regenerateSection,
        regenerateItem: regenerateItem,
        regenerateMultiple: regenerateMultiple,
        startAdventure: startAdventure,
        inspectWorld: inspectWorld,
        inspectWorldSnapshot: inspectWorldSnapshot,
        compareWorld: compareWorld,
        compareEntity: compareEntity,
        simulateStep: simulateStep,
        getSimulationState: getSimulationState,
        generateWorld: generateWorld,
        regenerateWorldSection: regenerateWorldSection,
        regenerateWorldEntity: regenerateWorldEntity,
        applyGeneratedPackage: applyGeneratedPackage,
    };
})();
