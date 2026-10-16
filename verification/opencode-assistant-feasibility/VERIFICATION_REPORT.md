# OpenCode Feasibility & Security Verification — Slice A report

Slice: **OpenCode feasibility and security verification** for the Architecture
Assistant (the first slice of `implementation_plan_opencode_agent.md`).

Status: **complete**. Harness, tests, and evidence are under
`verification/opencode-assistant-feasibility/`. No application file was changed;
no migration, dependency, service, or UI was added.

---

## 1. Versions verified

| Component | Version / value | Evidence |
|---|---|---|
| OpenCode | `v2.0.30` (`opencode --version`; `GET /api/info` → `{"version":"2.0.30"}`) | `artifacts/versions.txt`, `artifacts/pytest.txt` |
| OpenCode HTTP API document | OpenAPI `3.1.0`, `info.title = "opencode HttpApi"`, `info.version = "0.0.1"`, 142 operations | `GET /openapi.json` on the isolated server |
| OpenCode server surface used | `opencode serve --hostname <h> --port <p>` | `runtime/harness.py` |
| Node (host) | `v20.19.2` | `artifacts/versions.txt` |
| Docker / Compose | Docker `26.1.5+dfsg1`, Compose `2.26.1-4` | `artifacts/versions.txt` |
| Host platform | Debian 13 (trixie) aarch64, 4 cores | `docs/host-environment.md` |
| Test suite | **21 tests, 21 passed, 38 s** | `artifacts/pytest.txt` |
| Compose exposure proof | **PASS** (0 published host ports, host cannot connect, sibling container reaches it, 401 without auth) | `artifacts/compose-proof.txt` |
| Model used during verification | scripted local mock (`mock/mock-tool-model`), no real provider or credential | `runtime/mock_provider.py` |

Isolation: dedicated `XDG_*` directories per server, own database, own port,
scratch sandbox containing only the profile and the verification plugin. The
developer's live OpenCode service and the application were never contacted.

---

## 2. Answers to the ten verification questions

### Q1 — Does a plugin tool executor reliably receive the authoritative session ID? **YES**

`context.sessionID` inside the tool executor equals the session ID returned by
`POST /api/session`. It is supplied by OpenCode's execution context, not by the
model or the tool arguments.

Evidence (`test_01`): the plugin tool returned
`{"sessionID":"ses_eba2…","agent":"architecture-assistant","messageID":"msg_…","callID":"call_…"}`
and the returned `sessionID` matched the API-created session exactly. The same
identity is available in the `context` hook as `event.sessionID` (`test_02`,
`test_03`), so the backend can resolve tenant/workspace/state/discipline from its
own row keyed by an OpenCode-supplied ID.

### Q2 — Is the session/context hook asynchronous, and can it restrict tools per conversation without races or leakage? **YES**

* The `context` hook may be `async`. The harness hook awaits a real filesystem
  read plus a configurable delay; `test_02` asserts the delay is actually awaited
  (`ended - started ≥ 850 ms` for a 900 ms delay) **and** that the first provider
  request happened only after the hook finished. OpenCode waits for the hook
  rather than racing it.
* Tool restriction works by deleting keys from `event.tools`. `test_02` observed
  `tools_before = [all three verification tools]` → `tools_after = [scoped tool]`
  with the other two in `removed`, and the model was offered exactly the scoped
  tool.
* No cross-session leakage: `test_03` runs two conversations concurrently with
  different scopes and delays. Each hook record carries its own conversation's
  marker and its own tool subset, no record mixed the two, and each tool call
  reported its own session ID.

### Q3 — What permission action/identifier is produced for plugin tools? **The effective (namespaced) tool name; no automatic per-call request**

* A plugin tool is matched by its **effective tool name** (`archverify_get_test_context`),
  not by the bare name (`get_test_context`) and not by a wildcard action.
  `test_04`: with `deny *` plus `allow archverify_get_test_context`, that tool is
  offered and runs while its sibling `archverify_get_test_context_second` and all
  built-ins are unavailable.
* Denial happens at **tool-set assembly**: a denied plugin tool disappears from
  the offered tool list, and a call to it fails with
  `No tool named "…" is currently available`.
* A plugin tool removed by the `context` hook fails with the distinct message
  `Tool is not available for this request: <name>`. The gateway must map both.
