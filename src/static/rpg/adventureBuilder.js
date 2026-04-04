/**
 * Adventure Builder — 5-Step Wizard
 *
 * Phase 1.2 modularization:
 * - state persistence/defaults moved to AdventureBuilderState
 * - shared shell/summary rendering moved to AdventureBuilderRenderer
 * - step-specific control flow stays here
 */
/* global AdventureBuilderApi, AdventureBuilderState, AdventureBuilderRenderer */

var AdventureBuilder = (function () {
    'use strict';

    // ─────────────────────────────────────────────────────────────────────────
    // State / DOM
    // ─────────────────────────────────────────────────────────────────────────

    var state = AdventureBuilderState.buildInitialState();
    var currentStep = state.step;
    var overlayEl = null;
    var _debounceTimer = null;

    // Alias state.setup as "setup" for backward compatibility
    var setup = state.setup;

    // ─────────────────────────────────────────────────────────────────────────
    // Constants
    // ─────────────────────────────────────────────────────────────────────────

    var STEP_COUNT = 5;
    var DEBOUNCE_MS = 400;

    // ─────────────────────────────────────────────────────────────────────────
    // Persistence / state mutations
    // ─────────────────────────────────────────────────────────────────────────

    function _saveDraft() {
        AdventureBuilderState.saveDraft(state.setup);
    }

    function _resetState() {
        AdventureBuilderState.resetState(state);
        setup = state.setup;
        currentStep = state.step;
        state.validation = null;
        state.preview = null;
    }

    function _clearDraft() {
        AdventureBuilderState.clearDraft();
    }

    function _markDirty() {
        AdventureBuilderState.markDirty(state);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // DOM helpers
    // ─────────────────────────────────────────────────────────────────────────

    var _esc = AdventureBuilderRenderer.esc;

    function _val(id) {
        var el = overlayEl ? overlayEl.querySelector('#' + id) : null;
        return el ? (el.value || '').trim() : '';
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Debounced validation / preview
    // ─────────────────────────────────────────────────────────────────────────

    function _scheduleValidation() {
        clearTimeout(_debounceTimer);
        _debounceTimer = setTimeout(function () {
            _runValidation();
            if (currentStep === 5) _runPreview();
        }, DEBOUNCE_MS);
    }

    function _runValidation() {
        _readCurrentStepIntoSetup();
        _markDirty();
        AdventureBuilderApi.validateSetup(state.setup).then(function (res) {
            state.validation = res.validation || null;
            _renderInlineIssues();
            _updateLaunchButton();
        }).catch(function () { /* ignore */ });
    }

    function _runPreview() {
        AdventureBuilderApi.previewSetup(state.setup).then(function (res) {
            state.preview = res;
            if (currentStep === 5) _renderPreviewPanel();
        }).catch(function () { /* ignore */ });
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Open / Close
    // ─────────────────────────────────────────────────────────────────────────

    function open() {
        if (overlayEl) { overlayEl.style.display = 'flex'; return; }
        _buildOverlay();
        _loadTemplates();
        _renderStep();
    }

    function close() {
        if (overlayEl) overlayEl.style.display = 'none';
    }

    function _buildOverlay() {
        overlayEl = document.createElement('div');
        overlayEl.id = 'adventureBuilderOverlay';
        overlayEl.className = 'ab-overlay';
        overlayEl.innerHTML =
            '<div class="ab-modal">' +
                '<div class="ab-header">' +
                    '<h3 class="ab-title">\uD83C\uDFAD Adventure Builder</h3>' +
                    '<button class="ab-close" id="abClose">&times;</button>' +
                '</div>' +
                '<div class="ab-progress" id="abProgress"></div>' +
                '<div class="ab-body" id="abBody"></div>' +
                '<div class="ab-validation-bar" id="abValidationBar"></div>' +
                '<div class="ab-footer" id="abFooter"></div>' +
            '</div>';
        document.body.appendChild(overlayEl);
        overlayEl.querySelector('#abClose').addEventListener('click', close);
        overlayEl.addEventListener('click', function (e) {
            if (e.target === overlayEl) close();
        });
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Step navigation
    // ─────────────────────────────────────────────────────────────────────────

    function _goStep(n) {
        _readCurrentStepIntoSetup();
        _markDirty();
        currentStep = Math.max(1, Math.min(STEP_COUNT, n));
        state.step = currentStep;
        _renderStep();
        if (currentStep === 5) { _runValidation(); _runPreview(); }
    }

    function _renderStep() {
        _renderProgress();
        var body = overlayEl.querySelector('#abBody');
        body.innerHTML = '';
        switch (currentStep) {
            case 1: _renderStep1(body); break;
            case 2: _renderStep2(body); break;
            case 3: _renderStep3(body); break;
            case 4: _renderStep4(body); break;
            case 5: _renderStep5(body); break;
        }
        _renderFooter();
    }

    function _renderProgress() {
        var labels = ['Basics', 'Rules', 'World', 'Start', 'Review'];
        var html = '';
        for (var i = 0; i < labels.length; i++) {
            var cls = 'ab-step-dot';
            if (i + 1 === currentStep) cls += ' ab-step-active';
            else if (i + 1 < currentStep) cls += ' ab-step-done';
            html += '<span class="' + cls + '" data-step="' + (i + 1) + '">' + labels[i] + '</span>';
        }
        var prog = overlayEl.querySelector('#abProgress');
        prog.innerHTML = html;
        prog.querySelectorAll('.ab-step-dot').forEach(function (dot) {
            dot.addEventListener('click', function () {
                _goStep(parseInt(dot.getAttribute('data-step'), 10));
            });
        });
    }

    function _renderFooter() {
        var footer = overlayEl.querySelector('#abFooter');
        var html = '';
        if (currentStep > 1) {
            html += '<button class="ab-btn ab-btn-secondary" id="abPrev">\u2190 Back</button>';
        }
        html += '<button class="ab-btn ab-btn-secondary" id="abSaveDraft">\uD83D\uDCBE Save Draft</button>';
        if (currentStep < STEP_COUNT) {
            html += '<button class="ab-btn ab-btn-primary" id="abNext">Next \u2192</button>';
        } else {
            html += '<button class="ab-btn ab-btn-launch" id="abLaunch" disabled>\u2694\uFE0F Launch Adventure</button>';
        }
        footer.innerHTML = html;

        var prevBtn = footer.querySelector('#abPrev');
        if (prevBtn) prevBtn.addEventListener('click', function () { _goStep(currentStep - 1); });
        var nextBtn = footer.querySelector('#abNext');
        if (nextBtn) nextBtn.addEventListener('click', function () { _goStep(currentStep + 1); });
        var saveBtn = footer.querySelector('#abSaveDraft');
        if (saveBtn) saveBtn.addEventListener('click', function () {
            _readCurrentStepIntoSetup(); _markDirty();
            saveBtn.textContent = '\u2705 Saved!';
            setTimeout(function () { saveBtn.textContent = '\uD83D\uDCBE Save Draft'; }, 1200);
        });
        var launchBtn = footer.querySelector('#abLaunch');
        if (launchBtn) launchBtn.addEventListener('click', _handleLaunch);
        _updateLaunchButton();
    }

    function _updateLaunchButton() {
        if (!overlayEl) return;
        var btn = overlayEl.querySelector('#abLaunch');
        if (!btn) return;
        var v = state.validation;
        btn.disabled = !!(v && v.blocking);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // API orchestration
    // ─────────────────────────────────────────────────────────────────────────

    var templates = [];

    function _loadTemplates() {
        AdventureBuilderApi.getTemplates().then(function (res) {
            templates = res.templates || [];
            if (currentStep === 1) _renderTemplateGallery();
        }).catch(function () { templates = []; });
    }

    function _applyTemplate(name) {
        AdventureBuilderApi.buildTemplate(name).then(function (res) {
            if (res.success && res.setup) {
                AdventureBuilderState.hydrateFromTemplate(state, res.setup || {}, name);
                setup = state.setup;
                if (!setup.title) {
                    setup.title = (name || '').replace(/_/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); });
                }
                _markDirty();
                _renderStep();
            }
        }).catch(function () { /* ignore */ });
    }

    function _templateIcon(genre) {
        var icons = {
            fantasy: '\u2694\uFE0F',
            'political intrigue': '\uD83D\uDC51',
            'mystery noir': '\uD83D\uDD75\uFE0F',
            grimdark: '\uD83D\uDC80',
            cyberpunk: '\uD83E\uDD16',
        };
        return icons[(genre || '').toLowerCase()] || '\uD83C\uDFAD';
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Rendering
    // ─────────────────────────────────────────────────────────────────────────

    // ── Step 1: Template / Basics ──

    function _renderStep1(body) {
        var html = '<div class="ab-section">' +
            '<h4>Choose a Template</h4>' +
            '<div class="ab-template-gallery" id="abTemplateGallery"></div>' +
            '</div>' +
            '<div class="ab-section">' +
            '<h4>Basic Details</h4>' +
            _field('Title', 'abTitle', 'text', setup.title, 'Adventure title') +
            _field('Genre', 'abGenre', 'text', setup.genre, 'fantasy, sci-fi, noir\u2026') +
            _field('Setting', 'abSetting', 'text', setup.setting, 'A medieval kingdom\u2026') +
            _textareaField('Premise', 'abPremise', setup.premise, 'What is the adventure about?', 3) +
            _field('Player Name', 'abPlayerName', 'text', (setup.metadata || {}).player_name || '', 'Player') +
            _selectField('Difficulty', 'abDifficulty', setup.difficulty_style, ['', 'easy', 'moderate', 'hard', 'brutal']) +
            _selectField('Mood', 'abMood', setup.mood, ['', 'heroic', 'dark', 'tense', 'grim', 'edgy', 'whimsical', 'epic']) +
            '</div>';
        body.innerHTML = html;
        _renderTemplateGallery();
        _attachBlurValidation(body);
    }

    function _renderTemplateGallery() {
        var gal = overlayEl ? overlayEl.querySelector('#abTemplateGallery') : null;
        if (!gal) return;
        if (!templates.length) { gal.innerHTML = '<p class="ab-muted">Loading templates\u2026</p>'; return; }
        var html = '<div class="ab-tpl-row">';
        html += '<div class="ab-tpl-card ab-tpl-blank" data-tpl="">' +
                    '<div class="ab-tpl-icon">\u2728</div>' +
                    '<div class="ab-tpl-name">Blank Setup</div>' +
                    '<div class="ab-tpl-desc">Start from scratch</div>' +
                '</div>';
        templates.forEach(function (t) {
            html += '<div class="ab-tpl-card" data-tpl="' + _esc(t.name) + '">' +
                        '<div class="ab-tpl-icon">' + _templateIcon(t.genre) + '</div>' +
                        '<div class="ab-tpl-name">' + _esc(t.label || t.name) + '</div>' +
                        '<div class="ab-tpl-genre">' + _esc(t.genre) + ' \u00B7 ' + _esc(t.mood) + '</div>' +
                        '<div class="ab-tpl-desc">' + _esc(t.description || '') + '</div>' +
                        '<button class="ab-tpl-use">Use Template</button>' +
                    '</div>';
        });
        html += '</div>';
        gal.innerHTML = html;
        gal.querySelectorAll('.ab-tpl-card').forEach(function (card) {
            card.addEventListener('click', function () {
                var name = card.getAttribute('data-tpl');
                if (!name) { _resetState(); _renderStep(); return; }
                _applyTemplate(name);
            });
        });
    }

    // ── Step 2: Rules / Tone ──

    function _renderStep2(body) {
        var html = '<div class="ab-section">' +
            '<h4>Hard Rules</h4>' +
            '<p class="ab-hint">Strict world rules the GM must enforce.</p>' +
            _chipEditor('abHardRules', setup.hard_rules, 'e.g. Magic has consequences') +
            '</div>' +
            '<div class="ab-section">' +
            '<h4>Tone Rules</h4>' +
            '<p class="ab-hint">Soft tonal guidance for the narrative style.</p>' +
            _chipEditor('abToneRules', setup.soft_tone_rules, 'e.g. Dark and atmospheric') +
            '</div>' +
            '<div class="ab-section">' +
            '<h4>Forbidden Content</h4>' +
            '<p class="ab-hint">Topics or themes that should not appear.</p>' +
            _chipEditor('abForbidden', setup.forbidden_content, 'e.g. Graphic violence against children') +
            '</div>' +
            '<div class="ab-section">' +
            '<h4>Canon Notes</h4>' +
            '<p class="ab-hint">Important world lore facts the GM should respect.</p>' +
            _chipEditor('abCanonNotes', setup.canon_notes, 'e.g. The king has been dead for 10 years') +
            '</div>';
        body.innerHTML = html;
        _attachChipEditors(body);
        _attachBlurValidation(body);
    }

    // ── Step 3: World Seeds ──

    function _renderStep3(body) {
        var html = '<div class="ab-section">' +
            '<h4>Factions</h4>' +
            '<div class="ab-inline-actions">' +
                '<button id="abRegenFactions" class="ab-btn ab-btn-secondary ab-btn-sm">♻ Regenerate Factions</button>' +
            '</div>' +
            '<div id="abFactionList"></div>' +
            '<button class="ab-btn ab-btn-add" id="abAddFaction">+ Add Faction</button>' +
            '</div>' +
            '<div class="ab-section">' +
            '<h4>Locations</h4>' +
            '<div class="ab-inline-actions">' +
                '<button id="abRegenLocations" class="ab-btn ab-btn-secondary ab-btn-sm">♻ Regenerate Locations</button>' +
            '</div>' +
            '<div id="abLocationList"></div>' +
            '<button class="ab-btn ab-btn-add" id="abAddLocation">+ Add Location</button>' +
            '</div>' +
            '<div class="ab-section">' +
            '<h4>NPCs</h4>' +
            '<div class="ab-inline-actions">' +
                '<button id="abRegenNpcs" class="ab-btn ab-btn-secondary ab-btn-sm">♻ Regenerate NPCs</button>' +
            '</div>' +
            '<div id="abNpcList"></div>' +
            '<button class="ab-btn ab-btn-add" id="abAddNpc">+ Add NPC</button>' +
            '</div>';
        body.innerHTML = html;

        _renderFactionCards();
        _renderLocationCards();
        _renderNpcCards();

        body.querySelector('#abAddFaction').addEventListener('click', function () {
            setup.factions.push({ faction_id: '', name: '', description: '', goals: [] });
            _markDirty();
            _renderFactionCards();
        });
        body.querySelector('#abAddLocation').addEventListener('click', function () {
            setup.locations.push({ location_id: '', name: '', description: '', tags: [] });
            _markDirty();
            _renderLocationCards();
        });
        body.querySelector('#abAddNpc').addEventListener('click', function () {
            setup.npc_seeds.push({ npc_id: '', name: '', role: '', description: '', goals: [], faction_id: '', location_id: '', must_survive: false });
            _markDirty();
            _renderNpcCards();
        });

        // Regeneration button bindings for Step 3
        var regenFactionsBtn = body.querySelector('#abRegenFactions');
        if (regenFactionsBtn) regenFactionsBtn.addEventListener('click', function () { _handleRegenerate('factions'); });

        var regenLocationsBtn = body.querySelector('#abRegenLocations');
        if (regenLocationsBtn) regenLocationsBtn.addEventListener('click', function () { _handleRegenerate('locations'); });

        var regenNpcsBtn = body.querySelector('#abRegenNpcs');
        if (regenNpcsBtn) regenNpcsBtn.addEventListener('click', function () { _handleRegenerate('npc_seeds'); });
    }

    // -- Faction cards

    function _renderFactionCards() {
        var list = overlayEl.querySelector('#abFactionList');
        if (!list) return;
        if (!setup.factions.length) { list.innerHTML = '<p class="ab-muted">No factions yet.</p>'; return; }
        var html = '';
        setup.factions.forEach(function (f, i) {
            html += '<div class="ab-entity-card" data-idx="' + i + '">' +
                '<div class="ab-entity-header">' +
                    '<span class="ab-entity-summary">' + _esc(f.name || 'Unnamed Faction') + '</span>' +
                    '<button class="ab-entity-del" data-type="faction" data-idx="' + i + '">\uD83D\uDDD1\uFE0F</button>' +
                    '<button class="ab-entity-toggle" data-idx="' + i + '">\u25BC</button>' +
                '</div>' +
                '<div class="ab-entity-body ab-entity-collapsed" id="abFaction' + i + '">' +
                    _field('Name', 'abFactionName' + i, 'text', f.name, 'Faction name') +
                    _field('ID', 'abFactionId' + i, 'text', f.faction_id, 'auto-generated from name') +
                    _textareaField('Description', 'abFactionDesc' + i, f.description, 'Faction description', 2) +
                    _chipEditor('abFactionGoals' + i, f.goals || [], 'Add a goal\u2026') +
                '</div>' +
            '</div>';
        });
        list.innerHTML = html;
        _attachEntityToggle(list);
        _attachEntityDelete(list, 'faction');
        _attachAutoSlug(list, 'Faction');
        _attachChipEditors(list);
    }

    // -- Location cards

    function _renderLocationCards() {
        var list = overlayEl.querySelector('#abLocationList');
        if (!list) return;
        if (!setup.locations.length) { list.innerHTML = '<p class="ab-muted">No locations yet.</p>'; return; }
        var html = '';
        setup.locations.forEach(function (loc, i) {
            html += '<div class="ab-entity-card" data-idx="' + i + '">' +
                '<div class="ab-entity-header">' +
                    '<span class="ab-entity-summary">' + _esc(loc.name || 'Unnamed Location') + '</span>' +
                    '<button class="ab-entity-del" data-type="location" data-idx="' + i + '">\uD83D\uDDD1\uFE0F</button>' +
                    '<button class="ab-entity-toggle" data-idx="' + i + '">\u25BC</button>' +
                '</div>' +
                '<div class="ab-entity-body ab-entity-collapsed" id="abLocation' + i + '">' +
                    _field('Name', 'abLocationName' + i, 'text', loc.name, 'Location name') +
                    _field('ID', 'abLocationId' + i, 'text', loc.location_id, 'auto-generated from name') +
                    _textareaField('Description', 'abLocationDesc' + i, loc.description, 'Describe this place', 2) +
                    _chipEditor('abLocationTags' + i, loc.tags || [], 'Add a tag\u2026') +
                '</div>' +
            '</div>';
        });
        list.innerHTML = html;
        _attachEntityToggle(list);
        _attachEntityDelete(list, 'location');
        _attachAutoSlug(list, 'Location');
        _attachChipEditors(list);
    }

    // -- NPC cards

    function _renderNpcCards() {
        var list = overlayEl.querySelector('#abNpcList');
        if (!list) return;
        if (!setup.npc_seeds.length) { list.innerHTML = '<p class="ab-muted">No NPCs yet.</p>'; return; }
        var html = '';
        setup.npc_seeds.forEach(function (npc, i) {
            html += '<div class="ab-entity-card" data-idx="' + i + '">' +
                '<div class="ab-entity-header">' +
                    '<span class="ab-entity-summary">' + _esc(npc.name || 'Unnamed NPC') + '</span>' +
                    '<button class="ab-entity-del" data-type="npc" data-idx="' + i + '">\uD83D\uDDD1\uFE0F</button>' +
                    '<button class="ab-entity-toggle" data-idx="' + i + '">\u25BC</button>' +
                '</div>' +
                '<div class="ab-entity-body ab-entity-collapsed" id="abNpc' + i + '">' +
                    _field('Name', 'abNpcName' + i, 'text', npc.name, 'NPC name') +
                    _field('ID', 'abNpcId' + i, 'text', npc.npc_id, 'auto-generated from name') +
                    _field('Role', 'abNpcRole' + i, 'text', npc.role, 'merchant, guard, villain\u2026') +
                    _textareaField('Description', 'abNpcDesc' + i, npc.description, 'NPC background and personality', 2) +
                    _factionSelect('abNpcFaction' + i, npc.faction_id) +
                    _locationSelect('abNpcLocation' + i, npc.location_id) +
                    '<label class="ab-label"><input type="checkbox" id="abNpcSurvive' + i + '" ' + (npc.must_survive ? 'checked' : '') + '> Must Survive (plot armor)</label>' +
                    _chipEditor('abNpcGoals' + i, npc.goals || [], 'Add a goal\u2026') +
                '</div>' +
            '</div>';
        });
        list.innerHTML = html;
        _attachEntityToggle(list);
        _attachEntityDelete(list, 'npc');
        _attachAutoSlug(list, 'Npc');
        _attachChipEditors(list);
    }

    // -- Entity helpers

    function _attachEntityToggle(container) {
        container.querySelectorAll('.ab-entity-toggle').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var card = btn.closest('.ab-entity-card');
                var bodyEl = card.querySelector('.ab-entity-body');
                bodyEl.classList.toggle('ab-entity-collapsed');
                btn.textContent = bodyEl.classList.contains('ab-entity-collapsed') ? '\u25BC' : '\u25B2';
            });
        });
    }

    function _attachEntityDelete(container, type) {
        container.querySelectorAll('.ab-entity-del').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var idx = parseInt(btn.getAttribute('data-idx'), 10);
                if (type === 'faction') { setup.factions.splice(idx, 1); _markDirty(); _renderFactionCards(); }
                else if (type === 'location') { setup.locations.splice(idx, 1); _markDirty(); _renderLocationCards(); }
                else if (type === 'npc') { setup.npc_seeds.splice(idx, 1); _markDirty(); _renderNpcCards(); }
                _markDirty();
            });
        });
    }

    function _attachAutoSlug(container, prefix) {
        container.querySelectorAll('input[id^="ab' + prefix + 'Name"]').forEach(function (input) {
            var idx = input.id.replace('ab' + prefix + 'Name', '');
            var idField = container.querySelector('#ab' + prefix + 'Id' + idx);
            if (!idField) return;
            input.addEventListener('input', function () {
                var pfx = prefix.toLowerCase().substring(0, 3) + '_';
                if (!idField.dataset.manual) {
                    idField.value = _slug(input.value, pfx);
                }
            });
            idField.addEventListener('input', function () {
                idField.dataset.manual = '1';
            });
        });
    }

    function _factionSelect(id, current) {
        var opts = '<option value="">\u2014 None \u2014</option>';
        setup.factions.forEach(function (f) {
            var sel = (f.faction_id && f.faction_id === current) ? ' selected' : '';
            opts += '<option value="' + _esc(f.faction_id) + '"' + sel + '>' + _esc(f.name || f.faction_id) + '</option>';
        });
        return '<label class="ab-label">Faction<select id="' + id + '" class="ab-select">' + opts + '</select></label>';
    }

    function _locationSelect(id, current) {
        var opts = '<option value="">\u2014 None \u2014</option>';
        setup.locations.forEach(function (l) {
            var sel = (l.location_id && l.location_id === current) ? ' selected' : '';
            opts += '<option value="' + _esc(l.location_id) + '"' + sel + '>' + _esc(l.name || l.location_id) + '</option>';
        });
        return '<label class="ab-label">Location<select id="' + id + '" class="ab-select">' + opts + '</select></label>';
    }

    // ── Step 4: Start State ──

    function _renderStep4(body) {
        var locOpts = '<option value="">\u2014 Auto (first location) \u2014</option>';
        setup.locations.forEach(function (l) {
            var sel = (l.location_id === setup.starting_location_id) ? ' selected' : '';
            locOpts += '<option value="' + _esc(l.location_id) + '"' + sel + '>' + _esc(l.name || l.location_id) + '</option>';
        });

        var npcChecks = '';
        if (!setup.npc_seeds.length) {
            npcChecks = '<p class="ab-muted">Add NPCs in the World Seeds step first.</p>';
        } else {
            setup.npc_seeds.forEach(function (npc) {
                var checked = (setup.starting_npc_ids || []).indexOf(npc.npc_id) >= 0 ? ' checked' : '';
                npcChecks += '<label class="ab-checkbox-label"><input type="checkbox" class="ab-starting-npc" value="' + _esc(npc.npc_id) + '"' + checked + '> ' + _esc(npc.name || npc.npc_id) + '</label>';
            });
        }

        var pacing = setup.pacing || {};
        var pacingStyles = ['', 'balanced', 'slow_burn', 'fast', 'relentless'];
        var dangerLevels = ['', 'low', 'medium', 'high'];

        var html = '<div class="ab-section">' +
            '<h4>Starting Location</h4>' +
            '<select id="abStartLocation" class="ab-select ab-full-width">' + locOpts + '</select>' +
            '</div>' +
            '<div class="ab-section">' +
            '<h4>Starting NPCs</h4>' +
            '<p class="ab-hint">NPCs present at the opening scene.</p>' +
            '<div id="abStartNpcs">' + npcChecks + '</div>' +
            '</div>' +
            '<div class="ab-section">' +
            '<h4>Pacing Profile</h4>' +
            _selectField('Style', 'abPacingStyle', pacing.style, pacingStyles) +
            _selectField('Danger Level', 'abPacingDanger', pacing.danger_level, dangerLevels) +
            '</div>';
        body.innerHTML = html;
        _attachBlurValidation(body);
    }

    // ── Step 5: Review / Preview ──

    function _renderStep5(body) {
        _readCurrentStepIntoSetup();
        var html = '<div class="ab-section">' +
            '<h4>Setup Summary</h4>' +
            '<div id="abReviewSummary" class="ab-review-block"></div>' +
            '</div>' +
            '<div class="ab-section">' +
            '<h4>Targeted Regeneration</h4>' +
            '<p class="ab-hint">Replace individual sections without losing your other work.</p>' +
            '<div class="ab-inline-actions">' +
                '<button id="abRegenOpening" class="ab-btn ab-btn-secondary ab-btn-sm">♻ Regenerate Opening</button>' +
                '<button id="abRegenThreads" class="ab-btn ab-btn-secondary ab-btn-sm">♻ Regenerate Tensions</button>' +
            '</div>' +
            '</div>' +
            '<div class="ab-section">' +
            '<h4>Validation</h4>' +
            '<div id="abReviewValidation" class="ab-review-block"></div>' +
            '</div>' +
            '<div class="ab-section">' +
            '<h4>Preview</h4>' +
            '<div id="abReviewPreview" class="ab-review-block"><p class="ab-muted">Loading preview\u2026</p></div>' +
            '</div>';
        body.innerHTML = html;

        var sumEl = body.querySelector('#abReviewSummary');
        sumEl.innerHTML = _buildReviewSummary();

        _renderReviewValidation();

        _runPreview();

        // Regeneration button bindings for Step 5
        var regenOpeningBtn = body.querySelector('#abRegenOpening');
        if (regenOpeningBtn) regenOpeningBtn.addEventListener('click', function () { _handleRegenerate('opening'); });

        var regenThreadsBtn = body.querySelector('#abRegenThreads');
        if (regenThreadsBtn) regenThreadsBtn.addEventListener('click', function () { _handleRegenerate('threads'); });
    }

    function _buildReviewSummary() {
        var s = setup;
        var lines = [];
        lines.push('<div class="ab-review-group"><strong>Basics</strong>');
        lines.push('<div>' + _esc(s.title || '(no title)') + ' \u2014 ' + _esc(s.genre || '(no genre)') + '</div>');
        lines.push('<div>' + _esc(s.setting || '(no setting)') + '</div>');
        lines.push('<div><em>' + _esc(s.premise || '(no premise)') + '</em></div>');
        if (s.mood) lines.push('<div>Mood: ' + _esc(s.mood) + '</div>');
        if (s.difficulty_style) lines.push('<div>Difficulty: ' + _esc(s.difficulty_style) + '</div>');
        lines.push('</div>');

        lines.push('<div class="ab-review-group"><strong>Rules</strong>');
        lines.push('<div>Hard rules: ' + (s.hard_rules || []).length + '</div>');
        lines.push('<div>Tone rules: ' + (s.soft_tone_rules || []).length + '</div>');
        lines.push('<div>Forbidden: ' + (s.forbidden_content || []).length + '</div>');
        lines.push('<div>Canon notes: ' + (s.canon_notes || []).length + '</div>');
        lines.push('</div>');

        lines.push('<div class="ab-review-group"><strong>World Seeds</strong>');
        lines.push('<div>Factions: ' + (s.factions || []).length + '</div>');
        lines.push('<div>Locations: ' + (s.locations || []).length + '</div>');
        lines.push('<div>NPCs: ' + (s.npc_seeds || []).length + '</div>');
        lines.push('</div>');

        lines.push('<div class="ab-review-group"><strong>Start State</strong>');
        var startLoc = s.starting_location_id || '(auto)';
        var locName = startLoc;
        (s.locations || []).forEach(function (l) { if (l.location_id === startLoc) locName = l.name; });
        lines.push('<div>Opening in: ' + _esc(locName) + '</div>');
        var startNames = [];
        var npcMap = {};
        (s.npc_seeds || []).forEach(function (n) { npcMap[n.npc_id] = n.name; });
        (s.starting_npc_ids || []).forEach(function (id) { startNames.push(npcMap[id] || id); });
        lines.push('<div>Present: ' + (startNames.length ? _esc(startNames.join(', ')) : '(auto)') + '</div>');
        lines.push('</div>');

        return lines.join('');
    }

    function _renderReviewValidation() {
        var el = overlayEl.querySelector('#abReviewValidation');
        if (!el) return;
        var v = state.validation;
        if (!v || !v.issues || !v.issues.length) {
            el.innerHTML = '<p class="ab-success">\u2705 No issues found</p>';
            return;
        }
        var html = '';
        v.issues.forEach(function (issue) {
            var cls = 'ab-issue-' + (issue.severity || 'error');
            var icon = issue.severity === 'warning' ? '\u26A0\uFE0F' : issue.severity === 'info' ? '\u2139\uFE0F' : '\u274C';
            html += '<div class="ab-issue ' + cls + '">' + icon + ' <strong>' + _esc(issue.path) + '</strong>: ' + _esc(issue.message) + '</div>';
        });
        if (v.blocking) {
            html += '<p class="ab-error-note">\u26D4 Blocking issues must be fixed before launching.</p>';
        }
        el.innerHTML = html;
    }

    function _renderPreviewPanel() {
        var el = overlayEl ? overlayEl.querySelector('#abReviewPreview') : null;
        if (!el) return;
        var pr = state.preview;
        if (!pr) { el.innerHTML = '<p class="ab-muted">No preview available.</p>'; return; }

        var html = '';
        if (pr.ok === false) {
            html = '<p class="ab-muted">Preview unavailable \u2014 fix validation issues first.</p>';
        } else {
            var preview = pr.preview || {};
            var ctx = pr.resolved_context || {};
            html += '<div class="ab-preview-item"><strong>Title:</strong> ' + _esc(preview.title || '') + '</div>';
            html += '<div class="ab-preview-item"><strong>Genre:</strong> ' + _esc(preview.genre || '') + '</div>';
            html += '<div class="ab-preview-item"><strong>Setting:</strong> ' + _esc(preview.setting || '') + '</div>';
            html += '<div class="ab-preview-item"><strong>Premise:</strong> ' + _esc(preview.premise || '') + '</div>';
            if (preview.counts) {
                html += '<div class="ab-preview-item"><strong>Counts:</strong> ' +
                    'Factions: ' + (preview.counts.factions || 0) +
                    ', Locations: ' + (preview.counts.locations || 0) +
                    ', NPCs: ' + (preview.counts.npc_seeds || 0) + '</div>';
            }
            if (ctx.location_name) {
                html += '<div class="ab-preview-item ab-preview-highlight">\uD83D\uDCCD Opening in: <strong>' + _esc(ctx.location_name) + '</strong></div>';
            }
            if (ctx.npc_names && ctx.npc_names.length) {
                html += '<div class="ab-preview-item ab-preview-highlight">\uD83D\uDC64 Present: <strong>' + _esc(ctx.npc_names.join(', ')) + '</strong></div>';
            }
        }
        var pVal = pr.validation;
        if (pVal && pVal.issues && pVal.issues.length) {
            html += '<div class="ab-preview-warnings">';
            pVal.issues.forEach(function (issue) {
                if (issue.severity === 'warning' || issue.severity === 'info') {
                    html += '<div class="ab-issue ab-issue-' + issue.severity + '">' + _esc(issue.message) + '</div>';
                }
            });
            html += '</div>';
        }
        el.innerHTML = html;
    }

    // ── Inline validation ──

    function _renderInlineIssues() {
        if (!overlayEl) return;
        var v = state.validation;
        if (!v) return;
        overlayEl.querySelectorAll('.ab-inline-issue').forEach(function (el) { el.remove(); });
        if (!v.issues) return;
        v.issues.forEach(function (issue) {
            var fieldId = _issuePathToFieldId(issue.path);
            if (!fieldId) return;
            var fieldEl = overlayEl.querySelector('#' + fieldId);
            if (!fieldEl) return;
            var parent = fieldEl.closest('.ab-label') || fieldEl.parentElement;
            if (!parent) return;
            var existing = parent.querySelector('.ab-inline-issue');
            if (existing) return;
            var span = document.createElement('span');
            span.className = 'ab-inline-issue ab-issue-' + (issue.severity || 'error');
            span.textContent = issue.message;
            parent.appendChild(span);
        });
        if (currentStep === 5) _renderReviewValidation();
    }

    function _issuePathToFieldId(path) {
        var map = {
            'title': 'abTitle',
            'genre': 'abGenre',
            'setting': 'abSetting',
            'premise': 'abPremise',
            'starting_location_id': 'abStartLocation',
        };
        if (map[path]) return map[path];
        return null;
    }

    function _attachBlurValidation(container) {
        container.querySelectorAll('input, textarea, select').forEach(function (el) {
            el.addEventListener('blur', _scheduleValidation);
            el.addEventListener('input', _scheduleValidation);
        });
    }

    // ── Read step fields into setup ──

    function _readCurrentStepIntoSetup() {
        if (!overlayEl) return;
        switch (currentStep) {
            case 1: _readStep1(); break;
            case 2: _readStep2(); break;
            case 3: _readStep3(); break;
            case 4: _readStep4(); break;
        }
    }

    function _readStep1() {
        setup.title = _val('abTitle');
        setup.genre = _val('abGenre');
        setup.setting = _val('abSetting');
        setup.premise = _val('abPremise');
        setup.difficulty_style = _val('abDifficulty') || null;
        setup.mood = _val('abMood') || null;
        if (!setup.metadata) setup.metadata = {};
        setup.metadata.player_name = _val('abPlayerName') || 'Player';
        if (!setup.setup_id) setup.setup_id = 'adventure_' + Date.now().toString(36) + '_' + Math.random().toString(36).substring(2, 6);
    }

    function _readStep2() {
        setup.hard_rules = _readChips('abHardRules');
        setup.soft_tone_rules = _readChips('abToneRules');
        setup.forbidden_content = _readChips('abForbidden');
        setup.canon_notes = _readChips('abCanonNotes');
    }

    function _readStep3() {
        setup.factions.forEach(function (f, i) {
            f.name = _val('abFactionName' + i) || f.name;
            f.faction_id = _val('abFactionId' + i) || f.faction_id;
            f.description = _val('abFactionDesc' + i) || f.description;
            f.goals = _readChips('abFactionGoals' + i);
        });
        setup.locations.forEach(function (l, i) {
            l.name = _val('abLocationName' + i) || l.name;
            l.location_id = _val('abLocationId' + i) || l.location_id;
            l.description = _val('abLocationDesc' + i) || l.description;
            l.tags = _readChips('abLocationTags' + i);
        });
        setup.npc_seeds.forEach(function (npc, i) {
            npc.name = _val('abNpcName' + i) || npc.name;
            npc.npc_id = _val('abNpcId' + i) || npc.npc_id;
            npc.role = _val('abNpcRole' + i) || npc.role;
            npc.description = _val('abNpcDesc' + i) || npc.description;
            var facSel = overlayEl.querySelector('#abNpcFaction' + i);
            if (facSel) npc.faction_id = facSel.value || '';
            var locSel = overlayEl.querySelector('#abNpcLocation' + i);
            if (locSel) npc.location_id = locSel.value || '';
            var surviveEl = overlayEl.querySelector('#abNpcSurvive' + i);
            if (surviveEl) npc.must_survive = surviveEl.checked;
            npc.goals = _readChips('abNpcGoals' + i);
        });
    }

    function _readStep4() {
        var loc = overlayEl.querySelector('#abStartLocation');
        setup.starting_location_id = loc ? (loc.value || null) : setup.starting_location_id;
        var npcIds = [];
        overlayEl.querySelectorAll('.ab-starting-npc:checked').forEach(function (cb) {
            npcIds.push(cb.value);
        });
        setup.starting_npc_ids = npcIds;
        var pacingStyle = _val('abPacingStyle');
        var pacingDanger = _val('abPacingDanger');
        if (pacingStyle || pacingDanger) {
            if (!setup.pacing) setup.pacing = {};
            if (pacingStyle) setup.pacing.style = pacingStyle;
            if (pacingDanger) setup.pacing.danger_level = pacingDanger;
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Regeneration controller
    // ─────────────────────────────────────────────────────────────────────────

    var REGEN_TARGETS = [
        ['abRegenFactions', 'factions'],
        ['abRegenLocations', 'locations'],
        ['abRegenNpcs', 'npc_seeds'],
        ['abRegenOpening', 'opening'],
        ['abRegenThreads', 'threads']
    ];

    var REGEN_LABELS = {
        factions: '\u267B Regenerate Factions',
        locations: '\u267B Regenerate Locations',
        npc_seeds: '\u267B Regenerate NPCs',
        opening: '\u267B Regenerate Opening',
        threads: '\u267B Regenerate Tensions'
    };

    function _handleRegenerate(target) {
        _readCurrentStepIntoSetup();
        _markDirty();

        state.regenerating = target;
        _setRegenerationButtonsDisabled(true, target);

        AdventureBuilderApi.regenerateSection(target, state.setup).then(function (res) {
            if (!res || !res.success) {
                alert((res && res.error) || 'Regeneration failed.');
                return;
            }

            if (res.updated_setup) {
                state.setup = res.updated_setup;
                setup = state.setup;
            }
            state.validation = res.validation || null;
            state.preview = {
                ok: true,
                preview: res.preview || null,
                validation: res.validation || null,
                resolved_context: res.resolved_context || null
            };

            _saveDraft();
            _renderStep();
            _runValidation();
        }).catch(function () {
            alert('Regeneration failed.');
        }).finally(function () {
            state.regenerating = null;
            _setRegenerationButtonsDisabled(false, null);
        });
    }

    function _setRegenerationButtonsDisabled(disabled, activeTarget) {
        if (!overlayEl) return;
        REGEN_TARGETS.forEach(function (pair) {
            var btn = overlayEl.querySelector('#' + pair[0]);
            if (!btn) return;
            btn.disabled = !!disabled;
            if (disabled && pair[1] === activeTarget) {
                btn.textContent = '\u23F3 Regenerating\u2026';
            } else {
                btn.textContent = REGEN_LABELS[pair[1]];
            }
        });
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Event binding
    // ─────────────────────────────────────────────────────────────────────────

    function _handleLaunch() {
        _readCurrentStepIntoSetup();
        _saveDraft();
        var btn = overlayEl.querySelector('#abLaunch');
        if (btn) { btn.disabled = true; btn.textContent = '\u23F3 Launching\u2026'; }

        AdventureBuilderApi.startAdventure(setup).then(function (res) {
            if (res.success) {
                _clearDraft();
                close();
                if (typeof window._onAdventureBuilderLaunch === 'function') {
                    window._onAdventureBuilderLaunch(res);
                }
            } else {
                alert('Failed to launch: ' + (res.error || 'Unknown error'));
                if (btn) { btn.disabled = false; btn.textContent = '\u2694\uFE0F Launch Adventure'; }
            }
        }).catch(function (err) {
            alert('Launch error: ' + err.message);
            if (btn) { btn.disabled = false; btn.textContent = '\u2694\uFE0F Launch Adventure'; }
        });
    }

    // ─────────────────────────────────────────────────────────────────────────
    // HTML helpers
    // ─────────────────────────────────────────────────────────────────────────

    function _slug(text, prefix) {
        var s = text.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '').substring(0, 40);
        return (prefix || '') + s;
    }

    function _field(label, id, type, value, placeholder) {
        return '<label class="ab-label">' + _esc(label) +
            '<input type="' + type + '" id="' + id + '" class="ab-input" value="' + _esc(value || '') + '" placeholder="' + _esc(placeholder || '') + '">' +
            '</label>';
    }

    function _textareaField(label, id, value, placeholder, rows) {
        return '<label class="ab-label">' + _esc(label) +
            '<textarea id="' + id + '" class="ab-textarea" rows="' + (rows || 3) + '" placeholder="' + _esc(placeholder || '') + '">' + _esc(value || '') + '</textarea>' +
            '</label>';
    }

    function _selectField(label, id, current, options) {
        var opts = '';
        options.forEach(function (o) {
            var sel = (o === current) ? ' selected' : '';
            var display = o || '\u2014 Select \u2014';
            opts += '<option value="' + _esc(o) + '"' + sel + '>' + _esc(display) + '</option>';
        });
        return '<label class="ab-label">' + _esc(label) +
            '<select id="' + id + '" class="ab-select">' + opts + '</select>' +
            '</label>';
    }

    // ── Chip editor ──

    function _chipEditor(id, items, placeholder) {
        var html = '<div class="ab-chip-editor" id="' + id + '">';
        html += '<div class="ab-chip-list">';
        (items || []).forEach(function (item, i) {
            html += '<span class="ab-chip">' + _esc(item) + '<button class="ab-chip-del" data-idx="' + i + '">&times;</button></span>';
        });
        html += '</div>';
        html += '<div class="ab-chip-input-row"><input type="text" class="ab-chip-input" placeholder="' + _esc(placeholder || 'Add item\u2026') + '"><button class="ab-chip-add">+</button></div>';
        html += '</div>';
        return html;
    }

    function _attachChipEditors(container) {
        container.querySelectorAll('.ab-chip-editor').forEach(function (editor) {
            var addBtn = editor.querySelector('.ab-chip-add');
            var input = editor.querySelector('.ab-chip-input');
            addBtn.addEventListener('click', function () {
                var val = input.value.trim();
                if (!val) return;
                _addChipToEditor(editor, val);
                input.value = '';
                _scheduleValidation();
            });
            input.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    addBtn.click();
                }
            });
            editor.querySelectorAll('.ab-chip-del').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    btn.closest('.ab-chip').remove();
                    _scheduleValidation();
                });
            });
        });
    }

    function _addChipToEditor(editor, text) {
        var list = editor.querySelector('.ab-chip-list');
        var idx = list.querySelectorAll('.ab-chip').length;
        var chip = document.createElement('span');
        chip.className = 'ab-chip';
        chip.innerHTML = _esc(text) + '<button class="ab-chip-del" data-idx="' + idx + '">&times;</button>';
        chip.querySelector('.ab-chip-del').addEventListener('click', function () {
            chip.remove();
            _scheduleValidation();
        });
        list.appendChild(chip);
    }

    function _readChips(editorId) {
        var editor = overlayEl ? overlayEl.querySelector('#' + editorId) : null;
        if (!editor) return [];
        var chips = [];
        editor.querySelectorAll('.ab-chip').forEach(function (chip) {
            var delBtn = chip.querySelector('.ab-chip-del');
            var text = chip.textContent.replace(delBtn ? delBtn.textContent : '', '').trim();
            if (text) chips.push(text);
        });
        return chips;
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Public API
    // ─────────────────────────────────────────────────────────────────────────

    return {
        open: open,
        close: close,
    };
})();