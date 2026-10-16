/**
 * Restricted Architecture Assistant plugin (Slice C).
 *
 * It declares the read-only architecture tools and proxies every call to the
 * authoritative backend dispatch endpoint. The backend owns validation,
 * scoping, and result bounding; the plugin only transports.
 *
 * Tool definitions are declared statically so plugin setup never depends on the
 * backend being up (a startup race would otherwise register zero tools). The
 * backend manifest (assistant-tools.json) and this list are kept in sync by a
 * test.
 *
 * Security invariants:
 *   - every tool declares `options.codemode: false` (Slice A blocking defect);
 *   - the `context` hook resolves scope from the OpenCode session id via the
 *     backend and removes every out-of-scope tool; if scope cannot be resolved,
 *     all architecture tools are removed for that request (fail closed);
 *   - tool output is whatever the backend returns: bounded and redacted.
 */

import { Plugin } from "@opencode/plugin"

const BACKEND = (globalThis as any).process?.env?.ARCHITECTURE_BACKEND_URL ?? ""
const TOKEN = (globalThis as any).process?.env?.ARCHITECTURE_SERVICE_TOKEN ?? ""

const OBJECT_SCHEMA = {
  type: "object",
  properties: { object_id: { type: "string" }, limit: { type: "integer", minimum: 1, maximum: 25 } },
  required: ["object_id"],
  additionalProperties: false,
}
const LIMIT_SCHEMA = {
  type: "object",
  properties: { limit: { type: "integer", minimum: 1, maximum: 25 } },
  additionalProperties: false,
}
const EMPTY_SCHEMA = { type: "object", properties: {}, additionalProperties: false }
const CONTRACT_SCHEMA = {
  type: "object",
  properties: { contract_id: { type: "string" } },
  required: ["contract_id"],
  additionalProperties: false,
}

type ToolSpec = { name: string; description: string; schema: Record<string, unknown> }

const TOOLS: ToolSpec[] = [
  { name: "architecture_get_workspace_context", description: "Read workspace name, description, enabled disciplines, and states. Read-only.", schema: EMPTY_SCHEMA },
  { name: "architecture_get_enabled_disciplines", description: "List enabled architecture disciplines. Read-only.", schema: EMPTY_SCHEMA },
  { name: "architecture_get_architecture_state", description: "Read a bounded preview of the active architecture state. Read-only.", schema: LIMIT_SCHEMA },
  { name: "architecture_search_canonical_objects", description: "Search canonical architecture objects by name/kind. Read-only.", schema: { type: "object", properties: { query: { type: "string" }, kind: { type: "string" }, limit: { type: "integer", minimum: 1, maximum: 25 } }, additionalProperties: false } },
  { name: "architecture_get_object_details", description: "Read a canonical object's details and state membership. Read-only.", schema: OBJECT_SCHEMA },
  { name: "architecture_get_object_relationships", description: "List stored typed relationships for an object. Read-only.", schema: OBJECT_SCHEMA },
  { name: "architecture_get_object_usages", description: "List how an object is used in the active state. Read-only.", schema: OBJECT_SCHEMA },
  { name: "architecture_trace_architecture_path", description: "Trace bounded connectivity from an object. Read-only.", schema: { type: "object", properties: { object_id: { type: "string" }, direction: { type: "string", enum: ["both", "outgoing", "incoming"] }, depth: { type: "integer", minimum: 1, maximum: 2 }, limit: { type: "integer", minimum: 1, maximum: 25 } }, required: ["object_id"], additionalProperties: false } },
  { name: "architecture_compare_current_candidate", description: "Compare the active candidate against Current. Read-only.", schema: LIMIT_SCHEMA },
  { name: "architecture_list_catalog_systems", description: "List Catalog systems. Read-only.", schema: LIMIT_SCHEMA },
  { name: "architecture_inspect_catalog_schema", description: "Inspect bounded Catalog fields. Read-only.", schema: { type: "object", properties: { system_id: { type: "string" }, object_id: { type: "string" }, limit: { type: "integer", minimum: 1, maximum: 25 } }, additionalProperties: false } },
  { name: "architecture_list_integration_contracts", description: "List integration Contracts. Read-only.", schema: LIMIT_SCHEMA },
  { name: "architecture_inspect_contract", description: "Inspect one Contract. Read-only.", schema: CONTRACT_SCHEMA },
  { name: "architecture_inspect_mapping_coverage", description: "Inspect Contract mapping coverage. Read-only.", schema: CONTRACT_SCHEMA },
  { name: "architecture_inspect_scenarios_and_conformance", description: "Inspect scenarios and conformance for a Contract. Read-only.", schema: { type: "object", properties: { contract_id: { type: "string" }, limit: { type: "integer", minimum: 1, maximum: 25 } }, required: ["contract_id"], additionalProperties: false } },
]

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
      await ctx.tool.transform((editor) => {
        editor.namespace({
          name: "architecture",
          description: "Architecture Assistant read-only tools",
        })
        for (const spec of TOOLS) {
          const bare = spec.name.replace(/^architecture_/, "")
          editor.add({
            name: bare,
            description: spec.description,
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
                    note: "This read tool is not permitted in the current scope.",
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