* `effect: "ask"` does **not** produce an interactive prompt for plugin tools
  (observed: the tool ran with `ask` configured and no permission request was
  created). `ask` therefore cannot be used to gate plugin tools; use `allow`/`deny`.
* A plugin can opt into per-call policy enforcement by calling
  `ctx.permission.assert({sessionID, action, resources})` with an action string
  **it chooses**. `test_05` proves both directions: an `allow` rule for
  `archverify.read_context` lets the call through, and a `deny` rule makes the
  call fail with `Permission denied: archverify.read_context`.
* Built-in tools *do* create per-call permission requests when the outcome is
  `ask` (`action: "shell"`, `resources: ["id"]`, `save: ["id *"]`), and an
  unanswered request blocks the turn — so `ask` must never be used unattended.

### Q4 — Can all built-in capabilities be denied? **YES, completely**

With the top-level rule `{"action":"*","resource":"*","effect":"deny"}` plus
per-agent allows for the verification tools:

* The model is offered **only** the three verification tools. `shell`, `read`,
  `write`, `edit`, `patch`, `glob`, `grep`, `webfetch`, `websearch`, `subagent`,
  `skill`, `question`, and `execute` (Code Mode) are absent from the request.
* Every attempted built-in call fails with `No tool named "…" is currently
  available`; none executes (`test_06`).
* Corroborating negative control: with no permission rules the same harness
  happily ran `shell` (`uid=1000(sedu)…`) and `read` (`/etc/passwd`), proving the
  denial is what removes the capability rather than a harness limitation.
* Disabling the built-in agents (`build`, `plan`, `general`, `explore`) and
  `steps` also verified: with `steps: 8` the runtime reported
  `Tools are disabled after the maximum agent steps`, so the step cap is a real
  control (the harness profile now sets `steps: 20`).

### Q5 — Can the tool list change per workspace, disciplines, state type, workbench, and conversation? **YES**

The allowed set is computed by the plugin's `context` hook from the
conversation's OpenCode session ID, refreshed on **every model request** (the
hook ran once per request in `test_02`/`test_03`). That gives full per-conversation
dynamics; workspace/discipline/state/workbench inputs map onto the same
mechanism because the hook resolves scope by session ID from backend-owned state.

* `test_07`: the model supplied `workspace_id: "attacker-ws"` and
  `discipline: "admin"` as tool arguments; the executor still reported its
  authoritative session ID, the arguments were only echoed as data, and the tool
  set still came from the session's own scope.
* `test_08`: a tool outside the conversation's scope is not callable.
* `test_06`: built-ins stay out of every request.

### Q6 — Are streaming, cancellation, session disposal, and reconnection controllable? **YES**

* Streaming: `GET /api/event` delivers live SSE events while a turn runs
  (`test_09`).
* Cancellation: `POST /api/session/{id}/interrupt` stops generation. `test_10`
  interrupts a slow streamed turn and asserts the provider was called exactly
  once (no continuation step) and the scripted follow-up text never appeared.
* Disposal: `DELETE /api/session/{id}` makes subsequent `prompt` and `get`
  return **404** (`test_11`), so a disposed conversation cannot call tools.
* Reconnection: breaking and re-subscribing yields live events again (`test_12`).
  Confirmed the documented behaviour that subscriptions are **live-only with no
  replay**, which matches the plan's design (the gateway keeps its own durable
  event log and cursor).
* Also verified: `POST /api/session/{id}/model` (model switch) and
  `POST /api/session/{id}/generate` both work (`test_15`), and
  `POST /api/experimental/session/{id}/wait` is a reliable "turn finished" signal.

### Q7 — Can OpenCode stay private inside Compose with no host port? **YES, proven**

`compose/verify.sh` builds a minimal OpenCode image from the local binary and
runs it on a private Compose network with `expose: ["4096"]` and **no `ports:`
mapping**:

* `published_host_ports=0` (Compose reports the exposed port with
  `PublishedPort: 0`);
* the host cannot connect to `127.0.0.1:4096`;
* a sibling container reaches it by service name
  (`http://opencode:4096/api/info` → `{"version":"2.0.30",…}`);
* an unauthenticated request from that sibling returns **401**.

Locally the verification server binds `127.0.0.1` only, and a connection attempt
to the machine's non-loopback address is refused (`test_20`).

