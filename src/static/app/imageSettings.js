(function (global) {
    'use strict';

    function _el(id) {
        return document.getElementById(id);
    }

    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function buildGlobalImageProviderOptions(currentProvider, providersPayload) {
        var providers = (providersPayload && providersPayload.providers) || [];
        if (!providers.length) {
            providers = [
                { key: 'flux_klein', label: 'FLUX.2 [klein] 4B' },
                { key: 'mock', label: 'Mock Image Provider' }
            ];
        }
        return providers.map(function (item) {
            var key = escapeHtml(item.key || '');
            var label = escapeHtml(item.label || item.key || '');
            var selected = key === String(currentProvider || 'flux_klein') ? ' selected' : '';
            return '<option value="' + key + '"' + selected + '>' + label + '</option>';
        }).join('');
    }

    function buildGlobalImageSettingsHtml(data, providersPayload) {
        var settings = (data && data.settings) || {};
        var flux = settings.flux_klein || {};
        var chat = settings.chat || {};
        var story = settings.story || {};
        var provider = settings.provider || 'flux_klein';
        return ''
            + '<div class="rpg-settings-card">'
            + '  <h3>Global Image Service</h3>'
            + '  <label><input type="checkbox" id="imgEnabled"' + (settings.enabled ? ' checked' : '') + '> Enabled</label><br>'
            + '  <label><input type="checkbox" id="imgAutoUnload"' + (settings.auto_unload_on_disable ? ' checked' : '') + '> Auto-unload on disable</label><br>'
            + '  <label>Provider'
            + '    <select id="imgProvider">'
            +          buildGlobalImageProviderOptions(provider, providersPayload)
            + '    </select>'
            + '  </label><br>'
            + '  <label>Download Dir'
            + '    <input id="imgFluxDownloadDir" type="text" value="' + escapeHtml(flux.download_dir || 'image') + '">'
            + '  </label><br>'
            + '  <label>Local Dir'
            + '    <input id="imgFluxLocalDir" type="text" value="' + escapeHtml(flux.local_dir || '') + '">'
            + '  </label><br>'
            + '  <label>Scene Width'
            + '    <input id="imgSceneWidth" type="number" value="' + String(flux.scene_width || 1344) + '">'
            + '  </label><br>'
            + '  <label>Scene Height'
            + '    <input id="imgSceneHeight" type="number" value="' + String(flux.scene_height || 768) + '">'
            + '  </label><br>'
            + '  <label>Portrait Width'
            + '    <input id="imgPortraitWidth" type="number" value="' + String(flux.portrait_width || 768) + '">'
            + '  </label><br>'
            + '  <label>Portrait Height'
            + '    <input id="imgPortraitHeight" type="number" value="' + String(flux.portrait_height || 1024) + '">'
            + '  </label><br>'
            + '  <label><input type="checkbox" id="imgChatAuto"' + (chat.auto_generate_images ? ' checked' : '') + '> Chat auto-generate images</label><br>'
            + '  <label>Chat style'
            + '    <input id="imgChatStyle" type="text" value="' + escapeHtml(chat.style || '') + '">'
            + '  </label><br>'
            + '  <label><input type="checkbox" id="imgStorySceneAuto"' + (story.auto_generate_scene_images ? ' checked' : '') + '> Story auto-generate scenes</label><br>'
            + '  <label><input type="checkbox" id="imgStoryCoverAuto"' + (story.auto_generate_cover_images ? ' checked' : '') + '> Story auto-generate covers</label><br>'
            + '  <label>Story style'
            + '    <input id="imgStoryStyle" type="text" value="' + escapeHtml(story.style || 'story') + '">'
            + '  </label><br>'
            + '  <div class="rpg-settings-actions">'
            + '    <button id="imgSettingsSaveBtn">Save</button>'
            + '    <button id="imgSettingsDownloadBtn">Download FLUX</button>'
            + '    <button id="imgSettingsLoadBtn">Load Provider</button>'
            + '    <button id="imgSettingsUnloadBtn">Unload Provider</button>'
            + '    <button id="imgSettingsRefreshRuntimeBtn">Refresh Runtime</button>'
            + '    <button id="imgSettingsListJobsBtn">List Jobs</button>'
            + '    <button id="imgSettingsManifestBtn">Asset Manifest</button>'
            + '    <button id="imgSettingsCleanupAssetsBtn">Cleanup Assets</button>'
            + '  </div>'
            + '  <pre id="imgRuntimeStatusBox"></pre>'
            + '</div>';
    }

    function collectGlobalImageSettingsForm() {
        return {
            enabled: !!(_el('imgEnabled') && _el('imgEnabled').checked),
            auto_unload_on_disable: !!(_el('imgAutoUnload') && _el('imgAutoUnload').checked),
            provider: (_el('imgProvider') && _el('imgProvider').value) || 'flux_klein',
            chat: {
                auto_generate_images: !!(_el('imgChatAuto') && _el('imgChatAuto').checked),
                style: (_el('imgChatStyle') && _el('imgChatStyle').value) || ''
            },
            story: {
                auto_generate_scene_images: !!(_el('imgStorySceneAuto') && _el('imgStorySceneAuto').checked),
                auto_generate_cover_images: !!(_el('imgStoryCoverAuto') && _el('imgStoryCoverAuto').checked),
                style: (_el('imgStoryStyle') && _el('imgStoryStyle').value) || 'story'
            },
            flux_klein: {
                download_dir: (_el('imgFluxDownloadDir') && _el('imgFluxDownloadDir').value) || 'image',
                local_dir: (_el('imgFluxLocalDir') && _el('imgFluxLocalDir').value) || '',
                scene_width: Number((_el('imgSceneWidth') && _el('imgSceneWidth').value) || 1344),
                scene_height: Number((_el('imgSceneHeight') && _el('imgSceneHeight').value) || 768),
                portrait_width: Number((_el('imgPortraitWidth') && _el('imgPortraitWidth').value) || 768),
                portrait_height: Number((_el('imgPortraitHeight') && _el('imgPortraitHeight').value) || 1024)
            }
        };
    }

    function bindGlobalImageSettingsEvents(container) {
        var runtimeBox = _el('imgRuntimeStatusBox');
        var saveBtn = _el('imgSettingsSaveBtn');
        var downloadBtn = _el('imgSettingsDownloadBtn');
        var loadBtn = _el('imgSettingsLoadBtn');
        var unloadBtn = _el('imgSettingsUnloadBtn');
        var refreshBtn = _el('imgSettingsRefreshRuntimeBtn');
        var jobsBtn = _el('imgSettingsListJobsBtn');
        var manifestBtn = _el('imgSettingsManifestBtn');
        var cleanupBtn = _el('imgSettingsCleanupAssetsBtn');

        function refreshRuntime() {
            fetch('/api/image/runtime', {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            }).then(function (r) { return r.json(); }).then(function (data) {
                if (runtimeBox) runtimeBox.textContent = JSON.stringify(data, null, 2);
            }).catch(function () {
                if (runtimeBox) runtimeBox.textContent = 'Failed to load runtime status.';
            });
        }

        if (saveBtn) {
            saveBtn.addEventListener('click', function () {
                fetch('/api/image/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(collectGlobalImageSettingsForm())
                }).then(function (r) { return r.json(); }).then(function () {
                    refreshRuntime();
                });
            });
        }

        if (downloadBtn) {
            downloadBtn.addEventListener('click', function () {
                fetch('/api/image/models/flux-klein/download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                }).then(function (r) { return r.json(); }).then(function (data) {
                    if (runtimeBox) runtimeBox.textContent = JSON.stringify(data, null, 2);
                });
            });
        }

        if (loadBtn) {
            loadBtn.addEventListener('click', function () {
                fetch('/api/image/provider/load', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ provider: (_el('imgProvider') && _el('imgProvider').value) || 'flux_klein' })
                }).then(function (r) { return r.json(); }).then(function (data) {
                    if (runtimeBox) runtimeBox.textContent = JSON.stringify(data, null, 2);
                    refreshRuntime();
                });
            });
        }

        if (unloadBtn) {
            unloadBtn.addEventListener('click', function () {
                fetch('/api/image/provider/unload', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ provider: (_el('imgProvider') && _el('imgProvider').value) || 'flux_klein' })
                }).then(function (r) { return r.json(); }).then(function (data) {
                    if (runtimeBox) runtimeBox.textContent = JSON.stringify(data, null, 2);
                    refreshRuntime();
                });
            });
        }

        if (refreshBtn) {
            refreshBtn.addEventListener('click', refreshRuntime);
        }

        if (jobsBtn) {
            jobsBtn.addEventListener('click', function () {
                fetch('/api/image/jobs', {
                    method: 'GET',
                    headers: { 'Content-Type': 'application/json' }
                }).then(function (r) { return r.json(); }).then(function (data) {
                    if (runtimeBox) runtimeBox.textContent = JSON.stringify(data, null, 2);
                });
            });
        }

        if (manifestBtn) {
            manifestBtn.addEventListener('click', function () {
                fetch('/api/image/assets/manifest', {
                    method: 'GET',
                    headers: { 'Content-Type': 'application/json' }
                }).then(function (r) { return r.json(); }).then(function (data) {
                    if (runtimeBox) runtimeBox.textContent = JSON.stringify(data, null, 2);
                });
            });
        }

        if (cleanupBtn) {
            cleanupBtn.addEventListener('click', function () {
                fetch('/api/image/assets/cleanup', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                }).then(function (r) { return r.json(); }).then(function (data) {
                    if (runtimeBox) runtimeBox.textContent = JSON.stringify(data, null, 2);
                });
            });
        }

        refreshRuntime();
    }

    function loadGlobalImageSettings(container) {
        Promise.all([
            fetch('/api/image/settings', {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            }).then(function (r) { return r.json(); }),
            fetch('/api/image/providers', {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            }).then(function (r) { return r.json(); }).catch(function () { return { ok: false, providers: [] }; })
        ]).then(function (results) {
            var data = results[0];
            var providersPayload = results[1];
            if (!container) return;
            if (!data || !data.ok) {
                container.innerHTML = '<p>Failed to load global image settings</p>';
                return;
            }
            container.innerHTML = buildGlobalImageSettingsHtml(data, providersPayload);
            bindGlobalImageSettingsEvents(container);
        }).catch(function () {
            if (container) container.innerHTML = '<p>Failed to load global image settings</p>';
        });
    }

    global.ImageSettingsUI = {
        loadGlobalImageSettings: loadGlobalImageSettings,
        bindGlobalImageSettingsEvents: bindGlobalImageSettingsEvents,
        buildGlobalImageSettingsHtml: buildGlobalImageSettingsHtml,
        buildGlobalImageProviderOptions: buildGlobalImageProviderOptions,
        collectGlobalImageSettingsForm: collectGlobalImageSettingsForm
    };
})(window);