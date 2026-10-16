# assistant-runtime

Pinned, restricted OpenCode runtime for the Architecture Assistant
(`implementation_plan_opencode_agent.md`, Slice B).

Nothing in this directory is user code or architecture logic. It exists only to
run a locked-down OpenCode server that the application backend talks to over a
private Compose network.

## Contents

| Path | Purpose |
|---|---|
| `Dockerfile` | Pins OpenCode `v2.0.30` (`@opencode/cli@2.0.30`), asserts the version at build time, and runs `opencode serve` with no host port. |
| `opencode.json` | Restricted profile: `deny *` plus one explicit allow, no `ask` rules, explicit `steps: 12`, built-in agents disabled, `update: "disable"`, snapshots/formatter/MCP off, reduced `tool_output`. |
| `assistant-tools.json` | Declared tool manifest the startup capability probe validates (namespaced names, `codemode: false`, explicit allow rule). |
| `.opencode/plugins/architecture-assistant/index.ts` | Minimal plugin registering exactly one startup-probe tool. No architecture tools yet. |

## Security posture

* **No host port.** The Compose service uses `expose` only; it is reachable only
  by the `api` service on the internal network.
* **HTTP Basic auth.** Username `opencode`, password from server-side secret
  material (`OPENCODE_PASSWORD`). The password never reaches the browser.
* **Deny by default.** `permissions: [{action: "*", resource: "*", effect: "deny"}]`
  removes every built-in capability (shell, read, write, edit, patch, glob,
  grep, webfetch, websearch, subagent, skill, question, Code Mode `execute`).
* **No `ask` rules.** An `ask` outcome can block a turn on an interactive prompt
  the browser must never see, so only `allow`/`deny` are used. The capability
  probe asserts the profile contains no `ask` effect.
* **`codemode: false` on every tool.** Without it a plugin tool is registered but
  never offered to the model (the Slice A blocking defect). The probe fails
  closed if any declared tool omits it.
* **Sensitive data directory.** All XDG state lives under `/data`, a bounded
  volume. It is never mounted into another container or served by any route.

## Building

The image is built by Compose (`opencode` service). The build requires network
access to npm to fetch the pinned `@opencode/cli@2.0.30` package. A version
mismatch fails the build.

The repository itself is not modified by this directory.