### Q8 — Can server credentials stay exclusively in backend/container configuration? **YES, with one required control**

* Credentials are supplied to the server process only (`OPENCODE_PASSWORD`,
  provider key via env/`{env:…}`). None appear in session transcripts, message
  payloads, SSE events, or the OpenAPI document (`test_13` scans all four for the
  exact secret).
* **Finding:** `GET /api/config` returns the **fully resolved provider API key in
  clear** (`test_13b` asserts the raw secret is present and the `{env:…}`
  placeholder is not). The plan's fixed endpoint subset already excludes it, but
  this is now a verified hazard: the gateway must never proxy `/api/config`,
  `/api/credential`, filesystem, shell, PTY, VCS, or worktree routes to the
  browser, and must never log their bodies.
* Server authentication is HTTP **Basic** with username `opencode` and the server
  password (`Authorization: Basic base64("opencode:<password>")`). `Bearer`,
  `x-opencode-password`, and an empty username all return 401. This differs from
  the plan's "pairing code" assumption and must be corrected.

### Q9 — Does the version provide stable APIs for everything the plan needs? **YES, with two corrections**

Verified present and exercised: session creation (`POST /api/session`, including
`location.directory`, `agent`, `model`, `permissions`), prompting
(`POST /api/session/{id}/prompt`), message retrieval
(`GET /api/session/{id}/message`), streaming (`GET /api/event`), cancellation
(`POST /api/session/{id}/interrupt`), disposal (`DELETE /api/session/{id}`),
provider/model selection (`POST /api/session/{id}/model`, `GET /api/provider`,
`GET /api/model`), and plugin/tool registration (loaded from
`.opencode/plugins/<name>/index.ts`).

Corrections:

1. **No structured-output schema.** `POST /api/session/{id}/generate` accepts
   only `{prompt}`; `POST /api/experimental/generate` accepts only
   `{prompt, model}`. `test_14` asserts the property sets. Structured output must
   therefore come from tool calls (JSON Schema on tool input) plus strict
   application-side parsing, not from a provider "schema" parameter.
2. **Responses are wrapped**: every HTTP payload is `{"data": …}`. Any generated
   client must unwrap.

### Q10 — Can a prompt-injection attempt escape the scoped allowlist? **NO**

`test_16` drives a fully "compromised" model (the scripted provider) with
injection text in the user turn *and* inside tool data. It attempts
`shell rm -rf /`, `read /etc/shadow`, and `apply_change_set`, then calls the
scoped tool. Every denied tool fails as unavailable; the scoped tool runs and the
injected text is only echoed as data; nothing executed on the host. The
`apply_change_set` / `approve_change_set` names are simply not tools — the
boundary does not depend on model compliance.

---

## 3. Security-test results

| Required proof | Test | Result |
|---|---|---|
| Session A cannot use Session B context | `test_03` | PASS — per-session scope + per-call session ID, no mixed records |
| Scope cannot be supplied/overridden by model arguments | `test_07` | PASS — identity from OpenCode; args only data |
| A denied built-in tool remains unavailable | `test_06` | PASS — 12 built-ins absent and rejected |
| An unavailable discipline tool cannot be invoked | `test_08`, `test_04` | PASS |
| A malicious tool name is rejected | `test_17` | PASS — `../../etc/passwd`, `…; rm -rf /`, `$(id)` all rejected |
| Unknown tool arguments are rejected | `test_18` | PASS **with a correction** — OpenCode *silently strips* properties the input schema does not describe (no error), so the executor sees only schema-described args while the transcript keeps the raw ones. The adapter must still validate/cap on the backend. |
| Oversized tool arguments are rejected | `test_18` | **NOT by the runtime** — a 400-char value passed through unchanged (no `maxLength` enforcement). The application adapter must enforce size caps. |
| Tool output is bounded | `test_19` | PASS, but not as assumed — see §4.3 |
| Cancellation terminates generation | `test_10` | PASS |
| Disposed sessions cannot continue calling tools | `test_11` | PASS (404 on prompt/get) |
| No credential in browser-visible/streamed events | `test_13` | PASS for messages, session, SSE events, OpenAPI; `/api/config` leaks resolved secrets (`test_13b`) |
| Prompt-injection fixture cannot widen permissions | `test_16` | PASS |
| Server stays private with no host port | `test_20`, `compose/verify.sh` | PASS |

