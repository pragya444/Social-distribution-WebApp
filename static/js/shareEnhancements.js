// Minimal share auto-copy (no id / label changes).
(function () {
  const iconSelector = '.share-icon';
  const textSelector = '.share-text';
  const linkSelector = '.share-link';
  const msgSelector = '.share-copied-msg';

  function getURL() {
    const el = document.querySelector(linkSelector);
    if (!el) return '';
    return ('value' in el) ? el.value.trim() : (el.textContent || '').trim();
  }

  function showMsg() {
    const m = document.querySelector(msgSelector);
    if (m) m.style.display = 'block';
  }

  function copy(url) {
    if (!url) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(showMsg).catch(fallback);
    } else {
      fallback();
    }
    function fallback() {
      const el = document.querySelector(linkSelector);
      if (el && el.select) {
        el.select();
        try { document.execCommand('copy'); } catch (_) {}
        showMsg();
      }
    }
  }

  function handle(e) {
    e.preventDefault();
    copy(getURL());
  }

  function init() {
    const icon = document.querySelector(iconSelector);
    const text = document.querySelector(textSelector);
    if (icon && !icon.__bound) { icon.addEventListener('click', handle); icon.__bound = true; icon.style.cursor='pointer'; }
    if (text && !text.__bound) { text.addEventListener('click', handle); text.__bound = true; text.style.cursor='pointer'; }

    // Auto-copy once if desired when page loads (optional; comment out if not wanted):
    copy(getURL());
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();