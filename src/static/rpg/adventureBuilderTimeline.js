/**
 * Adventure Builder — Timeline & Diff Renderer (Phase 2.5)
 *
 * Responsibilities:
 * - Render snapshot timeline list
 * - Render graph diff summary
 * - Render entity history compare (before/after)
 * - Provide computeAndStoreGraphDiff for the main module
 *
 * Does NOT own state or API calls.
 */

/* global AdventureBuilderRenderer, AdventureBuilderWorldGraph */

var AdventureBuilderTimeline = (function () {
    'use strict';

    var _esc = AdventureBuilderRenderer.esc;

    // ─────────────────────────────────────────────────────────────────────
    // Graph diff computation (replaces inline version in WorldGraph)
    // ─────────────────────────────────────────────────────────────────────

    /**
     * Compute a local graph diff between two graph objects.
     * Returns { added: [...ids], removed: [...ids], changed: [...{id, fields}] }
     */
    function computeGraphDiff(previousGraph, nextGraph) {
        var prevNodes = {};
        var nextNodes = {};
        (previousGraph && previousGraph.nodes || []).forEach(function (n) { prevNodes[n.id] = n; });
        (nextGraph && nextGraph.nodes || []).forEach(function (n) { nextNodes[n.id] = n; });

        var added = [];
        var removed = [];
        var changed = [];

        Object.keys(nextNodes).forEach(function (id) {
            if (!prevNodes[id]) added.push(id);
        });
        Object.keys(prevNodes).forEach(function (id) {
            if (!nextNodes[id]) removed.push(id);
        });
        // Detect changed nodes
        Object.keys(nextNodes).forEach(function (id) {
            if (!prevNodes[id]) return;
            var b = prevNodes[id];
            var a = nextNodes[id];
            var fields = [];
            if (b.label !== a.label) fields.push('label');
            if (b.type !== a.type) fields.push('type');
            // Quick local diff — JSON.stringify is order-sensitive but acceptable
            // here since the authoritative diff comes from the Python backend
            // which normalizes and sorts meta properly.
            if (JSON.stringify(b.meta || {}) !== JSON.stringify(a.meta || {})) fields.push('meta');
            if (fields.length) changed.push({ id: id, fields: fields });
        });

        return { added: added, removed: removed, changed: changed };
    }

    /**
     * computeAndStoreGraphDiff — wrapper matching the old public API.
     */
    function computeAndStoreGraphDiff(previousGraph, nextGraph) {
        return computeGraphDiff(previousGraph, nextGraph);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Graph diff summary rendering
    // ─────────────────────────────────────────────────────────────────────

    /**
     * Render a compact diff summary bar.
     * @param {HTMLElement} container
     * @param {Object|null} diff  - Server diff response (nodes, edges, summary)
     */
    function renderGraphDiffSummary(container, diff) {
        if (!container) return;
        diff = diff || {};
        var added = (diff.nodes && diff.nodes.added || []).length;
        var removed = (diff.nodes && diff.nodes.removed || []).length;
        var changed = (diff.nodes && diff.nodes.changed || []).length;
        var edgeAdded = (diff.edges && diff.edges.added || []).length;
        var edgeRemoved = (diff.edges && diff.edges.removed || []).length;
        if (!added && !removed && !changed && !edgeAdded && !edgeRemoved) {
            container.innerHTML = '';
            return;
        }
        var html = '<div class="ab-wg-diff-summary">' +
            '<span class="ab-wg-diff-chip ab-diff-added">+' + _esc(added) + ' added</span>' +
            '<span class="ab-wg-diff-chip ab-diff-removed">-' + _esc(removed) + ' removed</span>' +
            '<span class="ab-wg-diff-chip ab-diff-changed">~' + _esc(changed) + ' changed</span>' +
            '<span class="ab-wg-diff-chip">+' + _esc(edgeAdded) + ' edges</span>' +
            '<span class="ab-wg-diff-chip">-' + _esc(edgeRemoved) + ' edges</span>' +
            '</div>';
        container.innerHTML = html;
    }

    /**
     * Render diff filter controls.
     * @param {HTMLElement} container
     * @param {Object} filters - { nodeType, changeType }
     * @param {Function} onChange - Callback with new filters
     */
    function renderDiffFilters(container, filters, onChange) {
        if (!container) return;
        filters = filters || { nodeType: 'all', changeType: 'all' };
        container.innerHTML = '' +
            '<div class="ab-diff-filters">' +
                '<label>Node Type ' +
                    '<select id="abDiffNodeType">' +
                        '<option value="all">All</option>' +
                        '<option value="npc">NPC</option>' +
                        '<option value="faction">Faction</option>' +
                        '<option value="location">Location</option>' +
                        '<option value="thread">Thread</option>' +
                        '<option value="opening">Opening</option>' +
                    '</select>' +
                '</label>' +
                '<label>Change Type ' +
                    '<select id="abDiffChangeType">' +
                        '<option value="all">All</option>' +
                        '<option value="added">Added</option>' +
                        '<option value="removed">Removed</option>' +
                        '<option value="changed">Changed</option>' +
                    '</select>' +
                '</label>' +
            '</div>';
        var nt = container.querySelector('#abDiffNodeType');
        var ct = container.querySelector('#abDiffChangeType');
        if (nt) nt.value = filters.nodeType || 'all';
        if (ct) ct.value = filters.changeType || 'all';
        if (nt) nt.addEventListener('change', function () {
            onChange({ nodeType: nt.value, changeType: ct ? ct.value : 'all' });
        });
        if (ct) ct.addEventListener('change', function () {
            onChange({ nodeType: nt ? nt.value : 'all', changeType: ct.value });
        });
    }

    // ─────────────────────────────────────────────────────────────────────
    // Snapshot timeline rendering
    // ─────────────────────────────────────────────────────────────────────

    function _relativeTime(ts) {
        var diff = (Date.now() / 1000) - ts;
        if (diff < 60) return 'just now';
        if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
        if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
        return Math.floor(diff / 86400) + 'd ago';
    }

    /**
     * Render the timeline tab content.
     *
     * @param {HTMLElement} container
     * @param {Array} snapshots
     * @param {Object} callbacks - { onView, onCompare, onCapture, onClear }
     */
    function renderTimeline(container, snapshots, callbacks) {
        if (!container) return;
        callbacks = callbacks || {};

        var html = '<div class="ab-timeline-header">' +
            '<h4>Snapshot Timeline</h4>' +
            '<div class="ab-inline-actions">' +
            '<button class="ab-btn ab-btn-secondary ab-btn-sm" id="abTimelineCapture">📸 Capture Snapshot</button>' +
            '<button class="ab-btn ab-btn-secondary ab-btn-sm" id="abTimelineClear">🗑️ Clear History</button>' +
            '</div>' +
            '</div>';

        if (!snapshots || !snapshots.length) {
            html += '<p class="ab-muted">No snapshots yet. Snapshots are captured automatically on significant changes, or use the button above.</p>';
            container.innerHTML = html;
            _bindTimelineButtons(container, callbacks);
            return;
        }

        html += '<div class="ab-timeline-list">';
        for (var i = snapshots.length - 1; i >= 0; i--) {
            var snap = snapshots[i];
            var summary = snap.summary || {};
            html += '<div class="ab-timeline-card" data-index="' + i + '">' +
                '<div class="ab-timeline-card-header">' +
                '<span class="ab-timeline-label">' + _esc(snap.label || 'Snapshot') + '</span>' +
                '<span class="ab-timeline-time">' + _relativeTime(snap.created_at || 0) + '</span>' +
                '</div>' +
                '<div class="ab-timeline-card-meta">' +
                '<span class="ab-timeline-stat">' + (summary.node_count || 0) + ' nodes</span>' +
                '<span class="ab-timeline-stat">' + (summary.edge_count || 0) + ' edges</span>' +
                '</div>' +
                '<div class="ab-timeline-card-actions">' +
                '<button class="ab-btn ab-btn-secondary ab-btn-xs ab-timeline-view" data-index="' + i + '">👁️ View</button>' +
                '<button class="ab-btn ab-btn-secondary ab-btn-xs ab-timeline-compare" data-index="' + i + '">⚖️ Compare to Current</button>' +
                '</div>' +
                '</div>';
        }
        html += '</div>';
        container.innerHTML = html;

        _bindTimelineButtons(container, callbacks);

        container.querySelectorAll('.ab-timeline-view').forEach(function (btn) {
            btn.addEventListener('click', function () {
                if (callbacks.onView) callbacks.onView(parseInt(btn.getAttribute('data-index'), 10));
            });
        });
        container.querySelectorAll('.ab-timeline-compare').forEach(function (btn) {
            btn.addEventListener('click', function () {
                if (callbacks.onCompare) callbacks.onCompare(parseInt(btn.getAttribute('data-index'), 10));
            });
        });
    }

    function _bindTimelineButtons(container, callbacks) {
        var captureBtn = container.querySelector('#abTimelineCapture');
        if (captureBtn && callbacks.onCapture) {
            captureBtn.addEventListener('click', callbacks.onCapture);
        }
        var clearBtn = container.querySelector('#abTimelineClear');
        if (clearBtn && callbacks.onClear) {
            clearBtn.addEventListener('click', callbacks.onClear);
        }
    }

    // ─────────────────────────────────────────────────────────────────────
    // Diff tab rendering
    // ─────────────────────────────────────────────────────────────────────

    /**
     * Render the full diff tab content from a server diff response.
     *
     * @param {HTMLElement} container
     * @param {Object|null} diff - Server diff response (nodes, edges, summary)
     * @param {Function|null} onEntityClick - Callback when user clicks a changed entity
     */
    function renderDiffTab(container, diff, onEntityClick) {
        if (!container) return;

        if (!diff) {
            container.innerHTML = '<p class="ab-muted">No diff data. Compare to a previous snapshot from the Timeline tab.</p>';
            return;
        }

        var html = '';

        // Summary chips
        if (diff.summary && diff.summary.length) {
            html += '<div class="ab-wg-diff-summary ab-diff-tab-summary">';
            diff.summary.forEach(function (s) {
                html += '<span class="ab-wg-diff-chip">' + _esc(s) + '</span>';
            });
            html += '</div>';
        }

        // Nodes section
        var nodes = diff.nodes || {};
        html += '<div class="ab-diff-section">';
        html += '<h4>Nodes</h4>';

        if (nodes.added && nodes.added.length) {
            html += '<div class="ab-diff-group">';
            html += '<h5 class="ab-diff-added">Added (' + nodes.added.length + ')</h5>';
            nodes.added.forEach(function (id) {
                html += '<div class="ab-diff-item ab-diff-added-item">' +
                    '<span class="ab-diff-badge ab-diff-badge-added">+</span> ' + _esc(id) +
                    '</div>';
            });
            html += '</div>';
        }

        if (nodes.removed && nodes.removed.length) {
            html += '<div class="ab-diff-group">';
            html += '<h5 class="ab-diff-removed">Removed (' + nodes.removed.length + ')</h5>';
            nodes.removed.forEach(function (id) {
                html += '<div class="ab-diff-item ab-diff-removed-item">' +
                    '<span class="ab-diff-badge ab-diff-badge-removed">\u2212</span> ' + _esc(id) +
                    '</div>';
            });
            html += '</div>';
        }

        if (nodes.changed && nodes.changed.length) {
            html += '<div class="ab-diff-group">';
            html += '<h5 class="ab-diff-changed">Changed (' + nodes.changed.length + ')</h5>';
            nodes.changed.forEach(function (c) {
                html += '<div class="ab-diff-item ab-diff-changed-item ab-diff-clickable" data-entity="' + _esc(c.id) + '">' +
                    '<span class="ab-diff-badge ab-diff-badge-changed">\u0394</span> ' + _esc(c.id) +
                    ' <span class="ab-diff-fields">(' + c.fields.join(', ') + ')</span>' +
                    '</div>';
            });
            html += '</div>';
        }

        if (!(nodes.added && nodes.added.length) && !(nodes.removed && nodes.removed.length) && !(nodes.changed && nodes.changed.length)) {
            html += '<p class="ab-muted">No node changes detected.</p>';
        }
        html += '</div>';

        // Edges section
        var edges = diff.edges || {};
        html += '<div class="ab-diff-section">';
        html += '<h4>Edges</h4>';

        if (edges.added && edges.added.length) {
            html += '<div class="ab-diff-group">';
            html += '<h5 class="ab-diff-added">Added (' + edges.added.length + ')</h5>';
            edges.added.forEach(function (e) {
                html += '<div class="ab-diff-item ab-diff-added-item">' +
                    '<span class="ab-diff-badge ab-diff-badge-added">+</span> ' +
                    _esc(e.source) + ' → ' + _esc(e.target) + ' <span class="ab-diff-edge-type">(' + _esc(e.type) + ')</span>' +
                    '</div>';
            });
            html += '</div>';
        }

        if (edges.removed && edges.removed.length) {
            html += '<div class="ab-diff-group">';
            html += '<h5 class="ab-diff-removed">Removed (' + edges.removed.length + ')</h5>';
            edges.removed.forEach(function (e) {
                html += '<div class="ab-diff-item ab-diff-removed-item">' +
                    '<span class="ab-diff-badge ab-diff-badge-removed">\u2212</span> ' +
                    _esc(e.source) + ' → ' + _esc(e.target) + ' <span class="ab-diff-edge-type">(' + _esc(e.type) + ')</span>' +
                    '</div>';
            });
            html += '</div>';
        }

        if (!(edges.added && edges.added.length) && !(edges.removed && edges.removed.length)) {
            html += '<p class="ab-muted">No edge changes detected.</p>';
        }
        html += '</div>';

        container.innerHTML = html;

        // Bind entity click handlers
        if (onEntityClick) {
            container.querySelectorAll('.ab-diff-clickable').forEach(function (el) {
                el.addEventListener('click', function () {
                    onEntityClick(el.getAttribute('data-entity'));
                });
            });
        }
    }

    // ─────────────────────────────────────────────────────────────────────
    // Entity history compare rendering
    // ─────────────────────────────────────────────────────────────────────

    /**
     * Render a before/after comparison for a single entity.
     *
     * @param {HTMLElement} container
     * @param {Object|null} entityDiff - Server compare-entity response diff section
     * @param {string} entityId
     */
    function renderEntityCompare(container, entityDiff, entityId) {
        if (!container) return;

        if (!entityDiff) {
            container.innerHTML = '<p class="ab-muted">No entity comparison data available.</p>';
            return;
        }

        var html = '<div class="ab-entity-compare">';
        html += '<h4>Entity: ' + _esc(entityId) + '</h4>';

        if (entityDiff.changed_fields && entityDiff.changed_fields.length) {
            html += '<div class="ab-entity-changed-fields">';
            html += '<strong>Changed fields:</strong> ';
            entityDiff.changed_fields.forEach(function (f) {
                html += '<span class="ab-diff-field-chip">' + _esc(f) + '</span>';
            });
            html += '</div>';
        }

        // Related changes
        if (entityDiff.related_added && entityDiff.related_added.length) {
            html += '<div class="ab-entity-related"><span class="ab-diff-badge ab-diff-badge-added">+</span> Related added: ' +
                entityDiff.related_added.map(function (id) { return _esc(id); }).join(', ') + '</div>';
        }
        if (entityDiff.related_removed && entityDiff.related_removed.length) {
            html += '<div class="ab-entity-related"><span class="ab-diff-badge ab-diff-badge-removed">\u2212</span> Related removed: ' +
                entityDiff.related_removed.map(function (id) { return _esc(id); }).join(', ') + '</div>';
        }

        // Before / After columns
        var before = entityDiff.before || {};
        var after = entityDiff.after || {};
        var allKeys = {};
        Object.keys(before).forEach(function (k) { allKeys[k] = true; });
        Object.keys(after).forEach(function (k) { allKeys[k] = true; });
        var keys = Object.keys(allKeys).sort();
        var changedSet = {};
        (entityDiff.changed_fields || []).forEach(function (f) { changedSet[f] = true; });

        html += '<div class="ab-entity-compare-grid">';
        html += '<div class="ab-entity-compare-col ab-entity-col-before"><h5>Before</h5></div>';
        html += '<div class="ab-entity-compare-col ab-entity-col-after"><h5>After</h5></div>';
        html += '</div>';

        keys.forEach(function (key) {
            var isChanged = changedSet[key];
            var cls = isChanged ? ' ab-entity-row-changed' : '';
            var bVal = _formatValue(before[key]);
            var aVal = _formatValue(after[key]);
            html += '<div class="ab-entity-compare-row' + cls + '">' +
                '<div class="ab-entity-row-label">' + _esc(key) + (isChanged ? ' <span class="ab-diff-badge ab-diff-badge-changed">\u0394</span>' : '') + '</div>' +
                '<div class="ab-entity-compare-grid">' +
                '<div class="ab-entity-compare-col ab-entity-col-before">' + bVal + '</div>' +
                '<div class="ab-entity-compare-col ab-entity-col-after">' + aVal + '</div>' +
                '</div>' +
                '</div>';
        });

        html += '</div>';
        container.innerHTML = html;
    }

    function _formatValue(val) {
        if (val === null || val === undefined) return '<span class="ab-muted">—</span>';
        if (typeof val === 'string') return _esc(val) || '<span class="ab-muted">(empty)</span>';
        if (Array.isArray(val)) {
            if (!val.length) return '<span class="ab-muted">(empty list)</span>';
            return val.map(function (v) {
                if (typeof v === 'object' && v !== null) return '<code>' + _esc(JSON.stringify(v)) + '</code>';
                return _esc(String(v));
            }).join(', ');
        }
        if (typeof val === 'object') return '<code>' + _esc(JSON.stringify(val)) + '</code>';
        return _esc(String(val));
    }

    // ─────────────────────────────────────────────────────────────────────
    // Public API
    // ─────────────────────────────────────────────────────────────────────

    return {
        computeGraphDiff: computeGraphDiff,
        computeAndStoreGraphDiff: computeAndStoreGraphDiff,
        renderGraphDiffSummary: renderGraphDiffSummary,
        renderDiffFilters: renderDiffFilters,
        renderTimeline: renderTimeline,
        renderDiffTab: renderDiffTab,
        renderEntityCompare: renderEntityCompare
    };
})();
