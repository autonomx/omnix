/**
 * Adventure Builder — Renderer Helpers
 *
 * Owns:
 * - repeated shell markup
 * - validation summary rendering
 * - preview summary rendering
 * - small shared card/list helpers
 *
 * Step-specific form layout remains in adventureBuilder.js for Phase 1.2.
 */
var AdventureBuilderRenderer = (function () {
    'use strict';

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&')
            .replace(/</g, '<')
            .replace(/>/g, '>')
            .replace(/"/g, '"')
            .replace(/'/g, '&#39;');
    }

    function shell(step, bodyHtml) {
        return '' +
            '<div class="ab-shell">' +
                progress(step) +
                '<div class="ab-body">' + bodyHtml + '</div>' +
            '</div>';
    }

    function progress(step) {
        var items = [
            'Template & Basics',
            'Rules & Tone',
            'World Seeds',
            'Start State',
            'Review & Launch'
        ];
        return '' +
            '<div class="ab-progress">' +
                items.map(function (label, idx) {
                    var n = idx + 1;
                    var cls = 'ab-progress-step';
                    if (n === step) cls += ' active';
                    if (n < step) cls += ' complete';
                    return '' +
                        '<div class="' + cls + '" data-step="' + n + '">' +
                            '<div class="ab-progress-num">' + n + '</div>' +
                            '<div class="ab-progress-label">' + esc(label) + '</div>' +
                        '</div>';
                }).join('') +
            '</div>';
    }

    function section(title, innerHtml, extraClass) {
        return '' +
            '<section class="ab-section' + (extraClass ? ' ' + extraClass : '') + '">' +
                '<div class="ab-section-title">' + esc(title) + '</div>' +
                '<div class="ab-section-body">' + (innerHtml || '') + '</div>' +
            '</section>';
    }

    function issueList(validation) {
        if (!validation || !validation.issues || !validation.issues.length) return '';
        return '' +
            '<div class="ab-issues">' +
                validation.issues.map(function (issue) {
                    var sev = esc(issue.severity || 'warning');
                    return '' +
                        '<div class="ab-issue ab-issue-' + sev + '">' +
                            '<div class="ab-issue-head">' +
                                '<span class="ab-issue-severity">' + sev.toUpperCase() + '</span>' +
                                (issue.path ? '<span class="ab-issue-path">' + esc(issue.path) + '</span>' : '') +
                            '</div>' +
                            '<div class="ab-issue-message">' + esc(issue.message || '') + '</div>' +
                        '</div>';
                }).join('') +
            '</div>';
    }

    function previewSummary(preview, resolvedContext) {
        if (!preview && !resolvedContext) return '';
        var counts = (preview && preview.counts) || {};
        var locName = resolvedContext && resolvedContext.location_name ? resolvedContext.location_name : '';
        var npcNames = resolvedContext && resolvedContext.npc_names ? resolvedContext.npc_names : [];
        return '' +
            '<div class="ab-preview-summary">' +
                '<div class="ab-preview-grid">' +
                    metric('Factions', counts.factions || 0) +
                    metric('Locations', counts.locations || 0) +
                    metric('NPCs', counts.npcs || counts.npc_seeds || 0) +
                    metric('Warnings', (preview && preview.warnings ? preview.warnings.length : 0)) +
                '</div>' +
                '<div class="ab-preview-context">' +
                    '<div><strong>Opening location:</strong> ' + esc(locName || 'Auto-resolved at launch') + '</div>' +
                    '<div><strong>Opening NPCs:</strong> ' + esc((npcNames || []).join(', ') || 'Auto-resolved at launch') + '</div>' +
                '</div>' +
            '</div>';
    }

    function metric(label, value) {
        return '' +
            '<div class="ab-metric">' +
                '<div class="ab-metric-value">' + esc(value) + '</div>' +
                '<div class="ab-metric-label">' + esc(label) + '</div>' +
            '</div>';
    }

    function emptyState(message) {
        return '<div class="ab-empty">' + esc(message || 'Nothing here yet.') + '</div>';
    }

    return {
        esc: esc,
        shell: shell,
        progress: progress,
        section: section,
        issueList: issueList,
        previewSummary: previewSummary,
        metric: metric,
        emptyState: emptyState
    };
})();