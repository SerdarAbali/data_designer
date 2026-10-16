/**
 * Restricted Architecture Assistant plugin (proposal + read tools).
 *
 * Tool definitions (name, description, strict JSON Schema) come from the
 * generated manifest baked into the image at /sandbox/assistant-tools.json. The
 * backend remains authoritative: every call is proxied to
 * /internal/assistant/call, re-validated there, and scoped from the OpenCode
 * session id. The plugin holds no business logic and no capability of its own.
 *
 * Security invariants:
 *   - every tool declares `options.codemode: false` (Slice A blocking defect);
 *   - registration fails closed: if the manifest cannot be read, no tool is
 *     registered;
 *   - the `context` hook resolves scope from the session id via the backend and
 *     removes every out-of-scope tool; if scope cannot be resolved, all
 *     architecture tools are removed for that request;
 *   - approve/apply/undo are never registered (they are absent from the backend
 *     registry, so they cannot appear here).
 */

import { readFileSync } from "node:fs"
import { Plugin } from "@opencode/plugin"

const BACKEND = (globalThis as any).process?.env?.ARCHITECTURE_BACKEND_URL ?? ""
const TOKEN = (globalThis as any).process?.env?.ARCHITECTURE_SERVICE_TOKEN ?? ""
const TOOLS_PATH =
  (globalThis as any).process?.env?.ARCHITECTURE_TOOLS_PATH ?? "/sandbox/assistant-tools.json"

type ToolSpec = {
  name: string
  kind?: string
  codemode?: boolean
  description?: string
  schema?: Record<string, unknown>
}

function loadTools(): ToolSpec[] {
  try {
    const parsed = JSON.parse(readFileSync(TOOLS_PATH, "utf8"))
    if (!parsed || !Array.isArray(parsed.tools)) return []
    return parsed.tools.filter(
      (tool: ToolSpec) =>
        typeof tool?.name === "string" &&
        tool.name.startsWith("architecture_") &&
        tool.codemode === false &&
        tool.schema &&
        typeof tool.schema === "object",
    )
  } catch {
    return []
  }
}

function headers(): Record<string, string> {
  return { "Content-Type": "application/json", "X-Assistant-Service-Token": TOKEN }
}

async function fetchJson(url: string, init?: RequestInit): Promise<any | null> {
  if (!BACKEND || !TOKEN) return null
  try {
    const response = await fetch(url, init)
    if (!response.ok) return null
    return await response.json()
  } catch {
    return null
  }
}

async function backendScope(sessionID: string): Promise<string[] | null> {
  const payload = await fetchJson(
    `${BACKEND}/internal/assistant/scope?session=${encodeURIComponent(sessionID)}`,
    { headers: headers() },
  )
  if (!payload || payload.status !== "ok" || !Array.isArray(payload.tools)) return null
  return payload.tools as string[]
}

async function backendCall(
  sessionID: string,
  callID: string,
  tool: string,
  args: unknown,
): Promise<{ status: string; error_code?: string | null; result?: unknown }> {
  const payload = await fetchJson(`${BACKEND}/internal/assistant/call`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      opencode_session_id: sessionID,
      call_id: callID,
      tool,
      arguments: args ?? {},
    }),
  })
  if (!payload) return { status: "error", error_code: "backend_unreachable" }
  return payload
}

export default Plugin.define({
  id: "architecture-assistant",
  async setup(ctx) {
    try {
      const tools = loadTools()
      if (tools.length === 0) return

      await ctx.tool.transform((editor) => {
        editor.namespace({
          name: "architecture",
          description: "Architecture Assistant tools",
        })
        for (const spec of tools) {
          const bare = spec.name.replace(/^architecture_/, "")
          editor.add({
            name: bare,
            description: spec.description ?? "Architecture Assistant tool.",
            options: { namespace: "architecture", codemode: false },
            input: spec.schema,
            execute: async (input: unknown, context: any) => {
              const outcome = await backendCall(
                context?.sessionID ?? "",
                context?.id ?? "",
                spec.name,
                input,
              )
              if (outcome.status !== "ok") {
                return {
                  content: JSON.stringify({
                    error: outcome.error_code ?? "tool_error",
                    note: "This tool is not permitted in the current scope.",
                  }),
                }
              }
              return { content: JSON.stringify(outcome.result ?? {}) }
            },
          })
        }
      })

      await ctx.session.hook("context", async (event: any) => {
        const sessionID = event?.sessionID ?? ""
        const tools = event?.tools ?? {}
        const allowed = await backendScope(sessionID)
        if (allowed === null) {
          for (const name of Object.keys(tools)) {
            if (name.startsWith("architecture_")) delete tools[name]
          }
          return
        }
        const allow = new Set(allowed)
        for (const name of Object.keys(tools)) {
          if (name.startsWith("architecture_") && !allow.has(name)) delete tools[name]
        }
      })
    } catch {
      // Fail closed: register no tools if setup fails.
    }
  },
})
