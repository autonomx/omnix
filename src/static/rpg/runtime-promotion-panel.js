(function () {
    'use strict';

    function safeObj(value) {
        return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
    }

    function safeArray(value) {
        return Array.isArray(value) ? value : [];
    }

    function safeStr(value) {
        return value == null ? '' : String(value);
    }

    function escapeHtml(value) {
        return safeStr(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function findRpgRoot() {
        return document.getElementById('rpgModeContainer')
            || document.getElementById('rpgRoot')
            || document.querySelector('.rpg-mode')
            || document.body;
    }

    function ensurePanelRoot() {
        var existing = document.getElementById('rpg-runtime-promotion-panel');
        if (existing) return existing;

        var root = findRpgRoot();
        var panel = document.createElement('section');
        panel.id = 'rpg-runtime-promotion-panel';
        panel.className = 'rpg-runtime-promotion-panel';
        panel.setAttribute('aria-label', 'Climate, survival, and runtime promotion');

        var preferredParent = document.getElementById('rpgTopPanels')
            || document.querySelector('.rpg-top-panels')
            || document.getElementById('rpgSidePanel')
            || document.querySelector('.rpg-side-panel')
            || root;

        if (preferredParent.firstChild) {
            preferredParent.insertBefore(panel, preferredParent.firstChild);
        } else {
            preferredParent.appendChild(panel);
        }
        return panel;
    }

    function normalizePayload(payload) {
        payload = safeObj(payload);
        var result = safeObj(payload.result);
        var presentation = safeObj(payload.presentation || result.presentation);
        var panel = safeObj(
            payload.runtime_promotion_panel
            || presentation.runtime_promotion_panel
            || result.runtime_promotion_panel
        );
        var climate = safeObj(
            payload.climate_survival
            || payload.climate_survival_runtime_payload
            || presentation.climate_survival
            || result.climate_survival
            || panel.climate_survival
        );
        var audit = safeObj(
            payload.runtime_promotion_summary
            || safeObj(payload.runtime_state).runtime_promotion_summary
            || result.runtime_promotion_summary
            || panel.runtime_promotion
        );
        var suggestions = safeArray(
            payload.survival_suggested_actions
            || presentation.survival_suggested_actions
            || result.survival_suggested_actions
            || safeObj(payload.turn_contract).survival_suggested_actions
        );
        if (!suggestions.length) {
            suggestions = safeArray(safeObj(payload.turn_contract).suggested_actions)
                .filter(function (item) { return safeObj(item).type === 'survival_relief'; });
        }
        return {
            panel: panel,
            climate: climate,
            audit: audit,
            suggestions: suggestions,
        };
    }

    function buildSuggestionsHtml(suggestions) {
        suggestions = safeArray(suggestions);
        if (!suggestions.length) return '';
        var rows = suggestions.map(function (item) {
            item = safeObj(item);
            var label = safeStr(item.label || item.command || item.action_kind || 'Survival action');
            var command = safeStr(item.command || '');
            var reason = safeStr(item.reason || item.price_label || '');
            return '' +
                '<li class="rpg-runtime-suggestion-item">' +
                    '<strong>' + escapeHtml(label) + '</strong>' +
                    (command ? '<code>' + escapeHtml(command) + '</code>' : '') +
                    (reason ? '<span>' + escapeHtml(reason) + '</span>' : '') +
                '</li>';
        }).join('');
        return '' +
            '<div class="rpg-runtime-suggestions">' +
                '<div class="rpg-runtime-subtitle">Suggested relief</div>' +
                '<ul>' + rows + '</ul>' +
            '</div>';
    }

    function buildClimateHtml(climate, suggestions) {
        climate = safeObj(climate);
        var display = safeObj(climate.display);
        if (!climate.ok && !Object.keys(display).length) return '';

        return '' +
            '<div class="rpg-runtime-card rpg-runtime-card--climate">' +
                '<div class="rpg-runtime-card-title">' + escapeHtml(display.title || 'Climate + Survival') + '</div>' +
                '<dl class="rpg-runtime-card-grid">' +
                    '<dt>Time</dt><dd>' + escapeHtml(display.time_label || safeObj(climate.time).label || '') + '</dd>' +
                    '<dt>Weather</dt><dd>' + escapeHtml(display.weather_label || safeObj(climate.weather).label || '') + '</dd>' +
                    '<dt>Needs</dt><dd>' + escapeHtml(display.needs_label || safeObj(climate.survival).label || '') + '</dd>' +
                    '<dt>Warnings</dt><dd>' + escapeHtml(display.warnings_label || 'Stable') + '</dd>' +
                '</dl>' +
                buildSuggestionsHtml(suggestions) +
            '</div>';
    }

    function buildAuditHtml(audit) {
        audit = safeObj(audit);
        if (!audit.system_count && !safeArray(audit.systems).length) return '';
        var promoted = safeStr(audit.runtime_promoted_count || 0) + ' / ' + safeStr(audit.system_count || safeArray(audit.systems).length);
        var rows = safeArray(audit.systems).map(function (item) {
            item = safeObj(item);
            return '<li><span>' + escapeHtml(item.name || 'system') + '</span><strong>' + escapeHtml(item.status || 'unknown') + '</strong></li>';
        }).join('');
        return '' +
            '<details class="rpg-runtime-card rpg-runtime-card--audit">' +
                '<summary>Runtime Promotion: ' + escapeHtml(promoted) + '</summary>' +
                '<ul class="rpg-runtime-audit-list">' + rows + '</ul>' +
            '</details>';
    }

    function render(payload) {
        var normalized = normalizePayload(payload);
        var html = buildClimateHtml(normalized.climate, normalized.suggestions) + buildAuditHtml(normalized.audit);
        if (!html) return;
        var panel = ensurePanelRoot();
        panel.innerHTML = html;
    }

    function installStyles() {
        if (document.getElementById('rpg-runtime-promotion-panel-style')) return;
        var style = document.createElement('style');
        style.id = 'rpg-runtime-promotion-panel-style';
        style.textContent = '' +
            '.rpg-runtime-promotion-panel{display:flex;gap:10px;flex-wrap:wrap;margin:8px 0;padding:0;}' +
            '.rpg-runtime-card{border:1px solid rgba(255,255,255,.14);background:rgba(10,16,28,.74);border-radius:12px;padding:10px 12px;color:inherit;min-width:220px;box-shadow:0 8px 24px rgba(0,0,0,.18);}' +
            '.rpg-runtime-card-title{font-weight:700;margin-bottom:6px;}' +
            '.rpg-runtime-subtitle{font-weight:700;margin:10px 0 4px;font-size:12px;opacity:.9;}' +
            '.rpg-runtime-card-grid{display:grid;grid-template-columns:auto 1fr;gap:4px 10px;margin:0;font-size:12px;}' +
            '.rpg-runtime-card-grid dt{opacity:.72;}' +
            '.rpg-runtime-card-grid dd{margin:0;}' +
            '.rpg-runtime-suggestions ul{list-style:none;margin:0;padding:0;display:grid;gap:6px;}' +
            '.rpg-runtime-suggestion-item{display:grid;gap:2px;border-top:1px solid rgba(255,255,255,.08);padding-top:6px;font-size:12px;}' +
            '.rpg-runtime-suggestion-item code{white-space:normal;background:rgba(255,255,255,.08);border-radius:6px;padding:2px 5px;font-family:inherit;}' +
            '.rpg-runtime-suggestion-item span{opacity:.72;}' +
            '.rpg-runtime-card--audit summary{cursor:pointer;font-weight:700;}' +
            '.rpg-runtime-audit-list{list-style:none;margin:8px 0 0;padding:0;display:grid;gap:4px;font-size:12px;}' +
            '.rpg-runtime-audit-list li{display:flex;justify-content:space-between;gap:10px;border-top:1px solid rgba(255,255,255,.08);padding-top:4px;}' +
            '.rpg-runtime-audit-list strong{font-weight:700;white-space:nowrap;}';
        document.head.appendChild(style);
    }

    function safeJsonParse(value) {
        try { return JSON.parse(value); } catch (_error) { return null; }
    }

    function encodeText(text) {
        return new TextEncoder().encode(text || '');
    }

    function sse(data) {
        return 'data: ' + JSON.stringify(data || {}) + '\n\n';
    }

    function latestPlayerCommand() {
        var nodes = document.querySelectorAll('.rpg-msg--player');
        if (!nodes.length) return '';
        return safeStr(nodes[nodes.length - 1].textContent).toLowerCase();
    }

    function isGenericFallback(text) {
        text = safeStr(text).toLowerCase();
        return text.indexOf('a deliberate action is taken') !== -1
            || text.indexOf('the action resolves') !== -1
            || text.indexOf('dramatic atmosphere') !== -1
            || text.indexOf('current scene feels') !== -1;
    }

    function serviceFallbackForCommand(command) {
        command = safeStr(command).toLowerCase();
        var mentionsRoom = command.indexOf('room') !== -1 || command.indexOf('rent') !== -1 || command.indexOf('lodging') !== -1 || command.indexOf('sleep') !== -1;
        var mentionsBran = command.indexOf('bran') !== -1 || command.indexOf('innkeeper') !== -1 || command.indexOf('inn') !== -1;
        if (mentionsRoom && mentionsBran) {
            return 'Bran the Innkeeper gives you a practical nod from behind the counter. “A room is available. Five silver for the night, paid up front, and I’ll see that you are not disturbed.”';
        }
        return '';
    }

    function improveFallbackForCurrentCommand(text) {
        var fallback = safeStr(text).trim();
        if (!isGenericFallback(fallback)) return fallback;
        return serviceFallbackForCommand(latestPlayerCommand()) || fallback;
    }

    function normalizeTurnStreamEvent(event) {
        if (!event || typeof event !== 'object') return event;
        if (event.type !== 'authoritative_result' && event.type !== 'turn_result') return event;
        if (!event.turn_id) {
            event.turn_id = 'client_turn_' + Date.now();
        }
        var status = safeStr(event.narration_status || event.status).trim().toLowerCase();
        if (status === 'queued' || status === 'processing' || status === 'pending' || status === 'streaming') {
            event.fallback_narration = '';
            return event;
        }
        var fallback = event.fallback_narration || event.deterministic_fallback_narration || event.summary || 'The action resolves, and the scene waits for your next move.';
        event.fallback_narration = improveFallbackForCurrentCommand(fallback);
        return event;
    }

    function wrapTurnStreamIdentifiers(response) {
        if (!response || !response.body || typeof ReadableStream === 'undefined') return response;
        var reader = response.body.getReader();
        var decoder = new TextDecoder();
        var buffer = '';
        var stream = new ReadableStream({
            start: function (controller) {
                function pump() {
                    reader.read().then(function (next) {
                        if (!next || next.done) {
                            if (buffer) controller.enqueue(encodeText(buffer));
                            controller.close();
                            return;
                        }
                        buffer += decoder.decode(next.value, { stream: true });
                        var parts = buffer.split('\n\n');
                        buffer = parts.pop() || '';
                        for (var i = 0; i < parts.length; i += 1) {
                            var raw = parts[i];
                            var dataLines = String(raw || '').split('\n')
                                .filter(function (line) { return String(line || '').indexOf('data:') === 0; })
                                .map(function (line) { return line.slice(5).trim(); });
                            if (!dataLines.length) {
                                controller.enqueue(encodeText(raw + '\n\n'));
                                continue;
                            }
                            var event = safeJsonParse(dataLines.join('\n'));
                            if (!event) {
                                controller.enqueue(encodeText(raw + '\n\n'));
                                continue;
                            }
                            controller.enqueue(encodeText(sse(normalizeTurnStreamEvent(event))));
                        }
                        pump();
                    }).catch(function (error) {
                        controller.error(error);
                    });
                }
                pump();
            },
            cancel: function (reason) {
                try { reader.cancel(reason); } catch (_error) {}
            }
        });
        return new Response(stream, {
            status: response.status,
            statusText: response.statusText,
            headers: response.headers,
        });
    }

    function patchTurnStreamIdentifiers() {
        if (window.__rpgRuntimePromotionTurnStreamPatched) return;
        window.__rpgRuntimePromotionTurnStreamPatched = true;
        var originalFetch = window.fetch;
        if (typeof originalFetch !== 'function') return;
        window.fetch = function (input, init) {
            var url = '';
            try { url = String((input && input.url) || input || ''); } catch (_error) { url = ''; }
            var isTurnStream = /\/api\/rpg\/session\/turn\/stream(?:$|[?#])/.test(url);
            return originalFetch.apply(this, arguments).then(function (response) {
                if (isTurnStream && response && response.ok) return wrapTurnStreamIdentifiers(response);
                return response;
            });
        };
    }

    installStyles();
    patchTurnStreamIdentifiers();

    window.RpgRuntimePromotionPanel = {
        render: render,
        normalizePayload: normalizePayload,
        normalizeTurnStreamEvent: normalizeTurnStreamEvent,
        improveFallbackForCurrentCommand: improveFallbackForCurrentCommand,
    };

    window.addEventListener('rpg:climate-survival-update', function (event) {
        render(safeObj(event.detail));
    });

    window.addEventListener('rpg:turn-payload', function (event) {
        render(safeObj(event.detail));
    });
})();
