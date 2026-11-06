(() => {
  const key = 'pinlite-next.theme.v1';
  const themes = {
    classic: null,
    dark: '/static/themes/dark.css',
    oldweb: '/static/themes/oldweb.css',
    terminal: '/static/themes/terminal.css',
    parchment: '/static/themes/parchment.css',
    ao3: '/static/themes/ao3.css',
    geocities: '/static/themes/geocities.css',
  };

  let selected = 'classic';
  try {
    const saved = localStorage.getItem(key);
    if (Object.hasOwn(themes, saved)) selected = saved;
  } catch {}

  document.write(
    '<link id="theme-stylesheet" rel="stylesheet"' +
    (themes[selected] ? ` href="${themes[selected]}"` : '') +
    '>'
  );

  document.addEventListener('DOMContentLoaded', () => {
    const stylesheet = document.getElementById('theme-stylesheet');
    const select = document.getElementById('theme');
    select.value = selected;

    select.addEventListener('change', () => {
      selected = select.value;
      if (!Object.hasOwn(themes, selected)) return;

      if (themes[selected]) {
        stylesheet.href = themes[selected];
      } else {
        stylesheet.removeAttribute('href');
      }

      try {
        localStorage.setItem(key, selected);
      } catch {}
    });
  });
})();