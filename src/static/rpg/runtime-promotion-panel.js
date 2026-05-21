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
        var presentation = safeObj(payload.presentation);
        var panel = safeObj(
            payload.runtime_promotion_panel
            || presentation.runtime_promotion_panel
            || safeObj(payload.result).runtime_promotion_panel
        );
        var climate = safeObj(
            payload.climate_survival
            || payload.climate_survival_runtime_payload
            || presentation.climate_survival
            || panel.climate_survival
        );
        var audit = safeObj(
            payload.runtime_promotion_summary
            || safeObj(payload.runtime_state).runtime_promotion_summary
            || panel.runtime_promotion
        );
        return {
            panel: panel,
            climate: climate,
            audit: audit,
        };
    }

    function buildClimateHtml(climate) {
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
        var html = buildClimateHtml(normalized.climate) + buildAuditHtml(normalized.audit);
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
            '.rpg-runtime-card-grid{display:grid;grid-template-columns:auto 1fr;gap:4px 10px;margin:0;font-size:12px;}' +
            '.rpg-runtime-card-grid dt{opacity:.72;}' +
            '.rpg-runtime-card-grid dd{margin:0;}' +
            '.rpg-runtime-card--audit summary{cursor:pointer;font-weight:700;}' +
            '.rpg-runtime-audit-list{list-style:none;margin:8px 0 0;padding:0;display:grid;gap:4px;font-size:12px;}' +
            '.rpg-runtime-audit-list li{display:flex;justify-content:space-between;gap:10px;border-top:1px solid rgba(255,255,255,.08);padding-top:4px;}' +
            '.rpg-runtime-audit-list strong{font-weight:700;white-space:nowrap;}';
        document.head.appendChild(style);
    }

    installStyles();

    window.RpgRuntimePromotionPanel = {
        render: render,
        normalizePayload: normalizePayload,
    };

    window.addEventListener('rpg:climate-survival-update', function (event) {
        render(safeObj(event.detail));
    });

    window.addEventListener('rpg:turn-payload', function (event) {
        render(safeObj(event.detail));
    });
})();
