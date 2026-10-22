// Dev-only log viewer. Toggle with the backtick key or the "logs" button.
// Only imported when import.meta.env.DEV is true.

import { clearLogs, formatEntry, getLogs, LEVELS, onLog, type Level, type LogEntry } from './lib/logger';

const MAX_ROWS = 500;

function download(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export function mountLogViewer() {
  const toggle = document.createElement('button');
  toggle.className = 'devlog-toggle';
  toggle.textContent = 'logs';
  toggle.setAttribute('aria-label', 'Toggle dev log viewer');

  const panel = document.createElement('section');
  panel.className = 'devlog';
  panel.hidden = true;
  panel.setAttribute('aria-label', 'Dev log viewer');
  panel.innerHTML = `
    <header>
      <select data-level aria-label="Minimum level">${LEVELS.map((l) => `<option${l === 'DEBUG' ? ' selected' : ''}>${l}</option>`).join('')}</select>
      <select data-module aria-label="Module filter"><option value="">all modules</option></select>
      <button data-txt aria-label="Export logs as text">.txt</button>
      <button data-json aria-label="Export logs as JSON">.json</button>
      <button data-clear aria-label="Clear logs">clear</button>
    </header>
    <pre data-rows></pre>`;
  document.body.append(toggle, panel);

  const levelSel = panel.querySelector<HTMLSelectElement>('[data-level]')!;
  const moduleSel = panel.querySelector<HTMLSelectElement>('[data-module]')!;
  const rows = panel.querySelector<HTMLPreElement>('[data-rows]')!;
  const modules = new Set<string>();

  const visible = (e: LogEntry) =>
    LEVELS.indexOf(e.level) >= LEVELS.indexOf(levelSel.value as Level) && (!moduleSel.value || e.module === moduleSel.value);

  function noteModule(m: string) {
    if (modules.has(m)) return;
    modules.add(m);
    moduleSel.add(new Option(m, m));
  }

  function redraw() {
    if (panel.hidden) return;
    const shown = getLogs().filter(visible).slice(-MAX_ROWS);
    rows.textContent = shown.length ? shown.map(formatEntry).join('\n') : 'No log entries match.';
    rows.scrollTop = rows.scrollHeight;
  }

  getLogs().forEach((e) => noteModule(e.module));
  onLog((e) => {
    noteModule(e.module);
    if (visible(e)) redraw();
  });

  const flip = () => {
    panel.hidden = !panel.hidden;
    redraw();
  };
  toggle.addEventListener('click', flip);
  window.addEventListener('keydown', (e) => {
    if (e.key === '`') flip();
  });
  levelSel.addEventListener('change', redraw);
  moduleSel.addEventListener('change', redraw);
  panel.querySelector('[data-clear]')!.addEventListener('click', () => {
    clearLogs();
    redraw();
  });
  panel.querySelector('[data-txt]')!.addEventListener('click', () =>
    download('terrarium-log.txt', getLogs().map(formatEntry).join('\n'), 'text/plain'));
  panel.querySelector('[data-json]')!.addEventListener('click', () =>
    download('terrarium-log.json', JSON.stringify(getLogs(), null, 2), 'application/json'));
}
