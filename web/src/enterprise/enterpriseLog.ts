export type EnterpriseLogEntry = {
  at: string;
  level: "info" | "error";
  action: string;
  detail?: unknown;
};

const buffer: EnterpriseLogEntry[] = [];
const MAX_ENTRIES = 200;

declare global {
  interface Window {
    __enterpriseWorkbenchLog?: EnterpriseLogEntry[];
  }
}

function record(level: EnterpriseLogEntry["level"], action: string, detail?: unknown) {
  const entry: EnterpriseLogEntry = { at: new Date().toISOString(), level, action, detail };
  buffer.push(entry);
  if (buffer.length > MAX_ENTRIES) buffer.shift();
  if (typeof window !== "undefined") window.__enterpriseWorkbenchLog = buffer;
  const logger = level === "error" ? console.error : console.info;
  logger(`[enterprise-workbench] ${action}`, detail ?? "");
}

export const enterpriseLog = {
  info(action: string, detail?: unknown) {
    record("info", action, detail);
  },
  error(action: string, detail?: unknown) {
    record("error", action, detail);
  },
  entries(): EnterpriseLogEntry[] {
    return [...buffer];
  },
};