Additional verified facts worth recording:

* The agent `system` prompt is applied: the first provider request carried the
  990-character restricted-profile system prompt as the `system` message.
* Tool results reach the model as `role: "tool"` messages with the tool output as
  `content`.
* A session-scoped permission override exists
  (`POST /api/session` `permissions`, `PATCH /api/session/{id}` `permissions`),
  evaluated after the agent's rules — useful for per-conversation tightening.

---

## 4. Plugin approach classification

# **VERIFIED WITH CHANGES**

The plugin approach enforces the required boundary: identity is authoritative and
OpenCode-supplied, tool visibility is per-conversation and backend-driven,
built-ins are fully removable, cancellation/disposal/streaming work, and the
server can be kept private. The changes below are required before implementing
the plan as written.

### 4.1 Required architectural changes

1. **Plugin tools must declare `options.codemode: false`.**
   A plugin tool registered without it is present in `ctx.tool.list()` but is
   **never offered to the model** and cannot be called. This was the single
   blocking defect found; every architecture tool definition must set it (the
   built-in tools all declare `codemode: false`).
2. **Never use `effect: "ask"` for the assistant profile.**
   For built-ins an `ask` outcome creates a pending permission request and blocks
   the turn until a client replies — a prompt the browser must never see. For
   plugin tools `ask` does not prompt at all, so it silently does nothing. The
   profile must use only `allow`/`deny`.
3. **The gateway must bound tool results itself.**
   When a tool result exceeds `tool_output.max_bytes`, OpenCode **writes the full
   output to a file** under its data directory and replaces the model-visible
   content with a reference notice
   (`[showing 0 lines of 1; full output saved to …/tool-output/tool_….txt]`). The
   model loses the content, gains a filesystem path, and the runtime performed a
   disk write. The plan's per-tool result cap (16 KiB) is therefore **mandatory**,
   not defensive; results must be trimmed in the adapter before returning them.
4. **The adapter must validate arguments and enforce sizes.**
   OpenCode enforces the declared `input` schema *shape* (stripping unknown
   properties, without erroring) but applies **no value or size limits**. Backend
   validation remains required, and "unknown fields rejected" in the plan must be
   restated: the runtime strips them silently, so the adapter must reject rather
   than rely on that.
5. **Authentication is HTTP Basic (`opencode:<password>`), not pairing codes.**
   For a headless container, set `OPENCODE_PASSWORD` (or read the password the
   server prints to stdout) and send `Authorization: Basic …`. The plan's
   "pairing flow" wording must be replaced.
6. **The gateway's endpoint allowlist must explicitly exclude secret-bearing
   routes.** `GET /api/config` returns resolved provider credentials; credential,
   filesystem, shell, PTY, VCS, and worktree routes are likewise out of bounds.
   This must be an allowlist in code plus a test, not a convention.
7. **Two distinct denial messages must be handled**:
   `Tool is not available for this request: <name>` (removed by the context hook)
   and `No tool named "<name>" is currently available` (removed by permission
   rules). The model-facing error mapping should treat both as "not permitted in
   this scope".
8. **Tool-set changes take effect per model request**, so the hook is the correct
   place for dynamic scoping — but the backend must remain authoritative at
   dispatch time (the plan already requires this; it is now justified by
   observation, since a hook bug would otherwise silently widen scope).
9. **`steps` must be set explicitly** and kept in step with the tool-call budget:
   the runtime disables tools after the step limit with the message
   `Tools are disabled after the maximum agent steps`.
10. **No structured-output parameter exists.** Replace "structured output" in the
    plan with "tool-argument JSON Schema plus strict application-side parsing".

### 4.2 Plan text that is now confirmed and can be simplified

* `context.sessionID` in the tool executor **is** the authoritative conversation
  key; no opaque capability token, no model-visible scope handle, and no MCP
  server are needed. The plan's MCP fallback can stay documented but is not
  required.
* Deleting entries from `event.tools` in an async `context` hook is a working
  per-conversation tool filter.
* `permissions: [{action:"*",resource:"*",effect:"deny"}]` plus per-agent allows
  removes every built-in capability, including Code Mode (`execute`).
* Streaming, cancellation, disposal, and live-only re-subscription behave as the
  plan assumed; the gateway's own durable event log is the right design.

### 4.3 Facts that change the plan's wording (not its architecture)

