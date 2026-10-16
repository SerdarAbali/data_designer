/**
 * Verification-only OpenCode plugin for the Architecture Assistant feasibility
 * slice.
 *
 * It exists to prove four things on real OpenCode execution paths:
 *   1. a plugin tool executor receives an authoritative, OpenCode-supplied
 *      session id;
 *   2. the `context` session hook can run asynchronously and restrict the tool
 *      set per conversation without cross-session leakage;
 *   3. harmless architecture-shaped tools can be registered and bounded;
 *   4. nothing here has any filesystem, shell, network-fetch, or repository
 *      capability beyond writing its own verification journal.
 *
 * It never calls architecture helper endpoints and never touches application
 * code. Everything it writes stays inside the harness sandbox.
 */

import { appendFile, readFile } from "node:fs/promises"
import { Plugin } from "@opencode/plugin"

const SANDBOX =
  (globalThis as any).process?.env?.ARCHVERIFY_SANDBOX ??
  (globalThis as any).process?.cwd?.() ??
  "."
const SCOPE_FILE = `${SANDBOX}/.verify-scopes.json`
const HOOK_LOG = `${SANDBOX}/.verify-hook-log.jsonl`
const TOOL_LOG = `${SANDBOX}/.verify-tool-log.jsonl`

const TOOL_NAMES = [
  "archverify_get_test_context",
  "archverify_echo_bounded_value",
  "archverify_get_test_context_second",
]

type ScopeEntry = {
  tools?: string[]
  marker?: string
  delay_ms?: number
  label?: string
  assert_action?: string
}

async function readScopes(): Promise<Record<string, ScopeEntry>> {
  try {
    const raw = await readFile(SCOPE_FILE, "utf8")
    return JSON.parse(raw) as Record<string, ScopeEntry>
  } catch {
    return {}
  }
}

async function journal(file: string, record: Record<string, unknown>): Promise<void> {
  try {
    await appendFile(file, `${JSON.stringify(record)}\n`)
  } catch {
    // Journaling must never break a tool call.
  }
}

