// Theme bootstrap: runs before first paint (classic script in <head>, CSP-safe).
// data-theme-pref = user choice (system | light | dark); data-theme = resolved theme.
(() => {
  const KEY = 'ccon-theme';
  const root = document.documentElement;
  const media = window.matchMedia ? matchMedia('(prefers-color-scheme: dark)') : null;
  const read = () => {
    try {
      const value = localStorage.getItem(KEY);
      return value === 'light' || value === 'dark' ? value : 'system';
    } catch {
      return 'system';
    }
  };
  const apply = () => {
    const pref = read();
    root.dataset.themePref = pref;
    root.dataset.theme = pref === 'system' ? (media && media.matches ? 'dark' : 'light') : pref;
    root.style.colorScheme = root.dataset.theme;
  };
  apply();
  if (media && media.addEventListener) media.addEventListener('change', apply);
  window.cconTheme = {
    get: read,
    set(pref) {
      try {
        if (pref === 'system') localStorage.removeItem(KEY);
        else localStorage.setItem(KEY, pref);
      } catch { /* storage unavailable: theme still applies for this page */ }
      apply();
      return root.dataset.theme;
    },
  };
})();
