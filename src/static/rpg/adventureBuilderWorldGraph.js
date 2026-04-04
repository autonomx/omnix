/**
 * Adventure Builder — World Graph, Simulation & Inspector Renderer (Phase 2)
 *
 * Responsibilities:
 * - Render SVG-based force-lite graph of nodes and edges
 * - Render simulation summary panel
 * - Render per-entity inspector panel
 * - Handle node click → inspector population
 * - Filter / search / highlight
 */
/* global AdventureBuilderRenderer */

var AdventureBuilderWorldGraph = (function () {
    'use strict';

    var _esc = AdventureBuilderRenderer.esc;

    // ─────────────────────────────────────────────────────────────────────
    // Node type config — colors and icons
    // ─────────────────────────────────────────────────────────────────────

    var NODE_CONFIG = {
        faction:  { color: '#e74c3c', icon: '⚔️', label: 'Faction' },
        npc:      { color: '#3498db', icon: '👤', label: 'NPC' },
        location: { color: '#2ecc71', icon: '📍', label: 'Location' },
        thread:   { color: '#f39c12', icon: '🔗', label: 'Thread' },
        opening:  { color: '#9b59b6', icon: '🎬', label: 'Opening' }
    };

    var EDGE_CONFIG = {
        member_of:     { color: '#e74c3c', label: 'member of', dash: '' },
        located_in:    { color: '#2ecc71', label: 'located in', dash: '' },
        involves:      { color: '#f39c12', label: 'involves', dash: '5,3' },
        pressures:     { color: '#e67e22', label: 'pressures', dash: '8,4' },
        connected_to:  { color: '#9b59b6', label: 'connected', dash: '3,3' },
        starts_at:     { color: '#9b59b6', label: 'starts at', dash: '' }
    };

    // ─────────────────────────────────────────────────────────────────────
    // Simple force-directed layout (no external deps)
    // ─────────────────────────────────────────────────────────────────────

    function _layoutGraph(nodes, edges, width, height) {
        if (!nodes.length) return [];

        // Initialize positions randomly
        var positions = {};
        var padding = 60;
        nodes.forEach(function (n) {
            positions[n.id] = {
                x: padding + Math.random() * (width - 2 * padding),
                y: padding + Math.random() * (height - 2 * padding),
                vx: 0,
                vy: 0
            };
        });

        // Build edge map for attraction
        var edgeMap = {};
        edges.forEach(function (e) {
            if (!edgeMap[e.source]) edgeMap[e.source] = [];
            if (!edgeMap[e.target]) edgeMap[e.target] = [];
            edgeMap[e.source].push(e.target);
            edgeMap[e.target].push(e.source);
        });

        var iterations = 80;
        var repulsion = 3000;
        var attraction = 0.005;
        var damping = 0.85;
        var centerPull = 0.01;
        var cx = width / 2;
        var cy = height / 2;

        for (var iter = 0; iter < iterations; iter++) {
            // Repulsion between all pairs
            var ids = Object.keys(positions);
            for (var i = 0; i < ids.length; i++) {
                for (var j = i + 1; j < ids.length; j++) {
                    var a = positions[ids[i]];
                    var b = positions[ids[j]];
                    var dx = a.x - b.x;
                    var dy = a.y - b.y;
                    var dist = Math.sqrt(dx * dx + dy * dy) || 1;
                    var force = repulsion / (dist * dist);
                    var fx = (dx / dist) * force;
                    var fy = (dy / dist) * force;
                    a.vx += fx;
                    a.vy += fy;
                    b.vx -= fx;
                    b.vy -= fy;
                }
            }

            // Attraction along edges
            edges.forEach(function (e) {
                var s = positions[e.source];
                var t = positions[e.target];
                if (!s || !t) return;
                var dx = t.x - s.x;
                var dy = t.y - s.y;
                var dist = Math.sqrt(dx * dx + dy * dy) || 1;
                var force = attraction * dist;
                s.vx += (dx / dist) * force;
                s.vy += (dy / dist) * force;
                t.vx -= (dx / dist) * force;
                t.vy -= (dy / dist) * force;
            });

            // Center pull and update
            ids.forEach(function (id) {
                var p = positions[id];
                p.vx += (cx - p.x) * centerPull;
                p.vy += (cy - p.y) * centerPull;
                p.vx *= damping;
                p.vy *= damping;
                p.x += p.vx;
                p.y += p.vy;
                // Clamp
                p.x = Math.max(padding, Math.min(width - padding, p.x));
                p.y = Math.max(padding, Math.min(height - padding, p.y));
            });
        }

        return nodes.map(function (n) {
            return {
                id: n.id,
                type: n.type,
                label: n.label,
                meta: n.meta,
                x: positions[n.id].x,
                y: positions[n.id].y
            };
        });
    }

    // ─────────────────────────────────────────────────────────────────────
    // SVG Graph rendering
    // ─────────────────────────────────────────────────────────────────────

    function renderGraph(container, graphData, options) {
        options = options || {};
        var onNodeClick = options.onNodeClick || function () {};
        var selectedNodeId = options.selectedNodeId || null;
        var filterType = options.filterType || 'all';
        var searchQuery = (options.searchQuery || '').toLowerCase();

        var nodes = (graphData && graphData.nodes) || [];
        var edges = (graphData && graphData.edges) || [];

        // Filter nodes
        var visibleNodeIds = {};
        var filteredNodes = nodes.filter(function (n) {
            if (filterType !== 'all' && n.type !== filterType) return false;
            if (searchQuery && n.label.toLowerCase().indexOf(searchQuery) === -1) return false;
            visibleNodeIds[n.id] = true;
            return true;
        });

        // Filter edges to only show those between visible nodes
        var filteredEdges = edges.filter(function (e) {
            return visibleNodeIds[e.source] && visibleNodeIds[e.target];
        });

        if (!filteredNodes.length) {
            container.innerHTML = '<div class="ab-wg-empty">No nodes to display</div>';
            return;
        }

        var width = container.clientWidth || 600;
        var height = Math.max(400, container.clientHeight || 400);

        var laid = _layoutGraph(filteredNodes, filteredEdges, width, height);
        var posMap = {};
        laid.forEach(function (n) { posMap[n.id] = n; });

        // Highlight: when a node is selected, find connected nodes
        var highlightIds = {};
        if (selectedNodeId && posMap[selectedNodeId]) {
            highlightIds[selectedNodeId] = true;
            filteredEdges.forEach(function (e) {
                if (e.source === selectedNodeId) highlightIds[e.target] = true;
                if (e.target === selectedNodeId) highlightIds[e.source] = true;
            });
        }

        var svgParts = [];
        svgParts.push('<svg class="ab-wg-svg" width="' + width + '" height="' + height + '" viewBox="0 0 ' + width + ' ' + height + '">');

        // Defs for arrow markers
        svgParts.push('<defs>');
        Object.keys(EDGE_CONFIG).forEach(function (etype) {
            var ec = EDGE_CONFIG[etype];
            svgParts.push(
                '<marker id="arrow-' + etype + '" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="8" markerHeight="6" orient="auto-start-reverse">' +
                '<path d="M0,0 L10,3 L0,6 z" fill="' + ec.color + '" opacity="0.6" />' +
                '</marker>'
            );
        });
        svgParts.push('</defs>');

        // Edges
        filteredEdges.forEach(function (e) {
            var s = posMap[e.source];
            var t = posMap[e.target];
            if (!s || !t) return;
            var ec = EDGE_CONFIG[e.type] || { color: '#666', dash: '' };
            var dimmed = selectedNodeId && !highlightIds[e.source] && !highlightIds[e.target];
            var opacity = dimmed ? 0.15 : 0.5;
            var dashAttr = ec.dash ? ' stroke-dasharray="' + ec.dash + '"' : '';
            svgParts.push(
                '<line x1="' + s.x + '" y1="' + s.y + '" x2="' + t.x + '" y2="' + t.y + '" ' +
                'stroke="' + ec.color + '" stroke-width="1.5" opacity="' + opacity + '"' +
                dashAttr + ' marker-end="url(#arrow-' + e.type + ')" />'
            );
        });

        // Nodes
        laid.forEach(function (n) {
            var nc = NODE_CONFIG[n.type] || { color: '#666', icon: '●' };
            var isSelected = n.id === selectedNodeId;
            var dimmed = selectedNodeId && !highlightIds[n.id];
            var opacity = dimmed ? 0.3 : 1;
            var r = isSelected ? 22 : 18;
            var strokeWidth = isSelected ? 3 : 1.5;
            var stroke = isSelected ? '#fff' : 'rgba(255,255,255,0.3)';

            svgParts.push(
                '<g class="ab-wg-node" data-id="' + _esc(n.id) + '" style="cursor:pointer;opacity:' + opacity + '">' +
                '<circle cx="' + n.x + '" cy="' + n.y + '" r="' + r + '" fill="' + nc.color + '" stroke="' + stroke + '" stroke-width="' + strokeWidth + '" />' +
                '<text x="' + n.x + '" y="' + (n.y + 4) + '" text-anchor="middle" fill="#fff" font-size="12">' + nc.icon + '</text>' +
                '<text x="' + n.x + '" y="' + (n.y + r + 14) + '" text-anchor="middle" fill="currentColor" font-size="10" class="ab-wg-label">' + _esc(n.label) + '</text>' +
                '</g>'
            );
        });

        svgParts.push('</svg>');
        container.innerHTML = svgParts.join('');

        // Attach click listeners
        container.querySelectorAll('.ab-wg-node').forEach(function (g) {
            g.addEventListener('click', function (ev) {
                ev.stopPropagation();
                onNodeClick(g.getAttribute('data-id'));
            });
        });

        // Click on empty space deselects
        var svg = container.querySelector('.ab-wg-svg');
        if (svg) {
            svg.addEventListener('click', function () {
                onNodeClick(null);
            });
        }
    }

    // ─────────────────────────────────────────────────────────────────────
    // Graph filter bar
    // ─────────────────────────────────────────────────────────────────────

    function renderGraphControls(container, options) {
        options = options || {};
        var filterType = options.filterType || 'all';
        var searchQuery = options.searchQuery || '';
        var onFilterChange = options.onFilterChange || function () {};
        var onSearchChange = options.onSearchChange || function () {};

        var types = ['all', 'faction', 'npc', 'location', 'thread', 'opening'];
        var html = '<div class="ab-wg-controls">';
        html += '<div class="ab-wg-filter-row">';
        types.forEach(function (t) {
            var nc = NODE_CONFIG[t] || { icon: '🌐', label: 'All', color: '#999' };
            var active = t === filterType ? ' ab-wg-filter-active' : '';
            var label = t === 'all' ? '🌐 All' : nc.icon + ' ' + nc.label;
            html += '<button class="ab-wg-filter-btn' + active + '" data-filter="' + t + '">' + label + '</button>';
        });
        html += '</div>';
        html += '<input type="text" class="ab-wg-search" placeholder="Search nodes\u2026" aria-label="Search graph nodes" value="' + _esc(searchQuery) + '" />';
        html += '</div>';
        container.innerHTML = html;

        container.querySelectorAll('.ab-wg-filter-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                onFilterChange(btn.getAttribute('data-filter'));
            });
        });

        var searchInput = container.querySelector('.ab-wg-search');
        if (searchInput) {
            searchInput.addEventListener('input', function () {
                onSearchChange(searchInput.value);
            });
        }
    }

    // ─────────────────────────────────────────────────────────────────────
    // Legend
    // ─────────────────────────────────────────────────────────────────────

    function renderLegend(container) {
        var html = '<div class="ab-wg-legend">';
        Object.keys(NODE_CONFIG).forEach(function (type) {
            var nc = NODE_CONFIG[type];
            html += '<span class="ab-wg-legend-item">' +
                '<span class="ab-wg-legend-dot" style="background:' + nc.color + '"></span>' +
                nc.icon + ' ' + nc.label +
                '</span>';
        });
        html += '</div>';
        container.innerHTML = html;
    }

    // ─────────────────────────────────────────────────────────────────────
    // Inspector panel
    // ─────────────────────────────────────────────────────────────────────

    function renderInspector(container, nodeId, inspectorData) {
        if (!nodeId || !inspectorData || !inspectorData.entities) {
            container.innerHTML = '<div class="ab-wg-inspector-empty">Click a node to inspect it</div>';
            return;
        }

        var entity = inspectorData.entities[nodeId];
        if (!entity) {
            container.innerHTML = '<div class="ab-wg-inspector-empty">No data for: ' + _esc(nodeId) + '</div>';
            return;
        }

        var nc = NODE_CONFIG[entity.type] || { icon: '●', label: 'Entity', color: '#666' };
        var html = '<div class="ab-wg-inspector">';

        // Header
        html += '<div class="ab-wg-inspector-header" style="border-left: 4px solid ' + nc.color + '">';
        html += '<span class="ab-wg-inspector-icon">' + nc.icon + '</span>';
        html += '<span class="ab-wg-inspector-name">' + _esc(entity.name || entity.title || nodeId) + '</span>';
        html += '<span class="ab-wg-inspector-type">' + _esc(nc.label) + '</span>';
        html += '</div>';

        // Type-specific content
        if (entity.type === 'npc') {
            html += _inspectorNpc(entity);
        } else if (entity.type === 'faction') {
            html += _inspectorFaction(entity);
        } else if (entity.type === 'location') {
            html += _inspectorLocation(entity);
        } else if (entity.type === 'thread') {
            html += _inspectorThread(entity);
        }

        html += '</div>';
        container.innerHTML = html;
    }

    function _inspectorField(label, value) {
        if (!value && value !== 0) return '';
        return '<div class="ab-wg-inspector-field"><span class="ab-wg-field-label">' +
            _esc(label) + ':</span> <span class="ab-wg-field-value">' + _esc(value) + '</span></div>';
    }

    function _itemId(item) {
        return item.npc_id || item.thread_id || item.faction_id || item.location_id || '';
    }

    function _inspectorList(label, items) {
        if (!items || !items.length) return '';
        var html = '<div class="ab-wg-inspector-list"><span class="ab-wg-field-label">' + _esc(label) + ':</span><ul>';
        items.forEach(function (item) {
            if (typeof item === 'string') {
                html += '<li>' + _esc(item) + '</li>';
            } else {
                var display = item.name || item.title || _itemId(item);
                var id = _itemId(item);
                html += '<li>' + _esc(display) + (id ? ' <span class="ab-wg-id">(' + _esc(id) + ')</span>' : '') + '</li>';
            }
        });
        html += '</ul></div>';
        return html;
    }

    function _inspectorNpc(entity) {
        var html = '';
        html += _inspectorField('Role', entity.role);
        html += _inspectorField('Faction', entity.faction_id);
        html += _inspectorField('Location', entity.location_id);
        html += _inspectorField('Description', entity.description);
        html += _inspectorList('Goals', entity.goals);
        html += _inspectorList('Related Threads', entity.related_threads);
        return html;
    }

    function _inspectorFaction(entity) {
        var html = '';
        html += _inspectorField('Description', entity.description);
        html += _inspectorList('Goals', entity.goals);
        html += _inspectorList('Members', entity.members);
        html += _inspectorList('Related Locations', entity.related_locations);
        html += _inspectorList('Related Threads', entity.related_threads);
        return html;
    }

    function _inspectorLocation(entity) {
        var html = '';
        html += _inspectorField('Description', entity.description);
        html += _inspectorList('Tags', entity.tags);
        html += _inspectorList('Residents', entity.residents);
        html += _inspectorList('Involved Factions', entity.involved_factions);
        html += _inspectorList('Related Threads', entity.related_threads);
        return html;
    }

    function _inspectorThread(entity) {
        var html = '';
        html += _inspectorField('Description', entity.description);
        html += _inspectorField('Status', entity.status || 'active');
        html += _inspectorList('Involved Entities', entity.involved_entities);
        html += _inspectorList('Faction IDs', entity.faction_ids);
        html += _inspectorList('Location IDs', entity.location_ids);
        return html;
    }

    // ─────────────────────────────────────────────────────────────────────
    // Simulation panel
    // ─────────────────────────────────────────────────────────────────────

    function renderSimulation(container, simulationData) {
        if (!simulationData) {
            container.innerHTML = '<div class="ab-wg-sim-empty">No simulation data available</div>';
            return;
        }

        var html = '<div class="ab-wg-simulation">';

        // Entity counts
        var counts = simulationData.entity_counts || {};
        html += '<div class="ab-wg-sim-section">';
        html += '<h5 class="ab-wg-sim-title">📊 Entity Counts</h5>';
        html += '<div class="ab-wg-sim-counts">';
        html += _simCountCard('⚔️', 'Factions', counts.factions || 0);
        html += _simCountCard('📍', 'Locations', counts.locations || 0);
        html += _simCountCard('👤', 'NPCs', counts.npcs || 0);
        html += _simCountCard('🔗', 'Threads', counts.threads || 0);
        html += '</div></div>';

        // Hot locations
        var hotLocs = simulationData.hot_locations || [];
        if (hotLocs.length) {
            html += '<div class="ab-wg-sim-section">';
            html += '<h5 class="ab-wg-sim-title">🔥 Hot Locations</h5>';
            hotLocs.forEach(function (loc) {
                html += '<div class="ab-wg-sim-item ab-wg-sim-hot">' +
                    '<span class="ab-wg-sim-item-name">' + _esc(loc.name) + '</span>' +
                    '<span class="ab-wg-sim-item-detail">' + loc.npc_count + ' NPCs, ' + loc.thread_count + ' threads</span>' +
                    '</div>';
            });
            html += '</div>';
        }

        // Faction tensions
        var tensions = simulationData.faction_tensions || [];
        if (tensions.length) {
            html += '<div class="ab-wg-sim-section">';
            html += '<h5 class="ab-wg-sim-title">⚡ Faction Tensions</h5>';
            tensions.forEach(function (t) {
                html += '<div class="ab-wg-sim-item ab-wg-sim-tension">' +
                    '<span class="ab-wg-sim-item-name">' + _esc(t.factions.join(' ↔ ')) + '</span>' +
                    '<span class="ab-wg-sim-item-detail">shared threads' + (t.shared_npc_count ? ', ' + t.shared_npc_count + ' shared NPCs' : '') + '</span>' +
                    '</div>';
            });
            html += '</div>';
        }

        // Unresolved threads
        var unresolved = simulationData.unresolved_threads || [];
        if (unresolved.length) {
            html += '<div class="ab-wg-sim-section">';
            html += '<h5 class="ab-wg-sim-title">📌 Unresolved Threads</h5>';
            unresolved.forEach(function (t) {
                html += '<div class="ab-wg-sim-item">' +
                    '<span class="ab-wg-sim-item-name">' + _esc(t.title || t.thread_id) + '</span>' +
                    '</div>';
            });
            html += '</div>';
        }

        // Warnings: orphan NPCs and isolated factions
        var orphans = simulationData.orphan_npcs || [];
        var isolated = simulationData.isolated_factions || [];
        if (orphans.length || isolated.length) {
            html += '<div class="ab-wg-sim-section ab-wg-sim-warnings">';
            html += '<h5 class="ab-wg-sim-title">⚠️ Warnings</h5>';
            orphans.forEach(function (o) {
                html += '<div class="ab-wg-sim-item ab-wg-sim-warn">' +
                    '👤 <strong>' + _esc(o.name || o.npc_id) + '</strong> has no faction or location' +
                    '</div>';
            });
            isolated.forEach(function (f) {
                html += '<div class="ab-wg-sim-item ab-wg-sim-warn">' +
                    '⚔️ <strong>' + _esc(f.name || f.faction_id) + '</strong> has no members or thread links' +
                    '</div>';
            });
            html += '</div>';
        }

        // Resolved context
        var ctx = simulationData.resolved_context || {};
        if (ctx.location_id || ctx.opening_text) {
            html += '<div class="ab-wg-sim-section">';
            html += '<h5 class="ab-wg-sim-title">🎬 Resolved Opening</h5>';
            if (ctx.location_id) {
                html += '<div class="ab-wg-sim-item">Starting at: <strong>' + _esc(ctx.location_id) + '</strong></div>';
            }
            if (ctx.npc_ids && ctx.npc_ids.length) {
                html += '<div class="ab-wg-sim-item">Present: ' + _esc(ctx.npc_ids.join(', ')) + '</div>';
            }
            if (ctx.opening_text) {
                html += '<div class="ab-wg-sim-item ab-wg-sim-opening-text"><em>' + _esc(ctx.opening_text) + '</em></div>';
            }
            html += '</div>';
        }

        html += '</div>';
        container.innerHTML = html;
    }

    function _simCountCard(icon, label, count) {
        return '<div class="ab-wg-count-card">' +
            '<div class="ab-wg-count-icon">' + icon + '</div>' +
            '<div class="ab-wg-count-num">' + count + '</div>' +
            '<div class="ab-wg-count-label">' + _esc(label) + '</div>' +
            '</div>';
    }

    // ─────────────────────────────────────────────────────────────────────
    // Tab strip for World Graph sub-views
    // ─────────────────────────────────────────────────────────────────────

    function renderTabStrip(container, activeTab, onTabChange) {
        var tabs = [
            { id: 'graph', icon: '🕸️', label: 'World Graph' },
            { id: 'simulation', icon: '📊', label: 'Simulation' },
            { id: 'inspector', icon: '🔍', label: 'Inspector' }
        ];
        var html = '<div class="ab-wg-tabs">';
        tabs.forEach(function (t) {
            var active = t.id === activeTab ? ' ab-wg-tab-active' : '';
            html += '<button class="ab-wg-tab' + active + '" data-tab="' + t.id + '">' + t.icon + ' ' + _esc(t.label) + '</button>';
        });
        html += '</div>';
        container.innerHTML = html;

        container.querySelectorAll('.ab-wg-tab').forEach(function (btn) {
            btn.addEventListener('click', function () {
                onTabChange(btn.getAttribute('data-tab'));
            });
        });
    }

    // ─────────────────────────────────────────────────────────────────────
    // Public API
    // ─────────────────────────────────────────────────────────────────────

    return {
        renderGraph: renderGraph,
        renderGraphControls: renderGraphControls,
        renderLegend: renderLegend,
        renderInspector: renderInspector,
        renderSimulation: renderSimulation,
        renderTabStrip: renderTabStrip,
        NODE_CONFIG: NODE_CONFIG,
        EDGE_CONFIG: EDGE_CONFIG
    };
})();
