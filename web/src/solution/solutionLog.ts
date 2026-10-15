export type SolutionLogEntry = {
  at: string;
  level: "info" | "error";
  action: string;
  detail?: unknown;
};

const buffer: SolutionLogEntry[] = [];
const MAX_ENTRIES = 200;

declare global {
  interface Window {
    __solutionDesignerLog?: SolutionLogEntry[];
  }
}

function record(level: SolutionLogEntry["level"], action: string, detail?: unknown) {
  const entry: SolutionLogEntry = { at: new Date().toISOString(), level, action, detail };
  buffer.push(entry);
  if (buffer.length > MAX_ENTRIES) buffer.shift();
  if (typeof window !== "undefined") window.__solutionDesignerLog = buffer;
  const logger = level === "error" ? console.error : console.info;
  logger(`[solution-designer] ${action}`, detail ?? "");
}

export const solutionLog = {
  info(action: string, detail?: unknown) {
    record("info", action, detail);
  },
  error(action: string, detail?: unknown) {
    record("error", action, detail);
  },
  entries(): SolutionLogEntry[] {
    return [...buffer];
  },
};
