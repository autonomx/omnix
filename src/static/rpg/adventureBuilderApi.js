/**
 * Adventure Builder — API Client
 *
 * Thin wrappers around the creator endpoints.
 * Consumed by adventureBuilder.js.
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

    function regenerateSection(target, setup) {
        return fetch(BASE + '/regenerate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                target: target,
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

    return {
        getTemplates: getTemplates,
        buildTemplate: buildTemplate,
        validateSetup: validateSetup,
        previewSetup: previewSetup,
        regenerateSection: regenerateSection,
        startAdventure: startAdventure,
    };
})();
