/**
 * Slice B in-image verification.
 *
 * Runs *inside* the built OpenCode image (node:20 based) against the profile and
 * tool manifest baked into the image at /sandbox. It asserts the restricted
 * profile invariants without needing Python.
 */

const fs = require("fs")

const failures = []
function check(name, ok, detail) {
  const suffix = detail ? ` :: ${detail}` : ""
  console.log(`[${ok ? "PASS" : "FAIL"}] ${name}${suffix}`)
  if (!ok) failures.push(name)
}

const profile = JSON.parse(fs.readFileSync("/sandbox/opencode.json", "utf8"))
const tools = JSON.parse(fs.readFileSync("/sandbox/assistant-tools.json", "utf8"))
const plugin = fs.readFileSync(
  "/sandbox/.opencode/plugins/architecture-assistant/index.ts",
  "utf8",
)

function hasAsk(value) {
  if (Array.isArray(value)) return value.some(hasAsk)
  if (value && typeof value === "object") {
    if (value.effect === "ask") return true
    return Object.values(value).some(hasAsk)
  }
  return false
}

const denyAll =
  Array.isArray(profile.permissions) &&
  profile.permissions.some(
    (rule) => rule.action === "*" && rule.resource === "*" && rule.effect === "deny",
  )
check("deny-all policy present", denyAll)

check("no ask rule anywhere", !hasAsk(profile))

const agent = profile.agents && profile.agents[profile.default_agent]
check("default agent defined", Boolean(agent), `agent=${profile.default_agent}`)
check(
  "steps bounded",
  agent && Number.isInteger(agent.steps) && agent.steps > 0 && agent.steps <= 12,
  agent ? `steps=${agent.steps}` : "no agent",
)
check(
  "built-in agents disabled",
  ["build", "plan", "general", "explore"].every(
    (name) => profile.agents[name] && profile.agents[name].disabled === true,
  ),
)

const declared = Array.isArray(tools.tools) ? tools.tools : []
check("tool manifest present", declared.length > 0)
check(
  "probe tools use codemode:false",
  declared.every((tool) => tool.codemode === false),
)
check(
  "probe tools are namespaced",
  declared.every((tool) => String(tool.name).startsWith("architecture_")),
)

const allows = new Set(
  ((agent && agent.permissions) || [])
    .filter((rule) => rule.effect === "allow")
    .map((rule) => rule.action),
)
check(
  "probe tools have explicit allow rules",
  declared.every((tool) => allows.has(tool.name)),
)

const forbiddenTools = ["shell", "read", "write", "edit", "patch", "execute", "webfetch", "websearch"]
check(
  "no built-in coding capability allowed",
  ![...allows].some((action) => forbiddenTools.includes(action)),
)

check("plugin declares codemode:false", plugin.includes("codemode: false"))
check("plugin has no shell/fs execution import", !/child_process|node:fs\/promises/.test(plugin))

console.log(`\nIN-IMAGE RESULT: ${failures.length ? "FAIL" : "PASS"}`)
process.exit(failures.length ? 1 : 0)