export default Plugin.define({
  id: "verify.architecture-assistant",
  async setup(ctx) {
    try {
    await ctx.tool.transform((editor) => {
      editor.namespace({
        name: "archverify",
        description: "Verification-only Architecture Assistant tools",
      })

      editor.add({
        name: "get_test_context",
        description:
          "Return the authoritative execution context OpenCode supplies to this tool call.",
        options: { namespace: "archverify", codemode: false },
        input: {
          type: "object",
          properties: {
            workspace_id: { type: "string" },
            discipline: { type: "string" },
            note: { type: "string" },
          },
          additionalProperties: false,
        },
        execute: async (input: any, context: any) => {
          // Optional plugin-declared permission assertion. OpenCode does not
          // permission-check plugin tools automatically, so a plugin that wants
          // policy enforcement must assert an action it names itself. The scope
          // file decides the action name per session, which lets the harness
          // prove both that the action string is plugin-chosen and that a deny
          // rule blocks the call.
          const scopes = await readScopes()
          const scope = (context?.sessionID && scopes[context.sessionID]) || {}
          if (scope.assert_action) {
            try {
              await ctx.permission.assert({
                sessionID: context.sessionID,
                action: scope.assert_action,
                resources: ["*"],
                save: ["*"],
              })
              await journal(TOOL_LOG, {
                tool: "get_test_context",
                at: Date.now(),
                assert_action: scope.assert_action,
                assert_result: "allowed",
              })
            } catch (error: any) {
              await journal(TOOL_LOG, {
                tool: "get_test_context",
                at: Date.now(),
                assert_action: scope.assert_action,
                assert_result: "denied",
                message: String(error?.message ?? error),
              })
              throw error
            }
          }
          const payload = {
            sessionID: context?.sessionID ?? null,
            agent: context?.agent ?? null,
            messageID: context?.messageID ?? null,
            callID: context?.id ?? null,
            receivedInput: input ?? null,
            // Deliberately echo caller-supplied "scope" so the harness can prove
            // it is never treated as authority by the application.
            callerSuppliedWorkspace: input?.workspace_id ?? null,
            callerSuppliedDiscipline: input?.discipline ?? null,
          }
          await journal(TOOL_LOG, { tool: "get_test_context", at: Date.now(), ...payload })
          return { content: JSON.stringify(payload) }
        },
      })

      editor.add({
        name: "echo_bounded_value",
        description: "Echo a bounded value back to the caller.",
        options: { namespace: "archverify", codemode: false },
        input: {
          type: "object",
          properties: {
            value: { type: "string" },
            size: { type: "integer" },
          },
          required: ["value"],
          additionalProperties: false,
        },
        execute: async (input: any, context: any) => {
          const size = Number(input?.size ?? 0)
          const padding = Number.isFinite(size) && size > 0 ? "x".repeat(size) : ""
          const content = `${input?.value ?? ""}${padding}`
          await journal(TOOL_LOG, {
            tool: "echo_bounded_value",
            at: Date.now(),
            sessionID: context?.sessionID ?? null,
            returned_chars: content.length,
          })
          return { content }
        },
      })

      editor.add({
        name: "get_test_context_second",
        description: "Second scoped verification tool used for scope-isolation checks.",
        options: { namespace: "archverify", codemode: false },
        input: {
          type: "object",
          properties: { tag: { type: "string" } },
          additionalProperties: false,
        },
        execute: async (input: any, context: any) => {
          const payload = {
            sessionID: context?.sessionID ?? null,
            tag: input?.tag ?? null,
          }
          await journal(TOOL_LOG, { tool: "get_test_context_second", at: Date.now(), ...payload })
          return { content: JSON.stringify(payload) }
        },
      })

      // Introspection for the harness: what the editor holds right after add().
      void journal(HOOK_LOG, {
        kind: "editor_after_add",
        ids: editor.list().map((tool: any) => tool.id),
        ours: editor
          .list()
          .filter((tool: any) => String(tool.id).startsWith("archverify_"))
          .map((tool: any) => ({
            id: tool.id,
            keys: Object.keys(tool),
            options: tool.options,
            name: tool.name,
            namespace: tool.namespace,
            enabled: tool.enabled,
            source: tool.source,
            schemaType: (tool.input as any)?.type,
            hasExecute: typeof tool.execute,
          })),
        builtinRead: editor
          .list()
          .filter((tool: any) => tool.id === "read")
          .map((tool: any) => ({ keys: Object.keys(tool), options: tool.options, enabled: tool.enabled })),
      })
    })

    // Introspection for the harness: what the registry reports after the transform.
    const registered = await ctx.tool.list()
    await journal(HOOK_LOG, {
      kind: "registry_after_transform",
      ids: registered.map((tool: any) => tool.id),
    })

    // ----------------------------------------------------------------
    // Per-conversation tool restriction.
    //
    // The hook is asynchronous on purpose: it performs a real awaited I/O step
    // (reading the scope file, then an optional awaited delay) so that the
    // harness can prove OpenCode awaits the hook before dispatching the model
    // request rather than racing it.
    // ----------------------------------------------------------------
    await ctx.session.hook("context", async (event: any) => {
      const started = Date.now()
      const sessionID = event?.sessionID ?? null
      const tools = event?.tools ?? {}
      const before = Object.keys(tools)
      const scopes = await readScopes()
      const scope = (sessionID && scopes[sessionID]) || {}
      const delay = Number(scope.delay_ms ?? 0)
      if (delay > 0) await new Promise((resolve) => setTimeout(resolve, delay))

      const allowed = scope.tools ?? TOOL_NAMES
      const removed: string[] = []
      for (const name of before) {
        if (!name.startsWith("archverify_")) continue
        if (!allowed.includes(name)) {
          delete tools[name]
          removed.push(name)
        }
      }

      await journal(HOOK_LOG, {
        kind: "context",
        sessionID,
        marker: scope.marker ?? null,
        label: scope.label ?? null,
        tools_before: before,
        tools_after: Object.keys(tools),
        removed,
        delay_ms: delay,
        started,
        ended: Date.now(),
      })
    })

    await journal(HOOK_LOG, { kind: "setup", at: Date.now(), tools: TOOL_NAMES })
    } catch (error: any) {
      await journal(HOOK_LOG, {
        kind: "setup_error",
        message: String(error?.stack ?? error?.message ?? error),
      })
    }
  },
})
