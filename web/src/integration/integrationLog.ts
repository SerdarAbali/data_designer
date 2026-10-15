export type IntegrationLogEntry = {
  at: string;
  level: "info" | "error";
  action: string;
  detail?: unknown;
};

const buffer: IntegrationLogEntry[] = [];
const MAX_ENTRIES = 200;

declare global {
  interface Window {
    __integrationWorkbenchLog?: IntegrationLogEntry[];
  }
}

function record(level: IntegrationLogEntry["level"], action: string, detail?: unknown) {
  const entry: IntegrationLogEntry = { at: new Date().toISOString(), level, action, detail };
  buffer.push(entry);
  if (buffer.length > MAX_ENTRIES) buffer.shift();
  if (typeof window !== "undefined") window.__integrationWorkbenchLog = buffer;
  const logger = level === "error" ? console.error : console.info;
  logger(`[integration-workbench] ${action}`, detail ?? "");
}

export const integrationLog = {
  info(action: string, detail?: unknown) {
    record("info", action, detail);
  },
  error(action: string, detail?: unknown) {
    record("error", action, detail);
  },
  entries(): IntegrationLogEntry[] {
    return [...buffer];
  },
};
