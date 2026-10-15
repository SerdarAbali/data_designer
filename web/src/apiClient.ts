/**
 * Single shared HTTP client for every studio surface.
 *
 * The studio previously carried six near-identical `csrfToken`/`api`/`list`
 * triples (canvas, catalog, integration workspace, landscape, scenarios,
 * imports). They now all funnel through this module so CSRF, JSON headers,
 * error shaping and pagination behave identically everywhere.
 */

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(message: string, status: number, detail: unknown = undefined) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export function csrfToken(): string {
  const raw = document.cookie.split("; ").find((item) => item.startsWith("dd_csrf="))?.slice(8);
  if (!raw) throw new Error("Your session could not be verified. Reload and try again.");
  return decodeURIComponent(raw);
}

type ApiDetailIssue = { path?: string; message?: string; msg?: string };

/**
 * Best-effort human message for a FastAPI `detail` payload. Handles the
 * shapes the studio actually produces: a plain string, a Pydantic validation
 * list, or a structured object with `message`/`code`/`issues`/`integrations`.
 */
export function describeApiDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (item && typeof item === "object" && "msg" in item) {
        return String((item as { msg?: unknown }).msg).replace(/^Value error, /, "");
      }
      return JSON.stringify(item);
    }).filter(Boolean);
    if (parts.length === 0) return "";
    const [first, ...rest] = parts;
    return rest.length > 0 ? `${first} (+${rest.length} more)` : first;
  }
  if (detail && typeof detail === "object") {
    const record = detail as {
      message?: unknown;
      code?: unknown;
      issues?: ApiDetailIssue[];
      integrations?: { name?: string }[];
    };
    if (record.issues?.length) {
      return record.issues
        .map((issue) => `${issue.path ?? "value"}: ${issue.message ?? issue.msg ?? ""}`.trim())
        .join("; ");
    }
    const message =
      typeof record.message === "string"
        ? record.message
        : typeof record.code === "string"
          ? record.code
          : JSON.stringify(detail);
    if (record.integrations?.length) {
      return `${message}: ${record.integrations.map((item) => item.name ?? "contract").join(", ")}`;
    }
    return message;
  }
  return "";
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (init.method && init.method !== "GET") headers.set("X-CSRF-Token", csrfToken());
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
    const message = describeApiDetail(body.detail) || `Request failed (${response.status}).`;
    throw new ApiError(message, response.status, body.detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Fetch every page of a list endpoint using the studio-wide 500-row page size. */
export async function list<T>(path: string): Promise<T[]> {
  const records: T[] = [];
  let offset = 0;
  const separator = path.includes("?") ? "&" : "?";
  while (true) {
    const page = await api<T[]>(`${path}${separator}limit=500&offset=${offset}`);
    records.push(...page);
    if (page.length < 500) return records;
    offset += page.length;
  }
}