* "Unknown tool arguments are rejected" → the runtime strips them silently;
  reject explicitly in the adapter.
* "Oversized tool arguments are rejected" → nothing bounds them at runtime.
* "Tool output is bounded to 16 KiB" → the runtime's behaviour is *spill to disk
  and withhold*, so the adapter must bound first.
* "Provider credentials never leave the backend" → true for the surfaces the
  browser can reach, but `GET /api/config` is a live secret source inside the
  server; the plan's "never proxy config" rule becomes a hard requirement.
* "Structured output" → not available on either generate endpoint.
* "Pairing code" → HTTP Basic with `OPENCODE_PASSWORD`.

---

## 5. Files added or modified

Added (all inside `verification/opencode-assistant-feasibility/`):

| File | Purpose |
|---|---|
| `README.md` | harness overview and how to run it |
| `VERIFICATION_REPORT.md` | this report |
| `runtime/profile/opencode.json` | restricted profile (shipped candidate: deny-all + per-agent allows, custom agent, `steps: 20`, `tool_output` caps, mock provider) |
| `runtime/profile/.opencode/plugins/verify/index.ts` | test-only plugin: three harmless tools, async `context` scope hook, optional `ctx.permission.assert` probe, journaling |
| `runtime/mock_provider.py` | scripted OpenAI-compatible mock model (streaming + JSON, script registry, request recorder) |
| `runtime/harness.py` | isolated server/mock lifecycle, API client, SSE collector, transcript helpers |
| `tests/conftest.py` | fixtures: mock provider, restricted server, permission-variant server factory |
| `tests/test_opencode_feasibility.py` | 21 focused verification tests |
| `compose/Dockerfile` | minimal OpenCode image for the network proof |
| `compose/compose.verify.yml` | private-network stack, no published ports |
| `compose/verify.sh` | runs the proof and asserts the result |
| `artifacts/pytest.txt` | captured test run |
| `artifacts/compose-proof.txt` | captured Compose proof |
| `artifacts/versions.txt` | captured versions |

Modified: **none**. No file under `api/` or `web/` was touched, no dependency was
added, no migration was created, and no service was started outside the harness.
`git status` shows only the new `verification/` directory (and the plan document
that was already present as an untracked file).

---

## 6. Remaining risks and follow-ups

1. **Version pinning.** All results are for OpenCode `v2.0.30` and its
   OpenAPI `0.0.1` document. The plugin tool options (`codemode`), the hook
   contract, and the permission semantics are not part of the HTTP contract and
   could change between releases. Pin the runtime version and add a startup
   capability probe (assert `/api/info` version prefix plus a tool-registration
   smoke check) that fails closed.
2. **Hook-based scoping is a single point of failure.** The plugin hook is the
   only mechanism that hides out-of-scope tools. A hook exception, a stale scope
   file, or a plugin reload failure could widen visibility. The backend dispatch
   allowlist must therefore be authoritative and must be tested independently of
   the plugin, and the plugin must fail closed (register zero tools) when it
   cannot resolve scope.
3. **Tool-result spill.** Even with adapter-side caps, any accidental oversized
   result writes to the OpenCode data directory and leaks a path into model
   context. Treat the OpenCode data directory as sensitive, bound it, and monitor
   for `tool-output/` growth.
4. **Secret-bearing routes.** `GET /api/config` (and `/api/credential`) return
   resolved secrets. The gateway allowlist must be enforced in code and covered
   by a test; do not rely on "we just won't call it".
5. **`ask` hazards.** Any future permission rule with `ask` can block a turn
   forever. Add a config assertion that the assistant profile contains no `ask`
   effect, and ensure the gateway has a timeout + cancel path.
6. **Argument stripping is silent.** Because the runtime drops unknown
   properties without error, a schema/adapter mismatch (for example a typo in a
   tool's JSON Schema) would silently discard model intent instead of failing.
   Add a schema-vs-request-model conformance test in the tool surface slice.
7. **Not yet verified in this slice** (deliberately out of scope): real provider
   behaviour, model quality for proposal generation, per-workspace/state
   dispatch, conversation persistence, and the `ctx.permission.assert`
   `resources`/`save` semantics under multi-resource checks. The `save` pattern
   (`"id *"`) observed for shell shows that saved approvals are durable and
   project-scoped — the assistant profile must never rely on saved approvals.
