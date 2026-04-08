/**
 * Adventure Builder — 7-Step Wizard
 *
 * Phase 1.2 modularization:
 * - state persistence/defaults moved to AdventureBuilderState
 * - shared shell/summary rendering moved to AdventureBuilderRenderer
 * - step-specific control flow stays here
 */
/* global AdventureBuilderApi, AdventureBuilderState, AdventureBuilderRenderer, AdventureBuilderWorldGraph */

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

    var STEP_COUNT = 7;
    var DEBOUNCE_MS = 400;
    var MAX_SNAPSHOTS = 20;

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
        // Phase 2 — invalidate world inspection cache on setup changes
        if (state.worldInspection) {
            if (state.worldInspection.graph) {
                state.worldInspection.previousGraph = state.worldInspection.graph;
            }
            state.worldInspection.graph = null;
            state.worldInspection.simulation = null;
            state.worldInspection.inspector = null;
            state.worldInspection.graphDiff = null;
        }
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
            if (currentStep === 7) _runPreview();
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
            if (currentStep === 7) _renderPreviewPanel();
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
        if (currentStep === 7) {
            _runValidation();
            _runPreview();
            // Phase 2 — pre-fetch world inspection data
            _fetchWorldInspection(null);
        }
    }

    function _renderStep() {
        _renderProgress();
        var body = overlayEl.querySelector('#abBody');
        body.innerHTML = '';
        switch (currentStep) {
            case 1: _renderStep1(body); break;
            case 2: _renderStep2_PlayerCampaign(body); break;
            case 3: _renderStep3_Rules(body); break;
            case 4: _renderStep4_World(body); break;
            case 5: _renderStep5_Opening(body); break;
            case 6: _renderStep6_Generated(body); break;
            case 7: _renderStep7_Review(body); break;
        }
        _renderFooter();
    }

    function _renderProgress() {
        var labels = ['Basics', 'Player & Campaign', 'Rules', 'World', 'Opening', 'Generated World', 'Review'];
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

    // ── Step 2: Player & Campaign (Phase A) ──

    function _renderStep2_PlayerCampaign(body) {
        var mix = setup.desired_content_mix || {};
        var mixKeys = ['combat', 'exploration', 'intrigue', 'mystery', 'survival', 'romance', 'humor'];

        var quickFills = [
            { label: 'Suggest from genre', key: 'genre' },
            { label: 'Balanced', key: 'balanced' },
            { label: 'Combat-heavy', key: 'combat' },
            { label: 'Narrative-heavy', key: 'narrative' },
            { label: 'Mystery-heavy', key: 'mystery' },
            { label: 'Survival-heavy', key: 'survival' }
        ];

        var html = '<div class="ab-section">' +
            '<h4>\uD83C\uDFAD Player Fantasy</h4>' +
            _field('Role', 'abPlayerRole', 'text', setup.player_role, 'e.g. Wandering knight, Spy, Merchant\u2026') +
            _field('Archetype', 'abPlayerArchetype', 'text', setup.player_archetype, 'e.g. Reluctant hero, Cunning rogue\u2026') +
            _field('Background', 'abPlayerBackground', 'text', setup.player_background, 'e.g. Exiled noble, Street orphan\u2026') +
            '</div>' +
            '<div class="ab-section">' +
            '<h4>\uD83C\uDFAF Campaign Intent</h4>' +
            _textareaField('Campaign Objective', 'abCampaignObjective', setup.campaign_objective, 'What is the overarching goal?', 3) +
            _textareaField('Opening Hook', 'abOpeningHook', setup.opening_hook, 'What draws the player in?', 2) +
            _textareaField('Starter Conflict', 'abStarterConflict', setup.starter_conflict, 'The initial tension or problem', 2) +
            '</div>' +
            '<div class="ab-section">' +
            '<h4>\uD83D\uDCDC World Rules</h4>' +
            '<p class="ab-hint">Laws that govern your world.</p>' +
            _chipEditor('abCoreWorldLaws', setup.core_world_laws || [], 'e.g. Magic requires sacrifice') +
            '<p class="ab-hint">Genre-specific rules.</p>' +
            _chipEditor('abGenreRules', setup.genre_rules || [], 'e.g. No resurrection magic') +
            '</div>' +
            '<div class="ab-section">' +
            '<h4>\uD83C\uDFB2 Play Mix</h4>' +
            '<p class="ab-hint">Adjust desired content balance (sliders auto-normalize).</p>';

        mixKeys.forEach(function (k) {
            var val = mix[k] != null ? mix[k] : 0;
            html += '<label class="ab-label ab-slider-label">' + _esc(k.charAt(0).toUpperCase() + k.slice(1)) +
                ' <span class="ab-slider-val" id="abMixVal_' + k + '">' + Math.round(val * 100) + '%</span>' +
                '<input type="range" id="abMix_' + k + '" class="ab-slider" min="0" max="1" step="0.05" value="' + val + '">' +
                '</label>';
        });

        html += '<div class="ab-quick-fill">';
        quickFills.forEach(function (qf) {
            html += '<button class="ab-btn ab-btn-secondary ab-btn-sm ab-qf-btn" data-qf="' + _esc(qf.key) + '">' + _esc(qf.label) + '</button>';
        });
        html += '</div></div>';

        // Starting gear
        var gear = setup.starting_gear || [];
        html += '<div class="ab-section">' +
            '<h4>\uD83C\uDFF9 Starting Kit</h4>' +
            '<p class="ab-hint">Gear the player starts with.</p>' +
            '<div id="abGearList">';
        gear.forEach(function (g, i) {
            var gObj = typeof g === 'string' ? { name: g, description: '' } : g;
            html += '<div class="ab-gear-row">' +
                '<input type="text" class="ab-input ab-gear-name" value="' + _esc(gObj.name || '') + '" placeholder="Item name">' +
                '<input type="text" class="ab-input ab-gear-desc" value="' + _esc(gObj.description || '') + '" placeholder="Description (optional)">' +
                '<button class="ab-btn ab-btn-sm ab-gear-del" data-idx="' + i + '">\uD83D\uDDD1\uFE0F</button>' +
                '</div>';
        });
        html += '</div>' +
            '<button class="ab-btn ab-btn-add" id="abAddGear">+ Add Gear</button>' +
            '</div>';

        // Starting resources
        var res = setup.starting_resources || {};
        html += '<div class="ab-section">' +
            '<h4>\uD83D\uDCB0 Starting Resources</h4>' +
            '<div class="ab-resource-grid">' +
            _field('Gold', 'abRes_gold', 'number', res.gold || 0, '0') +
            _field('Supplies', 'abRes_supplies', 'number', res.supplies || 0, '0') +
            _field('Ammo', 'abRes_ammo', 'number', res.ammo || 0, '0') +
            _field('Rations', 'abRes_rations', 'number', res.rations || 0, '0') +
            '</div></div>';

        body.innerHTML = html;
        _attachChipEditors(body);
        _attachBlurValidation(body);

        // Slider live update
        mixKeys.forEach(function (k) {
            var slider = body.querySelector('#abMix_' + k);
            var valSpan = body.querySelector('#abMixVal_' + k);
            if (slider && valSpan) {
                slider.addEventListener('input', function () {
                    valSpan.textContent = Math.round(parseFloat(slider.value) * 100) + '%';
                });
            }
        });

        // Quick fill buttons
        var QF_PRESETS = {
            balanced: { combat: 0.20, exploration: 0.20, intrigue: 0.15, mystery: 0.15, survival: 0.10, romance: 0.10, humor: 0.10 },
            combat: { combat: 0.50, exploration: 0.15, intrigue: 0.10, mystery: 0.05, survival: 0.10, romance: 0.02, humor: 0.08 },
            narrative: { combat: 0.05, exploration: 0.15, intrigue: 0.30, mystery: 0.15, survival: 0.02, romance: 0.20, humor: 0.13 },
            mystery: { combat: 0.05, exploration: 0.20, intrigue: 0.20, mystery: 0.40, survival: 0.05, romance: 0.05, humor: 0.05 },
            survival: { combat: 0.20, exploration: 0.25, intrigue: 0.05, mystery: 0.10, survival: 0.35, romance: 0.00, humor: 0.05 },
            genre: { combat: 0.25, exploration: 0.25, intrigue: 0.20, mystery: 0.15, survival: 0.05, romance: 0.05, humor: 0.05 }
        };
        body.querySelectorAll('.ab-qf-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var preset = QF_PRESETS[btn.getAttribute('data-qf')] || QF_PRESETS.balanced;
                mixKeys.forEach(function (k) {
                    var slider = body.querySelector('#abMix_' + k);
                    var valSpan = body.querySelector('#abMixVal_' + k);
                    if (slider) {
                        slider.value = preset[k] || 0;
                        if (valSpan) valSpan.textContent = Math.round((preset[k] || 0) * 100) + '%';
                    }
                });
            });
        });

        // Gear add/delete
        var addGearBtn = body.querySelector('#abAddGear');
        if (addGearBtn) addGearBtn.addEventListener('click', function () {
            if (!setup.starting_gear) setup.starting_gear = [];
            setup.starting_gear.push({ name: '', description: '' });
            _readStep2_PlayerCampaign();
            _markDirty();
            _renderStep2_PlayerCampaign(body);
        });
        body.querySelectorAll('.ab-gear-del').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var idx = parseInt(btn.getAttribute('data-idx'), 10);
                _readStep2_PlayerCampaign();
                setup.starting_gear.splice(idx, 1);
                _markDirty();
                _renderStep2_PlayerCampaign(body);
            });
        });
    }

    // ── Step 3: Rules / Tone ──

    function _renderStep3_Rules(body) {
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

    // ── Step 4: World Seeds ──

    function _renderStep4_World(body) {
        var factionSelCount = _selectionCount('factions');
        var locationSelCount = _selectionCount('locations');
        var npcSelCount = _selectionCount('npc_seeds');
        var clearDisabled = state.selection.items.length ? '' : ' disabled';
        var undoDisabled = AdventureBuilderState.hasHistory(state) ? '' : ' disabled';
        var html = '<div class="ab-section">' +
            '<h4>Factions</h4>' +
            '<div class="ab-inline-actions">' +
                '<button id="abRegenFactions" class="ab-btn ab-btn-secondary ab-btn-sm">♻ Regenerate Factions</button>' +
                '<button id="abBulkRegenFactions" class="ab-btn ab-btn-secondary ab-btn-sm">\uD83D\uDD04 Bulk Regenerate Selected</button>' +
                '<span class="ab-selection-count">' + factionSelCount + ' selected</span>' +
            '</div>' +
            '<div id="abFactionList"></div>' +
            '<button class="ab-btn ab-btn-add" id="abAddFaction">+ Add Faction</button>' +
            '</div>' +
            '<div class="ab-section">' +
            '<h4>Locations</h4>' +
            '<div class="ab-inline-actions">' +
                '<button id="abRegenLocations" class="ab-btn ab-btn-secondary ab-btn-sm">♻ Regenerate Locations</button>' +
                '<button id="abBulkRegenLocations" class="ab-btn ab-btn-secondary ab-btn-sm">\uD83D\uDD04 Bulk Regenerate Selected</button>' +
                '<span class="ab-selection-count">' + locationSelCount + ' selected</span>' +
            '</div>' +
            '<div id="abLocationList"></div>' +
            '<button class="ab-btn ab-btn-add" id="abAddLocation">+ Add Location</button>' +
            '</div>' +
            '<div class="ab-section">' +
            '<h4>NPCs</h4>' +
            '<div class="ab-inline-actions">' +
                '<button id="abRegenNpcs" class="ab-btn ab-btn-secondary ab-btn-sm">♻ Regenerate NPCs</button>' +
                '<button id="abBulkRegenNpcs" class="ab-btn ab-btn-secondary ab-btn-sm">\uD83D\uDD04 Bulk Regenerate Selected</button>' +
                '<span class="ab-selection-count">' + npcSelCount + ' selected</span>' +
            '</div>' +
            '<div id="abNpcList"></div>' +
            '<button class="ab-btn ab-btn-add" id="abAddNpc">+ Add NPC</button>' +
            '</div>' +
            '<div class="ab-section ab-undo-section">' +
            '<button id="abClearSelection" class="ab-btn ab-btn-secondary ab-btn-sm"' + clearDisabled + '>\u2715 Clear Selection</button>' +
            '<button id="abUndoRegen" class="ab-btn ab-btn-secondary ab-btn-sm"' + undoDisabled + '>\u21A9 Undo Last Regeneration</button>' +
            '</div>';

        // Phase 1.5 — Tone & constraints panels
        body.innerHTML = html;
        _renderToneSelector(body);
        _renderConstraints(body);

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

        // Undo button binding for Step 3
        var undoBtn = body.querySelector('#abUndoRegen');
        if (undoBtn) undoBtn.addEventListener('click', function () { _handleUndo(); });

        // Phase 1.5 — Bulk regeneration button bindings
        var bulkFBtn = body.querySelector('#abBulkRegenFactions');
        if (bulkFBtn) bulkFBtn.addEventListener('click', function () { _handleBulkRegenerate('factions'); });
        var bulkLBtn = body.querySelector('#abBulkRegenLocations');
        if (bulkLBtn) bulkLBtn.addEventListener('click', function () { _handleBulkRegenerate('locations'); });
        var bulkNBtn = body.querySelector('#abBulkRegenNpcs');
        if (bulkNBtn) bulkNBtn.addEventListener('click', function () { _handleBulkRegenerate('npc_seeds'); });

        // Clear selection button binding
        var clearSelBtn = body.querySelector('#abClearSelection');
        if (clearSelBtn) clearSelBtn.addEventListener('click', function () {
            _clearSelection();
            _renderStep();
        });
    }

    // -- Faction cards

    function _renderFactionCards() {
        var list = overlayEl.querySelector('#abFactionList');
        if (!list) return;
        if (!setup.factions.length) { list.innerHTML = '<p class="ab-muted">No factions yet.</p>'; return; }
        var html = '';
        setup.factions.forEach(function (f, i) {
            var selChecked = (state.selection.activeTarget === 'factions' && state.selection.items.indexOf(f.faction_id || '') >= 0) ? ' checked' : '';
            html += '<div class="ab-entity-card" data-idx="' + i + '">' +
                '<div class="ab-entity-header">' +
                    '<input type="checkbox" class="ab-entity-select" data-type="factions" data-id="' + _esc(f.faction_id || '') + '"' + selChecked + '>' +
                    '<span class="ab-entity-summary">' + _esc(f.name || 'Unnamed Faction') + '</span>' +
                    '<button class="ab-entity-regen" data-type="factions" data-id="' + _esc(f.faction_id || '') + '" title="Regenerate this faction">\u267B</button>' +
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
        _attachEntityRegen(list);
        _attachEntitySelect(list);
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
            var selChecked = (state.selection.activeTarget === 'locations' && state.selection.items.indexOf(loc.location_id || '') >= 0) ? ' checked' : '';
            html += '<div class="ab-entity-card" data-idx="' + i + '">' +
                '<div class="ab-entity-header">' +
                    '<input type="checkbox" class="ab-entity-select" data-type="locations" data-id="' + _esc(loc.location_id || '') + '"' + selChecked + '>' +
                    '<span class="ab-entity-summary">' + _esc(loc.name || 'Unnamed Location') + '</span>' +
                    '<button class="ab-entity-regen" data-type="locations" data-id="' + _esc(loc.location_id || '') + '" title="Regenerate this location">\u267B</button>' +
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
        _attachEntityRegen(list);
        _attachEntitySelect(list);
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
            var selChecked = (state.selection.activeTarget === 'npc_seeds' && state.selection.items.indexOf(npc.npc_id || '') >= 0) ? ' checked' : '';
            html += '<div class="ab-entity-card" data-idx="' + i + '">' +
                '<div class="ab-entity-header">' +
                    '<input type="checkbox" class="ab-entity-select" data-type="npc_seeds" data-id="' + _esc(npc.npc_id || '') + '"' + selChecked + '>' +
                    '<span class="ab-entity-summary">' + _esc(npc.name || 'Unnamed NPC') + '</span>' +
                    '<button class="ab-entity-regen" data-type="npc_seeds" data-id="' + _esc(npc.npc_id || '') + '" title="Regenerate this NPC">\u267B</button>' +
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
        _attachEntityRegen(list);
        _attachEntitySelect(list);
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

    function _attachEntityRegen(container) {
        container.querySelectorAll('.ab-entity-regen').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var target = btn.getAttribute('data-type');
                var itemId = btn.getAttribute('data-id');
                if (target && itemId) {
                    _readCurrentStepIntoSetup();
                    _handleRegenerateItem(target, itemId);
                }
            });
        });
    }

    function _attachEntitySelect(container) {
        container.querySelectorAll('.ab-entity-select').forEach(function (cb) {
            cb.addEventListener('change', function () {
                var target = cb.getAttribute('data-type');
                var id = cb.getAttribute('data-id');
                if (target && id) {
                    _toggleSelection(target, id);
                    _renderStep();
                }
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

    // ── Step 5: Opening (Phase B) — merges old Step 4 + new opening fields ──

    function _renderStep5_Opening(body) {
        var opening = setup.opening || {};
        var locOpts = '<option value="">\u2014 Select Location \u2014</option>';
        setup.locations.forEach(function (l) {
            var sel = (l.location_id === opening.location_id) ? ' selected' : '';
            locOpts += '<option value="' + _esc(l.location_id) + '"' + sel + '>' + _esc(l.name || l.location_id) + '</option>';
        });

        var npcChecks = '';
        if (!setup.npc_seeds.length) {
            npcChecks = '<p class="ab-muted">Add NPCs in the World step first.</p>';
        } else {
            setup.npc_seeds.forEach(function (npc) {
                var checked = (opening.present_npc_ids || []).indexOf(npc.npc_id) >= 0 ? ' checked' : '';
                npcChecks += '<label class="ab-checkbox-label"><input type="checkbox" class="ab-opening-npc" value="' + _esc(npc.npc_id) + '"' + checked + '> ' + _esc(npc.name || npc.npc_id) + '</label>';
            });
        }

        var pacing = setup.pacing || {};
        var pacingStyles = ['', 'balanced', 'slow_burn', 'fast', 'relentless'];
        var dangerLevels = ['', 'low', 'medium', 'high'];
        var tensionLevels = ['low', 'medium', 'high', 'extreme'];
        var timeOptions = ['', 'dawn', 'morning', 'midday', 'afternoon', 'dusk', 'evening', 'night', 'midnight'];
        var weatherOptions = ['', 'clear', 'cloudy', 'rain', 'storm', 'snow', 'fog', 'wind'];

        var html = '<div class="ab-section">' +
            '<h4>\uD83C\uDF05 Opening Scene</h4>' +
            '<label class="ab-label">Where You Begin<select id="abOpeningLocation" class="ab-select ab-full-width">' + locOpts + '</select></label>' +
            _selectField('Time of Day', 'abOpeningTime', opening.time_of_day, timeOptions) +
            _selectField('Weather', 'abOpeningWeather', opening.weather, weatherOptions) +
            _selectField('Tension Level', 'abOpeningTension', opening.tension_level, tensionLevels) +
            '</div>' +
            '<div class="ab-section">' +
            '<h4>\uD83D\uDCDC What Is Happening</h4>' +
            _textareaField('Scene Frame', 'abSceneFrame', opening.scene_frame, 'Describe the opening scene...', 3) +
            _textareaField('Immediate Problem', 'abImmediateProblem', opening.immediate_problem, 'What urgent situation faces the player?', 3) +
            '</div>' +
            '<div class="ab-section">' +
            '<h4>\uD83E\uDDD1 Why Player Is Involved</h4>' +
            _textareaField('Involvement Reason', 'abInvolvementReason', opening.player_involvement_reason, 'Why is the player here and motivated to act?', 3) +
            '</div>' +
            '<div class="ab-section">' +
            '<h4>\uD83D\uDC64 Who Is Present</h4>' +
            '<p class="ab-hint">NPCs present at the opening scene.</p>' +
            '<div id="abOpeningNpcs">' + npcChecks + '</div>' +
            '</div>' +
            '<div class="ab-section">' +
            '<h4>\uD83C\uDFAF First Likely Choices</h4>' +
            '<p class="ab-hint">Suggested first actions for the player.</p>' +
            _chipEditor('abFirstChoices', opening.first_choices || [], 'e.g. Investigate the noise\u2026') +
            '<button class="ab-btn ab-btn-secondary ab-btn-sm" id="abSuggestChoices">\u2728 Suggest opening choices</button>' +
            '</div>' +
            '<div class="ab-section">' +
            '<h4>\u23F1\uFE0F Pacing Profile</h4>' +
            _selectField('Style', 'abPacingStyle', pacing.style, pacingStyles) +
            _selectField('Danger Level', 'abPacingDanger', pacing.danger_level, dangerLevels) +
            '</div>';
        body.innerHTML = html;
        _attachChipEditors(body);
        _attachBlurValidation(body);

        var suggestBtn = body.querySelector('#abSuggestChoices');
        if (suggestBtn) suggestBtn.addEventListener('click', function () {
            var defaults = ['Investigate the area', 'Talk to the nearest NPC', 'Look for clues'];
            var editor = overlayEl.querySelector('#abFirstChoices');
            if (editor) {
                defaults.forEach(function (d) { _addChipToEditor(editor, d); });
            }
        });
    }

    // ── Step 6: Generated World (Phase E) ──

    function _renderStep6_Generated(body) {
        var gp = setup.generated_package || {};
        var prefs = setup.generation_preferences || {};
        var creativityOptions = ['conservative', 'balanced', 'creative', 'wild'];

        var html = '<div class="ab-section">' +
            '<h4>\u2728 Generate World Details</h4>' +
            '<p class="ab-hint">Auto-generate characters, factions, locations, and lore to flesh out your world.</p>' +
            '<div class="ab-gen-prefs">' +
                _field('Characters', 'abGenCharCount', 'number', prefs.character_count || 5, '5') +
                _field('Locations', 'abGenLocCount', 'number', prefs.location_count || 4, '4') +
                _field('Factions', 'abGenFacCount', 'number', prefs.faction_count || 3, '3') +
                _field('Lore Entries', 'abGenLoreCount', 'number', prefs.lore_count || 6, '6') +
                _selectField('Creativity', 'abGenCreativity', prefs.creativity_profile || 'balanced', creativityOptions) +
            '</div>' +
            '<button class="ab-btn ab-btn-primary" id="abGenerateWorld">\uD83C\uDF0D Generate World Details</button>' +
            '</div>';

        // Status
        if (gp.status === 'generating') {
            html += '<div class="ab-section"><p class="ab-muted">\u23F3 Generating\u2026</p></div>';
        } else if (gp.status === 'done') {
            // Warnings
            if (gp.warnings && gp.warnings.length) {
                html += '<div class="ab-section"><h4>\u26A0\uFE0F Warnings</h4>';
                gp.warnings.forEach(function (w) { html += '<div class="ab-warning">' + _esc(w) + '</div>'; });
                html += '</div>';
            }
            // Sub-tabs
            html += '<div class="ab-section">' +
                '<div class="ab-gen-tabs" id="abGenTabs">' +
                    '<button class="ab-wg-tab ab-wg-tab-active" data-gtab="characters">\uD83D\uDC64 Characters</button>' +
                    '<button class="ab-wg-tab" data-gtab="factions">\u2694\uFE0F Factions</button>' +
                    '<button class="ab-wg-tab" data-gtab="locations">\uD83D\uDCCD Locations</button>' +
                    '<button class="ab-wg-tab" data-gtab="lore">\uD83D\uDCDC Lore</button>' +
                    '<button class="ab-wg-tab" data-gtab="opening">\uD83C\uDF05 Opening</button>' +
                '</div>' +
                '<div id="abGenContent"></div>' +
                '</div>';

            html += '<div class="ab-section">' +
                '<button class="ab-btn ab-btn-launch" id="abApplyGenerated">\u2705 Apply Generated Content</button>' +
                '</div>';
        }

        body.innerHTML = html;

        // Generate button
        var genBtn = body.querySelector('#abGenerateWorld');
        if (genBtn) genBtn.addEventListener('click', function () {
            _readCurrentStepIntoSetup();
            _markDirty();
            setup.generated_package.status = 'generating';
            _renderStep6_Generated(body);
            AdventureBuilderApi.generateWorld(setup, setup.generation_preferences).then(function (res) {
                if (res.generated_package) {
                    setup.generated_package = res.generated_package;
                    setup.generated_package.status = 'done';
                } else {
                    setup.generated_package.status = 'idle';
                }
                _markDirty();
                _renderStep6_Generated(body);
            }).catch(function () {
                setup.generated_package.status = 'idle';
                _renderStep6_Generated(body);
            });
        });

        // Apply button
        var applyBtn = body.querySelector('#abApplyGenerated');
        if (applyBtn) applyBtn.addEventListener('click', function () {
            _readCurrentStepIntoSetup();
            AdventureBuilderApi.applyGeneratedPackage(setup, setup.generated_package, setup.locked_generated_ids || []).then(function (res) {
                if (res.setup) {
                    Object.assign(setup, res.setup);
                    _markDirty();
                    _renderStep6_Generated(body);
                }
            }).catch(function () { /* ignore */ });
        });

        // Render generated content tabs
        if (gp.status === 'done') {
            _renderGenContentTab(body, 'characters');
            var tabBtns = body.querySelectorAll('[data-gtab]');
            tabBtns.forEach(function (btn) {
                btn.addEventListener('click', function () {
                    tabBtns.forEach(function (b) { b.classList.remove('ab-wg-tab-active'); });
                    btn.classList.add('ab-wg-tab-active');
                    _renderGenContentTab(body, btn.getAttribute('data-gtab'));
                });
            });
        }

        _attachBlurValidation(body);
    }

    function _renderGenContentTab(body, tab) {
        var container = body.querySelector('#abGenContent');
        if (!container) return;
        var gp = setup.generated_package || {};
        var locked = setup.locked_generated_ids || [];
        var html = '';

        var items = [];
        if (tab === 'characters') items = gp.characters || [];
        else if (tab === 'factions') items = gp.factions || [];
        else if (tab === 'locations') items = gp.locations || [];
        else if (tab === 'lore') items = gp.lore_entries || [];
        else if (tab === 'opening' && gp.opening_patch) {
            var op = gp.opening_patch;
            html += '<div class="ab-entity-card"><div class="ab-entity-header"><span class="ab-entity-summary">Opening Patch</span></div>' +
                '<div class="ab-entity-body">' +
                '<div><strong>Scene:</strong> ' + _esc(op.scene_frame || '') + '</div>' +
                '<div><strong>Problem:</strong> ' + _esc(op.immediate_problem || '') + '</div>' +
                '<div><strong>Involvement:</strong> ' + _esc(op.player_involvement_reason || '') + '</div>' +
                '</div></div>';
            container.innerHTML = html;
            return;
        }

        if (!items.length) {
            container.innerHTML = '<p class="ab-muted">No ' + tab + ' generated.</p>';
            return;
        }

        items.forEach(function (item, i) {
            var id = item.id || item.npc_id || item.faction_id || item.location_id || (tab + '_' + i);
            var isLocked = locked.indexOf(id) >= 0;
            html += '<div class="ab-entity-card" data-gen-type="' + _esc(tab) + '" data-gen-idx="' + i + '">' +
                '<div class="ab-entity-header">' +
                    '<span class="ab-entity-summary">' + _esc(item.name || item.title || 'Item ' + (i + 1)) + '</span>' +
                    '<button class="ab-gen-lock" data-id="' + _esc(id) + '" title="' + (isLocked ? 'Unlock' : 'Lock') + '">' + (isLocked ? '\uD83D\uDD12' : '\uD83D\uDD13') + '</button>' +
                    '<button class="ab-gen-regen" data-type="' + _esc(tab) + '" data-id="' + _esc(id) + '" title="Regenerate">\u267B</button>' +
                    '<button class="ab-gen-del" data-type="' + _esc(tab) + '" data-idx="' + i + '" title="Delete">\uD83D\uDDD1\uFE0F</button>' +
                '</div>' +
                '<div class="ab-entity-body">' +
                    '<div>' + _esc(item.description || item.content || '') + '</div>' +
                '</div>' +
            '</div>';
        });
        container.innerHTML = html;

        // Lock toggle
        container.querySelectorAll('.ab-gen-lock').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var id = btn.getAttribute('data-id');
                if (!setup.locked_generated_ids) setup.locked_generated_ids = [];
                var idx = setup.locked_generated_ids.indexOf(id);
                if (idx >= 0) setup.locked_generated_ids.splice(idx, 1);
                else setup.locked_generated_ids.push(id);
                _markDirty();
                _renderGenContentTab(body, tab);
            });
        });

        // Regenerate single entity
        container.querySelectorAll('.ab-gen-regen').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var type = btn.getAttribute('data-type');
                var id = btn.getAttribute('data-id');
                btn.disabled = true;
                btn.textContent = '\u23F3';
                AdventureBuilderApi.regenerateWorldEntity(setup, type, id).then(function (res) {
                    if (res.entity) {
                        var arr = type === 'lore' ? (setup.generated_package.lore_entries || []) : (setup.generated_package[type] || []);
                        for (var j = 0; j < arr.length; j++) {
                            var eid = arr[j].id || arr[j].npc_id || arr[j].faction_id || arr[j].location_id;
                            if (eid === id) { arr[j] = res.entity; break; }
                        }
                        _markDirty();
                    }
                    _renderGenContentTab(body, tab);
                }).catch(function () { _renderGenContentTab(body, tab); });
            });
        });

        // Delete entity
        container.querySelectorAll('.ab-gen-del').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var type = btn.getAttribute('data-type');
                var idx = parseInt(btn.getAttribute('data-idx'), 10);
                var arr = type === 'lore' ? setup.generated_package.lore_entries : setup.generated_package[type];
                if (arr) { arr.splice(idx, 1); _markDirty(); }
                _renderGenContentTab(body, tab);
            });
        });
    }

    // ── Step 7: Review / Preview ──

    function _renderStep7_Review(body) {
        _readCurrentStepIntoSetup();
        var undoDisabled = AdventureBuilderState.hasHistory(state) ? '' : ' disabled';

        // Phase 2.5 — Auto-capture initial snapshot on first Step 5 entry
        var wi = state.worldInspection || {};
        if (!wi.snapshots || !wi.snapshots.length) {
            _captureWorldSnapshot('Initial Draft');
        }

        // Phase 2 — Top-level tab strip for Step 5 sub-views
        var step5Tab = state.worldInspection ? (state.worldInspection.activeTab || 'summary') : 'summary';

        var html = '<div class="ab-step5-tabs" id="abStep5Tabs"></div>';
        html += '<div class="ab-step5-content" id="abStep5Content"></div>';
        body.innerHTML = html;

        _renderStep7Tabs(body, step5Tab);
        _renderStep7TabContent(body, step5Tab, undoDisabled);
    }

    function _renderStep7Tabs(body, activeTab) {
        var tabsEl = body.querySelector('#abStep5Tabs');
        if (!tabsEl) return;
        var tabs = [
            { id: 'summary', icon: '📋', label: 'Summary' },
            { id: 'validation', icon: '✅', label: 'Validation' },
            { id: 'preview', icon: '👁️', label: 'Preview' },
            { id: 'worldgraph', icon: '🕸️', label: 'World Graph' },
            { id: 'simulation', icon: '📊', label: 'Simulation' },
            { id: 'inspector', icon: '🔍', label: 'Inspector' },
            { id: 'timeline', icon: '🕰️', label: 'Timeline' },
            { id: 'diff', icon: '🔀', label: 'Diff' }
        ];
        var html = '<div class="ab-wg-tabs">';
        tabs.forEach(function (t) {
            var active = t.id === activeTab ? ' ab-wg-tab-active' : '';
            html += '<button class="ab-wg-tab' + active + '" data-tab="' + t.id + '">' + t.icon + ' ' + _esc(t.label) + '</button>';
        });
        html += '</div>';
        tabsEl.innerHTML = html;

        tabsEl.querySelectorAll('.ab-wg-tab').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var tab = btn.getAttribute('data-tab');
                if (!state.worldInspection) state.worldInspection = {};
                state.worldInspection.activeTab = tab;
                _renderStep7_Review(overlayEl.querySelector('#abBody'));
            });
        });
    }

    function _renderStep7TabContent(body, activeTab, undoDisabled) {
        var contentEl = body.querySelector('#abStep5Content');
        if (!contentEl) return;

        switch (activeTab) {
            case 'summary':
                _renderStep7Summary(contentEl, undoDisabled);
                break;
            case 'validation':
                _renderStep7Validation(contentEl);
                break;
            case 'preview':
                _renderStep7Preview(contentEl);
                break;
            case 'worldgraph':
                _renderStep7WorldGraph(contentEl);
                break;
            case 'simulation':
                _renderStep7Simulation(contentEl);
                break;
            case 'inspector':
                _renderStep7Inspector(contentEl);
                break;
            case 'timeline':
                _renderStep7Timeline(contentEl);
                break;
            case 'diff':
                _renderStep7Diff(contentEl);
                break;
            default:
                _renderStep7Summary(contentEl, undoDisabled);
        }
    }

    function _renderStep7Summary(contentEl, undoDisabled) {
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
                '<button id="abUndoRegen" class="ab-btn ab-btn-secondary ab-btn-sm"' + undoDisabled + '>\u21A9 Undo Last Regeneration</button>' +
            '</div>' +
            '</div>' +
            '<div class="ab-section">' +
            '<h4>Health Check</h4>' +
            '<div id="abHealthWarnings" class="ab-review-block"><p class="ab-muted">Analyzing setup\u2026</p></div>' +
            '</div>';
        contentEl.innerHTML = html;

        var sumEl = contentEl.querySelector('#abReviewSummary');
        sumEl.innerHTML = _buildReviewSummary();

        var healthEl = contentEl.querySelector('#abHealthWarnings');
        if (healthEl) {
            var healthHtml = _renderHealthWarnings({ health: _computeClientHealth() });
            healthEl.innerHTML = healthHtml || '<p class="ab-success">\u2705 Setup looks good!</p>';
        }

        // Regeneration button bindings
        var regenOpeningBtn = contentEl.querySelector('#abRegenOpening');
        if (regenOpeningBtn) regenOpeningBtn.addEventListener('click', function () { _handleRegenerate('opening'); });
        var regenThreadsBtn = contentEl.querySelector('#abRegenThreads');
        if (regenThreadsBtn) regenThreadsBtn.addEventListener('click', function () { _handleRegenerate('threads'); });
        var undoBtn = contentEl.querySelector('#abUndoRegen');
        if (undoBtn) undoBtn.addEventListener('click', function () { _handleUndo(); });
    }

    function _renderStep7Validation(contentEl) {
        var html = '<div class="ab-section">' +
            '<h4>Validation</h4>' +
            '<div id="abReviewValidation" class="ab-review-block"><p class="ab-muted">Loading\u2026</p></div>' +
            '</div>';
        contentEl.innerHTML = html;
        _runValidation();
        _renderReviewValidation();
    }

    function _renderStep7Preview(contentEl) {
        var html = '<div class="ab-section">' +
            '<h4>Preview</h4>' +
            '<div id="abReviewPreview" class="ab-review-block"><p class="ab-muted">Loading preview\u2026</p></div>' +
            '</div>';
        contentEl.innerHTML = html;
        _runPreview();
    }

    function _renderStep7WorldGraph(contentEl) {
        var wi = state.worldInspection || {};
        var html = '<div class="ab-section ab-wg-section">' +
            '<div id="abWorldGraphDiff"></div>' +
            '<div id="abWgControls" class="ab-wg-controls-container"></div>' +
            '<div id="abWgLegend"></div>' +
            '<div id="abWgCanvas" class="ab-wg-canvas"></div>' +
            '<div id="abWgNodeInspector" class="ab-wg-node-inspector"></div>' +
            '</div>';
        contentEl.innerHTML = html;

        // Render diff summary if available
        var diffEl = contentEl.querySelector('#abWorldGraphDiff');
        if (diffEl) {
            AdventureBuilderWorldGraph.renderGraphDiffSummary(diffEl, wi.graphDiff);
        }
        _fetchAndRenderWorldGraph(contentEl);
    }

    function _renderStep7Simulation(contentEl) {
        var wi = state.worldInspection || {};
        var rt = (wi.simulationRuntime) || {
            state: null,
            lastDiff: null,
            lastSummary: [],
            stepping: false,
            lastEvents: [],
            lastConsequences: [],
            lastEffectDiff: null,
            lastIncidentDiff: null,
            lastReactionDiff: null
        };
        var simState = rt.state;
        var tickLabel = simState ? simState.tick : '—';
        var stepping = rt.stepping;

        var html = '<div class="ab-section ab-wg-section">';

        // ── Simulation controls row ──
        html += '<div class="ab-sim-controls">';
        html += '<button id="abSimAdvance" class="ab-btn ab-btn-primary ab-btn-sm"' + (stepping ? ' disabled' : '') + '>\u23ED Advance Simulation</button>';
        html += '<span class="ab-sim-tick-badge">Tick: <strong>' + _esc(String(tickLabel)) + '</strong></span>';
        html += '</div>';

        // ── Simulation history timeline ──
        if (simState && simState.history && simState.history.length) {
            html += '<div class="ab-sim-history">';
            html += '<h5>Simulation History</h5>';
            simState.history.slice(-5).forEach(function (h) {
                var changeInfo = '';
                if (h.changes) {
                    var parts = [];
                    if (h.changes.threads) parts.push(h.changes.threads + ' thread' + (h.changes.threads !== 1 ? 's' : ''));
                    if (h.changes.factions) parts.push(h.changes.factions + ' faction' + (h.changes.factions !== 1 ? 's' : ''));
                    if (h.changes.locations) parts.push(h.changes.locations + ' location' + (h.changes.locations !== 1 ? 's' : ''));
                    if (parts.length) changeInfo = ' <span class="ab-sim-history-changes">(' + parts.join(', ') + ')</span>';
                }
                html += '<div class="ab-sim-history-row">';
                html += '<span class="ab-sim-history-tick">Tick ' + h.tick + '</span>' + changeInfo;
                html += '<span class="ab-sim-history-summary">' + _esc((h.summary || []).join(', ')) + '</span>';
                html += '</div>';
            });
            html += '</div>';
        }

        // ── Last-step summary ──
        if (rt.lastSummary && rt.lastSummary.length) {
            html += '<div class="ab-sim-summary"><h5>Last Step Summary</h5><ul>';
            rt.lastSummary.forEach(function (line) {
                html += '<li>' + _esc(line) + '</li>';
            });
            html += '</ul></div>';
        }

        // ── Simulation diff panel ──
        html += '<div id="abSimDiffPanel"></div>';

        // ── Static simulation summary (from world inspection) ──
        html += '<div id="abWgSimulation" class="ab-wg-sim-container"><p class="ab-muted">Loading simulation\u2026</p></div>';

        html += '</div>';
        contentEl.innerHTML = html;

        // Render simulation diff if available
        var diffPanel = contentEl.querySelector('#abSimDiffPanel');
        if (diffPanel && rt.lastDiff) {
            AdventureBuilderTimeline.renderSimulationDiff(
                diffPanel,
                rt.lastDiff,
                rt.lastSummary || [],
                rt.lastEvents,
                rt.lastConsequences,
                rt.lastEffectDiff,
                rt.lastIncidentDiff,
                rt.lastReactionDiff,
                rt.state
            );
        }

        // Render the static simulation summary
        _fetchAndRenderSimulation(contentEl);

        // Wire up the advance button
        var advBtn = contentEl.querySelector('#abSimAdvance');
        if (advBtn) {
            advBtn.addEventListener('click', function () {
                _handleAdvanceSimulation(contentEl);
            });
        }
    }

    function _handleAdvanceSimulation(contentEl) {
        var wi = state.worldInspection;
        if (!wi) return;
        if (!wi.simulationRuntime) {
            wi.simulationRuntime = { state: null, lastDiff: null, lastSummary: [], stepping: false };
        }
        if (wi.simulationRuntime.stepping) return;
        wi.simulationRuntime.stepping = true;
        _renderStep7Simulation(contentEl);

        AdventureBuilderApi.simulateStep(state.setup).then(function (res) {
            wi.simulationRuntime.stepping = false;
            if (res.success) {
                // Update setup
                if (res.updated_setup) {
                    state.setup = res.updated_setup;
                    setup = state.setup;
                    AdventureBuilderState.saveDraft(state.setup);
                }
                // Update world inspection data
                if (res.graph) wi.graph = res.graph;
                if (res.simulation) wi.simulation = res.simulation;
                if (res.inspector) wi.inspector = res.inspector;
                // Update runtime
                wi.simulationRuntime.state = res.simulation_state || null;
                wi.simulationRuntime.lastDiff = res.simulation_diff || null;
                wi.simulationRuntime.lastSummary = res.summary || [];
                wi.simulationRuntime.lastEvents = res.events || [];
                wi.simulationRuntime.lastConsequences = res.consequences || [];
                wi.simulationRuntime.lastEffectDiff = res.effect_diff || null;
                wi.simulationRuntime.lastIncidentDiff = res.incident_diff || null;
                wi.simulationRuntime.lastReactionDiff = res.reaction_diff || null;
                wi.simulationRuntime.lastScenes = res.scenes || [];
                // Capture snapshot
                var tick = (res.simulation_state && res.simulation_state.tick) || '?';
                _captureWorldSnapshot('After Simulation Tick ' + tick);
            }
            _renderStep7Simulation(contentEl);
        }).catch(function () {
            wi.simulationRuntime.stepping = false;
            _renderStep7Simulation(contentEl);
        });
    }

    function _renderStep7Inspector(contentEl) {
        var wi = state.worldInspection || {};
        var html = '<div class="ab-section ab-wg-section">' +
            '<div id="abWgInspectorPanel" class="ab-wg-inspector-container"></div>' +
            '</div>';
        contentEl.innerHTML = html;

        var panel = contentEl.querySelector('#abWgInspectorPanel');
        if (wi.inspector && wi.selectedNodeId) {
            AdventureBuilderWorldGraph.renderInspector(panel, wi.selectedNodeId, wi.inspector);
        } else if (wi.inspector) {
            // Show all entities as a list
            _renderInspectorEntityList(panel, wi.inspector);
        } else {
            panel.innerHTML = '<p class="ab-muted">Loading inspector data\u2026</p>';
            _fetchWorldInspection(function () {
                var wi2 = state.worldInspection || {};
                if (wi2.inspector) {
                    _renderInspectorEntityList(panel, wi2.inspector);
                }
            });
        }
    }

    var _DEFAULT_NODE_CONFIG = { icon: '●', color: '#666' };

    function _renderInspectorEntityList(container, inspectorData) {
        if (!inspectorData || !inspectorData.entities) {
            container.innerHTML = '<div class="ab-wg-inspector-empty">No entity data available</div>';
            return;
        }
        var entities = inspectorData.entities;
        var ids = Object.keys(entities);
        if (!ids.length) {
            container.innerHTML = '<div class="ab-wg-inspector-empty">No entities in this setup</div>';
            return;
        }
        var html = '<div class="ab-wg-entity-list">';
        html += '<h5>All Entities (' + ids.length + ')</h5>';
        ids.forEach(function (eid) {
            var e = entities[eid];
            var nc = (typeof AdventureBuilderWorldGraph !== 'undefined' && AdventureBuilderWorldGraph.NODE_CONFIG[e.type]) || _DEFAULT_NODE_CONFIG;
            html += '<div class="ab-wg-entity-list-item" data-id="' + _esc(eid) + '">' +
                '<span class="ab-wg-entity-icon" style="color:' + nc.color + '">' + nc.icon + '</span>' +
                '<span class="ab-wg-entity-name">' + _esc(e.name || e.title || eid) + '</span>' +
                '<span class="ab-wg-entity-type">' + _esc(e.type) + '</span>' +
                '</div>';
        });
        html += '</div>';
        container.innerHTML = html;

        container.querySelectorAll('.ab-wg-entity-list-item').forEach(function (item) {
            item.addEventListener('click', function () {
                var eid = item.getAttribute('data-id');
                state.worldInspection.selectedNodeId = eid;
                AdventureBuilderWorldGraph.renderInspector(container, eid, inspectorData);
            });
        });
    }

    // ── Phase 2.5 — Timeline & Diff tab renderers ──

    function _captureWorldSnapshot(label) {
        var wi = state.worldInspection;
        if (!wi) return;
        AdventureBuilderApi.inspectWorldSnapshot(state.setup, label || 'Snapshot').then(function (res) {
            if (res.success && res.snapshot) {
                // Attach the current setup so we can compare later
                res.snapshot.setup = JSON.parse(JSON.stringify(state.setup));
                if (!wi.snapshots) wi.snapshots = [];
                wi.snapshots.push(res.snapshot);
                if (wi.snapshots.length > MAX_SNAPSHOTS) {
                    wi.snapshots = wi.snapshots.slice(-MAX_SNAPSHOTS);
                }
                wi.selectedSnapshotIndex = wi.snapshots.length - 1;
            }
        }).catch(function () { /* silent */ });
    }

    function _renderStep7Timeline(contentEl) {
        var wi = state.worldInspection || {};
        var html = '<div class="ab-section ab-wg-section"><div id="abTimelineContent"></div></div>';
        contentEl.innerHTML = html;
        var panel = contentEl.querySelector('#abTimelineContent');

        AdventureBuilderTimeline.renderTimeline(panel, wi.snapshots || [], {
            onCapture: function () {
                _captureWorldSnapshot('Manual Snapshot');
                // Re-render after a short delay for the API call
                setTimeout(function () { _renderStep7Timeline(contentEl); }, 600);
            },
            onClear: function () {
                wi.snapshots = [];
                wi.selectedSnapshotIndex = null;
                wi.compareMode = false;
                wi.entityHistory = null;
                _renderStep7Timeline(contentEl);
            },
            onView: function (index) {
                wi.selectedSnapshotIndex = index;
                wi.activeTab = 'inspector';
                _renderStep7_Review(overlayEl.querySelector('#abBody'));
            },
            onCompare: function (index) {
                var snap = (wi.snapshots || [])[index];
                if (!snap || !snap.setup) return;
                wi.compareMode = true;
                wi.selectedSnapshotIndex = index;
                // Fetch server-side diff
                AdventureBuilderApi.compareWorld(snap.setup, state.setup).then(function (res) {
                    if (res.success) {
                        wi.graphDiff = res.diff;
                        wi.activeTab = 'diff';
                        _renderStep7_Review(overlayEl.querySelector('#abBody'));
                    }
                }).catch(function () { /* silent */ });
            }
        });
    }

    function _renderStep7Diff(contentEl) {
        var wi = state.worldInspection || {};
        var html = '<div class="ab-section ab-wg-section">' +
            '<div id="abDiffSummary"></div>' +
            '<div id="abDiffFilters"></div>' +
            '<div id="abDiffBody"></div>' +
            '</div>';
        contentEl.innerHTML = html;
        var summaryEl = contentEl.querySelector('#abDiffSummary');
        var filtersEl = contentEl.querySelector('#abDiffFilters');
        var bodyEl = contentEl.querySelector('#abDiffBody');

        if (summaryEl) AdventureBuilderTimeline.renderGraphDiffSummary(summaryEl, wi.graphDiff);

        if (filtersEl) {
            AdventureBuilderTimeline.renderDiffFilters(filtersEl, wi.diffFilters || { nodeType: 'all', changeType: 'all' }, function (nextFilters) {
                state.worldInspection.diffFilters = nextFilters;
                _renderStep7_Review(overlayEl.querySelector('#abBody'));
            });
        }

        if (bodyEl) {
            var diff = wi.graphDiff || { nodes: { added: [], removed: [], changed: [] }, edges: { added: [], removed: [] } };
            var filters = wi.diffFilters || { nodeType: 'all', changeType: 'all' };

            // Filter changed nodes by type
            var changedNodes = (diff.nodes.changed || []).filter(function (item) {
                if (filters.nodeType === 'all') return true;
                return (wi.graph && wi.graph.nodes || []).some(function (n) {
                    return n.id === item.id && n.type === filters.nodeType;
                });
            });

            // Filter added nodes by type
            var addedNodes = (diff.nodes.added || []).filter(function (id) {
                if (filters.nodeType === 'all') return true;
                return (wi.graph && wi.graph.nodes || []).some(function (n) {
                    return n.id === id && n.type === filters.nodeType;
                });
            });

            // Filter removed nodes by type (we may not have graph data for removed, so show all)
            var removedNodes = (diff.nodes.removed || []).filter(function () {
                return filters.nodeType === 'all';
            });

            var h = '';

            if (filters.changeType === 'all' || filters.changeType === 'added') {
                h += '<h5>Added Nodes</h5><pre>' + _esc(JSON.stringify(addedNodes, null, 2)) + '</pre>';
            }
            if (filters.changeType === 'all' || filters.changeType === 'removed') {
                h += '<h5>Removed Nodes</h5><pre>' + _esc(JSON.stringify(removedNodes, null, 2)) + '</pre>';
            }
            if (filters.changeType === 'all' || filters.changeType === 'changed') {
                h += '<h5>Changed Nodes</h5><pre>' + _esc(JSON.stringify(changedNodes, null, 2)) + '</pre>';
            }
            h += '<h5>Added Edges</h5><pre>' + _esc(JSON.stringify(diff.edges.added || [], null, 2)) + '</pre>';
            h += '<h5>Removed Edges</h5><pre>' + _esc(JSON.stringify(diff.edges.removed || [], null, 2)) + '</pre>';
            bodyEl.innerHTML = h;
        }
    }

    // ── World graph fetch and render ──

    var _wgFilterType = 'all';
    var _wgSearchQuery = '';

    function _fetchWorldInspection(callback) {
        var wi = state.worldInspection;
        if (!wi || !wi.activeTab) {
            state.worldInspection = { loading: false, graph: null, simulation: null, inspector: null, selectedNodeId: null, hoveredNodeId: null, activeTab: 'summary', previousGraph: null, graphDiff: { added: [], removed: [] }, layoutMode: 'auto' };
        }
        if (state.worldInspection.loading) return;
        state.worldInspection.loading = true;

        AdventureBuilderApi.inspectWorld(state.setup).then(function (res) {
            state.worldInspection.loading = false;
            if (res.success) {
                var prevGraph = state.worldInspection.previousGraph || state.worldInspection.graph;
                state.worldInspection.graphDiff = AdventureBuilderWorldGraph.computeAndStoreGraphDiff(prevGraph, res.graph);
                state.worldInspection.graph = res.graph;
                state.worldInspection.simulation = res.simulation;
                state.worldInspection.inspector = res.inspector;
                // Auto-select first node if none selected
                if (!state.worldInspection.selectedNodeId && res.graph && res.graph.nodes && res.graph.nodes.length) {
                    state.worldInspection.selectedNodeId = res.graph.nodes[0].id;
                }
            }
            if (callback) callback(res);
        }).catch(function () {
            state.worldInspection.loading = false;
            if (callback) callback(null);
        });
    }

    function _fetchAndRenderWorldGraph(contentEl) {
        var canvas = contentEl.querySelector('#abWgCanvas');
        var controls = contentEl.querySelector('#abWgControls');
        var legend = contentEl.querySelector('#abWgLegend');
        var inspector = contentEl.querySelector('#abWgNodeInspector');

        var wi = state.worldInspection || {};

        function _rerender() {
            AdventureBuilderWorldGraph.renderGraphControls(controls, {
                filterType: _wgFilterType,
                searchQuery: _wgSearchQuery,
                onFilterChange: function (f) { _wgFilterType = f; _rerender(); },
                onSearchChange: function (q) { _wgSearchQuery = q; _rerender(); }
            });
            AdventureBuilderWorldGraph.renderLegend(legend);
            AdventureBuilderWorldGraph.renderGraph(canvas, wi.graph, {
                selectedNodeId: wi.selectedNodeId,
                hoveredNodeId: wi.hoveredNodeId,
                graphDiff: wi.graphDiff,
                filterType: _wgFilterType,
                searchQuery: _wgSearchQuery,
                layoutMode: wi.layoutMode || 'auto',
                onHoverNode: function (nodeId) {
                    wi.hoveredNodeId = nodeId;
                    _rerender();
                },
                onSelectNode: function (nodeId) {
                    wi.selectedNodeId = nodeId;
                    _rerender();
                    AdventureBuilderWorldGraph.renderInspector(inspector, nodeId, wi.inspector);
                }
            });
            AdventureBuilderWorldGraph.renderInspector(inspector, wi.selectedNodeId, wi.inspector);
        }

        if (wi.graph) {
            _rerender();
        } else {
            canvas.innerHTML = '<p class="ab-muted">Loading world graph\u2026</p>';
            _fetchWorldInspection(function () {
                wi = state.worldInspection || {};
                _rerender();
            });
        }
    }

    function _fetchAndRenderSimulation(contentEl) {
        var simEl = contentEl.querySelector('#abWgSimulation');
        var wi = state.worldInspection || {};

        if (wi.simulation) {
            AdventureBuilderWorldGraph.renderSimulation(simEl, wi.simulation);
        } else {
            _fetchWorldInspection(function () {
                var wi2 = state.worldInspection || {};
                AdventureBuilderWorldGraph.renderSimulation(simEl, wi2.simulation);
            });
        }
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

        // Player & Campaign
        if (s.player_role || s.player_archetype || s.campaign_objective) {
            lines.push('<div class="ab-review-group"><strong>Player Fantasy</strong>');
            if (s.player_role) lines.push('<div>Role: ' + _esc(s.player_role) + '</div>');
            if (s.player_archetype) lines.push('<div>Archetype: ' + _esc(s.player_archetype) + '</div>');
            if (s.player_background) lines.push('<div>Background: ' + _esc(s.player_background) + '</div>');
            lines.push('</div>');
        }
        if (s.campaign_objective) {
            lines.push('<div class="ab-review-group"><strong>Campaign</strong>');
            lines.push('<div>Objective: ' + _esc(s.campaign_objective) + '</div>');
            if (s.opening_hook) lines.push('<div>Hook: ' + _esc(s.opening_hook) + '</div>');
            if (s.starter_conflict) lines.push('<div>Conflict: ' + _esc(s.starter_conflict) + '</div>');
            lines.push('</div>');
        }

        lines.push('<div class="ab-review-group"><strong>Rules</strong>');
        lines.push('<div>Hard rules: ' + (s.hard_rules || []).length + '</div>');
        lines.push('<div>Tone rules: ' + (s.soft_tone_rules || []).length + '</div>');
        lines.push('<div>Forbidden: ' + (s.forbidden_content || []).length + '</div>');
        lines.push('<div>Canon notes: ' + (s.canon_notes || []).length + '</div>');
        if ((s.core_world_laws || []).length) lines.push('<div>World laws: ' + s.core_world_laws.length + '</div>');
        if ((s.genre_rules || []).length) lines.push('<div>Genre rules: ' + s.genre_rules.length + '</div>');
        lines.push('</div>');

        lines.push('<div class="ab-review-group"><strong>World Seeds</strong>');
        lines.push('<div>Factions: ' + (s.factions || []).length + '</div>');
        lines.push('<div>Locations: ' + (s.locations || []).length + '</div>');
        lines.push('<div>NPCs: ' + (s.npc_seeds || []).length + '</div>');
        lines.push('</div>');

        // Opening
        var op = s.opening || {};
        lines.push('<div class="ab-review-group"><strong>Opening</strong>');
        var openLocId = op.location_id || s.starting_location_id || '(auto)';
        var openLocName = openLocId;
        (s.locations || []).forEach(function (l) { if (l.location_id === openLocId) openLocName = l.name; });
        lines.push('<div>\uD83D\uDCCD Location: ' + _esc(openLocName) + '</div>');
        if (op.time_of_day) lines.push('<div>Time: ' + _esc(op.time_of_day) + '</div>');
        if (op.tension_level) lines.push('<div>Tension: ' + _esc(op.tension_level) + '</div>');
        if (op.scene_frame) lines.push('<div><em>' + _esc(op.scene_frame) + '</em></div>');
        if (op.immediate_problem) lines.push('<div>\u26A1 Problem: ' + _esc(op.immediate_problem) + '</div>');
        if (op.player_involvement_reason) lines.push('<div>\uD83E\uDDD1 Why involved: ' + _esc(op.player_involvement_reason) + '</div>');
        var presentNpcs = op.present_npc_ids || s.starting_npc_ids || [];
        var npcMap = {};
        (s.npc_seeds || []).forEach(function (n) { npcMap[n.npc_id] = n.name; });
        var startNames = [];
        presentNpcs.forEach(function (id) { startNames.push(npcMap[id] || id); });
        lines.push('<div>\uD83D\uDC64 Present: ' + (startNames.length ? _esc(startNames.join(', ')) : '(auto)') + '</div>');
        if ((op.first_choices || []).length) lines.push('<div>First choices: ' + op.first_choices.length + '</div>');
        lines.push('</div>');

        // Generated package
        var gp = s.generated_package || {};
        if (gp.status === 'done') {
            lines.push('<div class="ab-review-group"><strong>Generated World</strong>');
            lines.push('<div>Characters: ' + (gp.characters || []).length + '</div>');
            lines.push('<div>Factions: ' + (gp.factions || []).length + '</div>');
            lines.push('<div>Locations: ' + (gp.locations || []).length + '</div>');
            lines.push('<div>Lore: ' + (gp.lore_entries || []).length + '</div>');
            lines.push('</div>');
        }

        // Content mix summary
        if (s.desired_content_mix) {
            lines.push('<div class="ab-review-group"><strong>Content Mix</strong>');
            Object.keys(s.desired_content_mix).forEach(function (k) {
                var pct = Math.round((s.desired_content_mix[k] || 0) * 100);
                if (pct > 0) lines.push('<div>' + _esc(k) + ': ' + pct + '%</div>');
            });
            lines.push('</div>');
        }

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
        // Phase 1.5 — show health warnings if available
        if (pr.health) {
            html += _renderHealthWarnings(pr);
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
        if (currentStep === 7) _renderReviewValidation();
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
            case 2: _readStep2_PlayerCampaign(); break;
            case 3: _readStep3_Rules(); break;
            case 4: _readStep4_World(); break;
            case 5: _readStep5_Opening(); break;
            case 6: _readStep6_Generated(); break;
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

    function _readStep3_Rules() {
        setup.hard_rules = _readChips('abHardRules');
        setup.soft_tone_rules = _readChips('abToneRules');
        setup.forbidden_content = _readChips('abForbidden');
        setup.canon_notes = _readChips('abCanonNotes');
    }

    function _readStep4_World() {
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

    function _readStep5_Opening() {
        if (!setup.opening) setup.opening = {};
        var loc = overlayEl.querySelector('#abOpeningLocation');
        if (loc) setup.opening.location_id = loc.value || '';
        setup.opening.time_of_day = _val('abOpeningTime') || setup.opening.time_of_day;
        setup.opening.weather = _val('abOpeningWeather') || setup.opening.weather;
        setup.opening.tension_level = _val('abOpeningTension') || setup.opening.tension_level;
        setup.opening.scene_frame = _val('abSceneFrame') || setup.opening.scene_frame;
        setup.opening.immediate_problem = _val('abImmediateProblem') || setup.opening.immediate_problem;
        setup.opening.player_involvement_reason = _val('abInvolvementReason') || setup.opening.player_involvement_reason;
        var npcIds = [];
        overlayEl.querySelectorAll('.ab-opening-npc:checked').forEach(function (cb) {
            npcIds.push(cb.value);
        });
        setup.opening.present_npc_ids = npcIds;
        setup.opening.first_choices = _readChips('abFirstChoices');
        // Also sync legacy fields
        setup.starting_location_id = setup.opening.location_id || setup.starting_location_id;
        setup.starting_npc_ids = npcIds.length ? npcIds : setup.starting_npc_ids;
    }

    function _readStep6_Generated() {
        // Generation preferences are read directly from inputs if present
        if (!setup.generation_preferences) setup.generation_preferences = {};
        var cc = overlayEl.querySelector('#abGenCharCount');
        if (cc) setup.generation_preferences.character_count = parseInt(cc.value, 10) || 5;
        var lc = overlayEl.querySelector('#abGenLocCount');
        if (lc) setup.generation_preferences.location_count = parseInt(lc.value, 10) || 4;
        var fc = overlayEl.querySelector('#abGenFacCount');
        if (fc) setup.generation_preferences.faction_count = parseInt(fc.value, 10) || 3;
        var lr = overlayEl.querySelector('#abGenLoreCount');
        if (lr) setup.generation_preferences.lore_count = parseInt(lr.value, 10) || 6;
        var cp = overlayEl.querySelector('#abGenCreativity');
        if (cp) setup.generation_preferences.creativity_profile = cp.value || 'balanced';
    }

    function _readStep2_PlayerCampaign() {
        setup.player_role = _val('abPlayerRole');
        setup.player_archetype = _val('abPlayerArchetype');
        setup.player_background = _val('abPlayerBackground');
        setup.campaign_objective = _val('abCampaignObjective');
        setup.opening_hook = _val('abOpeningHook');
        setup.starter_conflict = _val('abStarterConflict');
        setup.core_world_laws = _readChips('abCoreWorldLaws');
        setup.genre_rules = _readChips('abGenreRules');
        // Read content mix sliders
        var mixKeys = ['combat', 'exploration', 'intrigue', 'mystery', 'survival', 'romance', 'humor'];
        var mix = {};
        mixKeys.forEach(function (k) {
            var el = overlayEl.querySelector('#abMix_' + k);
            mix[k] = el ? parseFloat(el.value) || 0 : (setup.desired_content_mix[k] || 0);
        });
        setup.desired_content_mix = AdventureBuilderState.normalizeDesiredContentMix(mix);
        // Read starting gear
        var gearItems = [];
        overlayEl.querySelectorAll('.ab-gear-row').forEach(function (row) {
            var nameEl = row.querySelector('.ab-gear-name');
            var descEl = row.querySelector('.ab-gear-desc');
            var name = nameEl ? nameEl.value.trim() : '';
            if (name) gearItems.push({ name: name, description: descEl ? descEl.value.trim() : '' });
        });
        setup.starting_gear = AdventureBuilderState.normalizeGearItems(gearItems);
        // Read starting resources
        if (!setup.starting_resources) setup.starting_resources = {};
        ['gold', 'supplies', 'ammo', 'rations'].forEach(function (k) {
            var el = overlayEl.querySelector('#abRes_' + k);
            if (el) setup.starting_resources[k] = parseInt(el.value, 10) || 0;
        });
        setup.starting_resources = AdventureBuilderState.normalizeStartingResources(setup.starting_resources);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Regeneration controller (Phase 1.4A — preview/apply flow)
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

    // Targets that support merge strategy
    var MERGE_TARGETS = { factions: true, locations: true, npc_seeds: true };
    // Targets that support append strategy
    var APPEND_TARGETS = { threads: true };

    function _handleRegenerate(target) {
        _readCurrentStepIntoSetup();
        _markDirty();

        state.regenerating = target;
        state.regen.target = target;
        state.regen.loading = true;
        _setRegenerationButtonsDisabled(true, target);

        // Phase 1.4A: Always start with preview mode
        AdventureBuilderApi.regenerateSection(target, state.setup, {
            mode: 'preview',
            tone: state.tone || null,
            constraints: state.constraints || null
        }).then(function (res) {
            if (!res || !res.success) {
                alert((res && res.error) || 'Regeneration failed.');
                state.regenerating = null;
                state.regen.loading = false;
                _setRegenerationButtonsDisabled(false, null);
                return;
            }

            // Store preview in normalized state
            state.regen.preview = res;
            state.regen.modalOpen = true;

            // Show diff preview modal; user chooses apply/cancel/strategy
            _showRegenPreviewModal(target, res);
        }).catch(function () {
            alert('Regeneration failed.');
            state.regenerating = null;
            state.regen.loading = false;
            _setRegenerationButtonsDisabled(false, null);
        });
    }

    function _showRegenPreviewModal(target, previewRes) {
        var diff = previewRes.diff || {};
        var summary = (diff.summary || []);
        var rationale = previewRes.rationale
            ? '<div class="ab-regen-rationale">' + _esc(previewRes.rationale) + '</div>'
            : '';

        var hasMerge = !!MERGE_TARGETS[target];
        var hasAppend = !!APPEND_TARGETS[target];

        var html = '<div class="ab-modal-overlay" id="abRegenModal">' +
            '<div class="ab-modal">' +
            '<h3>Preview: Regenerate ' + _esc(target) + '</h3>' +
            rationale +
            '<div class="ab-diff-summary">';

        if (summary.length) {
            summary.forEach(function (line) {
                html += '<div class="ab-diff-line">' + _esc(line) + '</div>';
            });
        } else {
            html += '<div class="ab-diff-line ab-muted">No changes detected.</div>';
        }

        html += '<div class="ab-diff-stats">' +
            '<span class="ab-diff-added">+' + (diff.added || 0) + ' added</span> ' +
            '<span class="ab-diff-removed">\u2212' + (diff.removed || 0) + ' removed</span> ' +
            '<span class="ab-diff-changed">\u0394' + (diff.changed || 0) + ' changed</span>' +
            '</div>';

        html += '</div>' +
            '<div class="ab-modal-actions">' +
            '<button class="ab-btn ab-btn-primary" id="abRegenApplyReplace">\u2705 Replace All</button>';

        if (hasMerge) {
            html += '<button class="ab-btn ab-btn-secondary" id="abRegenApplyMerge">\U0001f500 Merge New</button>';
        }
        if (hasAppend) {
            html += '<button class="ab-btn ab-btn-secondary" id="abRegenApplyAppend">\u2795 Append</button>';
        }

        html += '<button class="ab-btn ab-btn-secondary" id="abRegenRetry">\u267B Regenerate Again</button>' +
            '<button class="ab-btn ab-btn-cancel" id="abRegenCancel">\u274C Cancel</button>' +
            '</div></div></div>';

        // Append modal to overlay
        var modalContainer = document.createElement('div');
        modalContainer.innerHTML = html;
        var modal = modalContainer.firstChild;
        (overlayEl || document.body).appendChild(modal);

        // Bind buttons
        var applyToken = previewRes.apply_token;

        modal.querySelector('#abRegenApplyReplace').addEventListener('click', function () {
            _closeRegenModal(modal);
            _applyRegeneration(target, applyToken, 'replace');
        });

        if (hasMerge) {
            modal.querySelector('#abRegenApplyMerge').addEventListener('click', function () {
                _closeRegenModal(modal);
                _applyRegeneration(target, applyToken, 'merge');
            });
        }

        if (hasAppend) {
            modal.querySelector('#abRegenApplyAppend').addEventListener('click', function () {
                _closeRegenModal(modal);
                _applyRegeneration(target, applyToken, 'append');
            });
        }

        modal.querySelector('#abRegenCancel').addEventListener('click', function () {
            _closeRegenModal(modal);
            state.regenerating = null;
            state.regen.modalOpen = false;
            state.regen.preview = null;
            _setRegenerationButtonsDisabled(false, null);
        });

        modal.querySelector('#abRegenRetry').addEventListener('click', function () {
            _closeRegenModal(modal);
            state.regen.modalOpen = false;
            state.regen.preview = null;
            _handleRegenerate(target);
        });

        // Keyboard shortcuts
        modal.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                modal.remove();
                state.regen.modalOpen = false;
                state.regen.preview = null;
            } else if (e.key === 'Enter') {
                var primary = modal.querySelector('[data-strategy="replace"]') || modal.querySelector('#abRegenApplyReplace');
                if (primary) primary.click();
            }
        });

        // Make modal focusable for keyboard events
        modal.tabIndex = -1;
        modal.focus();
    }

    function _closeRegenModal(modal) {
        if (modal && modal.parentNode) modal.parentNode.removeChild(modal);
    }

    function _applyRegeneration(target, applyToken, strategy) {
        _setRegenerationButtonsDisabled(true, target);

        // Phase 1.4D: push undo snapshot before applying
        AdventureBuilderState.pushHistory(state, {
            type: 'regeneration',
            target: target,
            strategy: strategy,
            beforeSetup: JSON.parse(JSON.stringify(state.setup)),
            timestamp: Date.now()
        });

        state.regen.loading = true;

        AdventureBuilderApi.regenerateSection(target, state.setup, {
            mode: 'apply',
            apply_token: applyToken,
            apply_strategy: strategy,
            tone: state.tone || null,
            constraints: state.constraints || null
        }).then(function (res) {
            if (!res || !res.success) {
                // Roll back the undo entry we just pushed
                AdventureBuilderState.popHistory(state);
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
                resolved_context: res.resolved_context || null,
                health: res.health || null
            };

            // Clear regen state
            state.regen.preview = null;
            state.regen.modalOpen = false;

            _saveDraft();
            _captureWorldSnapshot('After Regeneration (' + target + ')');
            _renderStep();
            _runValidation();
        }).catch(function () {
            AdventureBuilderState.popHistory(state);
            alert('Regeneration failed.');
        }).finally(function () {
            state.regenerating = null;
            state.regen.loading = false;
            _setRegenerationButtonsDisabled(false, null);
        });
    }

    // ── Single-item regeneration (Phase 1.4C) ─────────────────────────

    function _handleRegenerateItem(target, itemId) {
        _readCurrentStepIntoSetup();
        _markDirty();

        AdventureBuilderApi.regenerateItem(target, itemId, state.setup).then(function (res) {
            if (!res || !res.success) {
                alert((res && res.error) || 'Item regeneration failed.');
                return;
            }

            _showItemDiffModal(target, itemId, res);
        }).catch(function () {
            alert('Item regeneration failed.');
        });
    }

    function _showItemDiffModal(target, itemId, res) {
        var diff = res.diff || {};
        var changedFields = diff.changed_fields || [];
        var before = res.before || {};
        var after = res.after || {};
        var rationale = res.rationale
            ? '<div class="ab-regen-rationale">' + _esc(res.rationale) + '</div>'
            : '';

        var html = '<div class="ab-modal-overlay" id="abItemRegenModal">' +
            '<div class="ab-modal">' +
            '<h3>Preview: Regenerate ' + _esc(itemId) + '</h3>' +
            rationale +
            '<div class="ab-diff-detail">';

        if (!changedFields.length) {
            html += '<div class="ab-diff-line ab-muted">No changes detected.</div>';
        } else {
            changedFields.forEach(function (field) {
                var oldVal = before[field];
                var newVal = after[field];
                html += '<div class="ab-diff-field">' +
                    '<strong>' + _esc(field) + '</strong>' +
                    '<div class="ab-diff-old">\u2212 ' + _esc(String(oldVal != null ? oldVal : '')) + '</div>' +
                    '<div class="ab-diff-new">+ ' + _esc(String(newVal != null ? newVal : '')) + '</div>' +
                    '</div>';
            });
        }

        html += '</div>' +
            '<div class="ab-modal-actions">' +
            '<button class="ab-btn ab-btn-primary" id="abItemApply">\u2705 Apply</button>' +
            '<button class="ab-btn ab-btn-secondary" id="abItemRetry">\u267B Regenerate Again</button>' +
            '<button class="ab-btn ab-btn-cancel" id="abItemCancel">\u274C Cancel</button>' +
            '</div></div></div>';

        var modalContainer = document.createElement('div');
        modalContainer.innerHTML = html;
        var modal = modalContainer.firstChild;
        (overlayEl || document.body).appendChild(modal);

        modal.querySelector('#abItemApply').addEventListener('click', function () {
            _closeRegenModal(modal);

            // Push undo snapshot
            AdventureBuilderState.pushHistory(state, {
                type: 'item_regeneration',
                target: target,
                item_id: itemId,
                beforeSetup: JSON.parse(JSON.stringify(state.setup)),
                timestamp: Date.now()
            });

            if (res.updated_setup) {
                state.setup = res.updated_setup;
                setup = state.setup;
            }
            state.validation = res.validation || null;
            state.preview = {
                ok: true,
                preview: res.preview || null,
                validation: res.validation || null,
                resolved_context: res.resolved_context || null,
                health: res.health || null
            };

            _saveDraft();
            _renderStep();
            _runValidation();
        });

        modal.querySelector('#abItemRetry').addEventListener('click', function () {
            _closeRegenModal(modal);
            _handleRegenerateItem(target, itemId);
        });

        modal.querySelector('#abItemCancel').addEventListener('click', function () {
            _closeRegenModal(modal);
        });

        // Keyboard shortcuts for item modal
        modal.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                modal.remove();
            } else if (e.key === 'Enter') {
                var primary = modal.querySelector('#abItemApply');
                if (primary) primary.click();
            }
        });

        // Make modal focusable for keyboard events
        modal.tabIndex = -1;
        modal.focus();
    }

    // ── Single-item regeneration with loading state ─────────────────────

    function _handleRegenerateItem(target, itemId) {
        _readCurrentStepIntoSetup();
        _markDirty();
        state.regen.loading = true;

        AdventureBuilderApi.regenerateItem(target, itemId, state.setup).then(function (res) {
            if (!res || !res.success) {
                alert((res && res.error) || 'Item regeneration failed.');
                return;
            }

            _showItemDiffModal(target, itemId, res);
        }).catch(function () {
            alert('Item regeneration failed.');
        }).finally(function () {
            state.regen.loading = false;
        });
    }

    // ── Undo last regeneration (Phase 1.4D) ───────────────────────────

    function _handleUndo() {
        var entry = AdventureBuilderState.popHistory(state);
        if (!entry || !entry.beforeSetup) {
            alert('Nothing to undo.');
            return;
        }
        state.setup = entry.beforeSetup;
        setup = state.setup;

        // Clear regen state on undo
        state.regen.preview = null;
        state.regen.modalOpen = false;

        _saveDraft();
        _captureWorldSnapshot('After Undo');
        _renderStep();
        _runValidation();
    }

    // ── Phase 1.5 — Multi-select & bulk regeneration ──────────────────

    function _toggleSelection(target, id) {
        var sel = state.selection;
        if (sel.activeTarget !== target) {
            sel.items = [];
            sel.activeTarget = target;
        }
        var idx = sel.items.indexOf(id);
        if (idx >= 0) sel.items.splice(idx, 1);
        else sel.items.push(id);
    }

    function _clearSelection() {
        state.selection.items = [];
        state.selection.activeTarget = null;
    }

    function _selectionCount(target) {
        if (state.selection.activeTarget !== target) return 0;
        return (state.selection.items || []).length;
    }

    function _handleBulkRegenerate(target) {
        var ids = state.selection.items;
        if (!ids.length) { alert('No ' + target.replace('_', ' ') + ' selected'); return; }
        _readCurrentStepIntoSetup();
        _markDirty();
        AdventureBuilderApi.regenerateMultiple(target, ids, state.setup)
            .then(function (res) {
                if (!res || !res.success) { alert((res && res.error) || 'Bulk regeneration failed.'); return; }
                if (res.updated_setup) {
                    state.setup = res.updated_setup;
                    setup = state.setup;
                }
                if (res.health) {
                    state.preview = state.preview || {};
                    state.preview.health = res.health;
                }
                alert('Regenerated ' + res.count + ' ' + target.replace('_', ' '));
                _clearSelection();
                _renderStep();
                _runValidation();
                _runPreview();
            })
            .catch(function () { alert('Bulk regeneration failed.'); });
    }

    // ── Phase 1.5 — Tone selector ────────────────────────────────────

    function _renderToneSelector(container) {
        var tones = ['neutral', 'grim', 'heroic', 'chaotic'];
        var opts = '';
        tones.forEach(function (t) {
            var sel = (t === state.tone) ? ' selected' : '';
            opts += '<option value="' + t + '"' + sel + '>' + t.charAt(0).toUpperCase() + t.slice(1) + '</option>';
        });
        var html = '<div class="ab-section">' +
            '<h4>Tone</h4>' +
            '<p class="ab-hint">Set an overall narrative tone for regenerated content.</p>' +
            '<select id="abTone" class="ab-select">' + opts + '</select>' +
            '</div>';
        container.insertAdjacentHTML('beforeend', html);

        var sel = container.querySelector('#abTone');
        if (sel) {
            sel.addEventListener('change', function (e) {
                state.tone = e.target.value;
            });
        }
    }

    // ── Phase 1.5 — Constraint editor ─────────────────────────────────

    function _renderConstraints(container) {
        var c = state.constraints || {};
        var factionChecked = c.require_factions ? ' checked' : '';
        var conflictChecked = (c.require_conflict !== false) ? ' checked' : '';
        var density = c.npc_density || 'medium';

        var densityOpts = '';
        ['low', 'medium', 'high'].forEach(function (d) {
            var sel = (d === density) ? ' selected' : '';
            densityOpts += '<option value="' + d + '"' + sel + '>' + d.charAt(0).toUpperCase() + d.slice(1) + '</option>';
        });

        var html = '<div class="ab-section">' +
            '<h4>Constraints</h4>' +
            '<p class="ab-hint">Adjust generation constraints for the next regeneration.</p>' +
            '<label class="ab-checkbox-label"><input type="checkbox" id="abConstraintFaction"' + factionChecked + '> Require factions</label>' +
            '<label class="ab-checkbox-label"><input type="checkbox" id="abConstraintConflict"' + conflictChecked + '> Require conflict</label>' +
            '<label class="ab-label">NPC Density <select id="abConstraintDensity" class="ab-select">' + densityOpts + '</select></label>' +
            '</div>';
        container.insertAdjacentHTML('beforeend', html);

        var fEl = container.querySelector('#abConstraintFaction');
        if (fEl) fEl.addEventListener('change', function (e) { state.constraints.require_factions = e.target.checked; });

        var cEl = container.querySelector('#abConstraintConflict');
        if (cEl) cEl.addEventListener('change', function (e) { state.constraints.require_conflict = e.target.checked; });

        var dEl = container.querySelector('#abConstraintDensity');
        if (dEl) dEl.addEventListener('change', function (e) { state.constraints.npc_density = e.target.value; });
    }

    // ── Phase 1.5 — Health warnings display ──────────────────────────

    function _renderHealthWarnings(res) {
        if (!res || !res.health) return '';
        var health = res.health;
        var html = '<div class="ab-health">';
        if (health.warnings && health.warnings.length) {
            health.warnings.forEach(function (w) {
                html += '<div class="ab-warning">\u26A0\uFE0F ' + _esc(w) + '</div>';
            });
        }
        html += '<div class="ab-hint">Health score: ' + (health.score != null ? health.score : '—') + '/100</div>';
        html += '</div>';
        return html;
    }

    // ── Phase 1.5 — Client-side health check (mirrors backend) ───────

    function _computeClientHealth() {
        var s = state.setup || {};
        var warnings = [];
        if ((s.npc_seeds || []).length < 2) {
            warnings.push('Very few NPCs — consider adding more for richer interactions.');
        }
        if ((s.factions || []).length === 0) {
            warnings.push('No factions defined — world may feel flat.');
        }
        if (!s.starting_location_id) {
            warnings.push('No starting location set.');
        }
        return {
            warnings: warnings,
            score: Math.max(0, 100 - (warnings.length * 20))
        };
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
        // Update undo button visibility
        var undoBtn = overlayEl.querySelector('#abUndoRegen');
        if (undoBtn) {
            undoBtn.disabled = !AdventureBuilderState.hasHistory(state);
        }
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