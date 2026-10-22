export type Level = 'TRACE' | 'DEBUG' | 'INFO' | 'WARN' | 'ERROR';

export const LEVELS: Level[] = ['TRACE', 'DEBUG', 'INFO', 'WARN', 'ERROR'];

export interface LogEntry {
  time: number;
  level: Level;
  module: string;
  message: string;
  data?: unknown;
}

const RING_SIZE = 2000;
const ring: LogEntry[] = [];
const listeners = new Set<(entry: LogEntry) => void>();

// VITE_LOG_LEVEL overrides; otherwise DEBUG+ in dev, WARN+ in prod
const envLevel = import.meta.env.VITE_LOG_LEVEL as Level | undefined;
const threshold = LEVELS.indexOf(
  envLevel && LEVELS.includes(envLevel) ? envLevel : import.meta.env.DEV ? 'DEBUG' : 'WARN',
);

const consoleFor: Record<Level, (...args: unknown[]) => void> = {
  TRACE: console.debug,
  DEBUG: console.debug,
  INFO: console.info,
  WARN: console.warn,
  ERROR: console.error,
};

// Errors don't survive JSON.stringify, so flatten them up front
function normalise(data: unknown): unknown {
  if (data instanceof Error) return { name: data.name, message: data.message, stack: data.stack };
  return data;
}

function emit(level: Level, module: string, message: string, data?: unknown) {
  if (LEVELS.indexOf(level) < threshold) return;
  const entry: LogEntry = { time: Date.now(), level, module, message, data: normalise(data) };
  ring.push(entry);
  if (ring.length > RING_SIZE) ring.shift();

  const line = `[${level}] [${module}] ${message}`;
  if (data === undefined) consoleFor[level](line);
  else consoleFor[level](line, data);

  for (const fn of listeners) fn(entry);
}

export function createLogger(module: string) {
  return {
    trace: (message: string, data?: unknown) => emit('TRACE', module, message, data),
    debug: (message: string, data?: unknown) => emit('DEBUG', module, message, data),
    info: (message: string, data?: unknown) => emit('INFO', module, message, data),
    warn: (message: string, data?: unknown) => emit('WARN', module, message, data),
    error: (message: string, data?: unknown) => emit('ERROR', module, message, data),
  };
}

export function getLogs(): LogEntry[] {
  return ring.slice();
}

export function clearLogs() {
  ring.length = 0;
}

export function onLog(fn: (entry: LogEntry) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function formatEntry(e: LogEntry): string {
  const d = new Date(e.time);
  const time = `${d.toTimeString().slice(0, 8)}.${String(d.getMilliseconds()).padStart(3, '0')}`;
  const data = e.data === undefined ? '' : ' ' + JSON.stringify(e.data);
  return `${time} [${e.level}] [${e.module}] ${e.message}${data}`;
}
