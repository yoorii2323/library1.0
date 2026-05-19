(function () {
    const STORAGE_KEY = 'library_catalog_color_mode';
    const MODES = ['normal', 'dark', 'reading'];

    function apply(mode) {
        const m = MODES.includes(mode) ? mode : 'normal';
        document.documentElement.setAttribute('data-color-mode', m);
        try {
            localStorage.setItem(STORAGE_KEY, m);
        } catch (e) { /* ignore */ }
        const sel = document.getElementById('colorModeSelect');
        if (sel && sel.value !== m) sel.value = m;
    }

    function init() {
        let saved = 'normal';
        try {
            saved = localStorage.getItem(STORAGE_KEY) || 'normal';
        } catch (e) { /* ignore */ }
        apply(saved);
        const sel = document.getElementById('colorModeSelect');
        if (sel) {
            sel.value = MODES.includes(saved) ? saved : 'normal';
            sel.addEventListener('change', function () {
                apply(sel.value);
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
