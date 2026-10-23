// Puts the chosen color theme on <html> before the page paints (a blocking script in <head>),
// so a dark theme never flashes white. "system" follows the OS and keeps following it.
// app.js switches themes with window.clidaTheme(name); each switch fires a "clida-theme" event.
(() => {
  const dark = matchMedia('(prefers-color-scheme: dark)');
  let chosen = 'system';
  const apply = () => {
    document.documentElement.dataset.theme = chosen === 'system' ? (dark.matches ? 'dark' : 'light') : chosen;
    window.dispatchEvent(new Event('clida-theme'));
  };
  window.clidaTheme = (name) => {
    chosen = name || 'system';
    apply();
  };
  dark.addEventListener('change', () => { if (chosen === 'system') apply(); });
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem('desk.theme')); } catch { /* storage unavailable */ }
  window.clidaTheme(saved);
})();
