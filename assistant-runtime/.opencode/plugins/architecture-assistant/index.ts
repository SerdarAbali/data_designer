/**
 * Restricted Architecture Assistant plugin — Slice B foundation.
 *
 * Slice B ships exactly one startup-probe-only tool. It has no architecture
 * tools, no helper-action access, no filesystem, shell, network-fetch, or
 * repository capability. Later slices add the real architecture_* tools; the
 * security shape here is what those tools must follow.
 *
 * Security invariants this file must preserve:
 *   - every tool declares `options.codemode: false` (Slice A blocking defect:
 *     without it the tool is registered but never offered to the model);
 *   - every tool is namespaced (`architecture_*`) so the profile's explicit
 *     allow rules and the backend allowlist can address it by its effective
 *     tool name;
 *   - registration fails closed: if setup throws, no tool is registered;
 *   - tool output is bounded and contains no secrets, paths, or instructions.
 */

import { Plugin } from "@opencode/plugin"

export default Plugin.define({
  id: "architecture-assistant",
  async setup(ctx) {
    try {
      await ctx.tool.transform((editor) => {
        editor.namespace({
          name: "architecture",
          description: "Architecture Assistant tools",
        })

        editor.add({
          name: "probe_context",
          description:
            "Startup-probe-only tool. Returns the OpenCode-supplied execution context as bounded, non-sensitive data.",
          options: { namespace: "architecture", codemode: false },
          input: {
            type: "object",
            properties: {},
            additionalProperties: false,
          },
          execute: async (_input: unknown, context: any) => {
            const payload = {
              ok: true,
              sessionID: context?.sessionID ?? null,
              agent: context?.agent ?? null,
            }
            return { content: JSON.stringify(payload) }
          },
        })
      })
    } catch {
      // Fail closed: if registration fails for any reason, register no tools.
    }
  },
})
