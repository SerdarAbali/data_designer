// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ArchitectureState } from "../architectureTypes";
import EnterpriseWorkbench from "./EnterpriseWorkbench";
import type {
  ApplicationSupport,
  CapabilityMap,
  EnterpriseImpact,
  EnterpriseModel,
  ProcessImpact,
  StrategyTrace,
} from "./enterpriseModel";

const candidateState: ArchitectureState = {
  id: "state-1",
  workspace_id: "ws-1",
  name: "Candidate",
  state_type: "candidate",
  nodes: [],
  relationships: [],
  created_at: "",
  updated_at: "",
};

const goal = {
  object_id: "goal-1",
  kind: "goal" as const,
  name: "Grow revenue",
  description: "Grow recurring revenue.",
  owner: "CFO",
  outcome_metric: "+10% ARR",
  horizon: "FY27",
  process_type: null,
  principle_type: null,
  rationale: null,
  role_type: null,
  created_in_state_id: "state-1",
};
const requirement = {
  ...goal,
  object_id: "req-1",
  kind: "requirement" as const,
  name: "Real-time payments",
  owner: null,
  outcome_metric: null,
  horizon: null,
};
const capability = {
  ...goal,
  object_id: "cap-1",
  kind: "capability" as const,
  name: "Payment processing",
  owner: null,
  outcome_metric: null,
  horizon: null,
};
const processObject = {
  ...goal,
  object_id: "proc-1",
  kind: "process" as const,
  name: "Card settlement",
  owner: "Payments Ops",
  outcome_metric: null,
  horizon: null,
  process_type: "process",
};
const principle = {
  ...goal,
  object_id: "prin-1",
  kind: "principle" as const,
  name: "Data residency",
  owner: null,
  outcome_metric: null,
  horizon: null,
  principle_type: "constraint",
  rationale: "Regulated workloads stay in-region.",
};
const role = {
  ...goal,
  object_id: "role-1",
  kind: "role" as const,
  name: "Payments Team",
  owner: null,
  outcome_metric: null,
  horizon: null,
  role_type: "role",
};

const application = { object_id: "sys-1", name: "Core Banking", kind: "system" };

const model: EnterpriseModel = {
  state_id: "state-1",
  state_type: "candidate",
  editable: true,
  goals: [goal],
  requirements: [requirement],
  capabilities: [capability],
  processes: [processObject],
  principles: [principle],
  roles: [role],
  applications: [application],
  links: [
    { id: "link-1", source_object_id: "goal-1", target_object_id: "req-1", relationship_type: "drives" },
    { id: "link-2", source_object_id: "cap-1", target_object_id: "proc-1", relationship_type: "has_process" },
    { id: "link-3", source_object_id: "sys-1", target_object_id: "cap-1", relationship_type: "supports" },
  ],
};

const capabilityMap: CapabilityMap = {
  state_id: "state-1",
  capabilities: [
    {
      capability,
      processes: [processObject],
      applications: [application],
      principles: [principle],
      owner_role: role,
    },
  ],
};

const processImpact: ProcessImpact = {
  state_id: "state-1",
  processes: [
    {
      process: processObject,
      capabilities: [capability],
      applications: [application],
      requirements: [requirement],
      governed_by: [principle],
      impacted: true,
    },
  ],
};

const strategyTrace: StrategyTrace = {
  state_id: "state-1",
  chains: [
    {
      goal,
      steps: [
        {
          requirement,
          capabilities: [capability],
          processes: [processObject],
          applications: [application],
        },
      ],
      gaps: [],
    },
  ],
  unlinked_requirements: [],
  gaps: [],
};

const applicationSupport: ApplicationSupport = {
  state_id: "state-1",
  applications: [
    {
      application,
      capabilities: [capability],
      processes: [processObject],
      requirements: [requirement],
    },
  ],
};

const impact: EnterpriseImpact = {
  state_id: "state-1",
  baseline_state_id: "state-current",
  changes: [
    { object_id: "goal-1", kind: "goal", name: "Grow revenue", change: "added" },
    { object_id: "cap-1", kind: "capability", name: "Payment processing", change: "reused" },
  ],
  affected_applications: [application],
  affected_capabilities: [capability],
  affected_processes: [],
  unresolved_dependencies: [],
  unresolved_constraints: ["Constraint 'Data residency' governs no object"],
  risks: [],
  gaps: ["Process 'Card settlement' has no supporting system"],
};

const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

beforeEach(() => {
  document.cookie = "dd_csrf=test";
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      const url = String(path);
      if (url.includes("/enterprise/capability-map")) return reply(capabilityMap);
      if (url.includes("/enterprise/process-impact")) return reply(processImpact);
      if (url.includes("/enterprise/strategy-trace")) return reply(strategyTrace);
      if (url.includes("/enterprise/application-support")) return reply(applicationSupport);
      if (url.includes("/enterprise/impact")) return reply(impact);
      if (url.includes("/enterprise/objects") && init?.method === "POST") return reply(model, 201);
      if (url.includes("/enterprise/links")) return reply(model, 201);
      if (url.includes("/enterprise/model")) return reply(model);
      throw new Error(`Unexpected request: ${url}`);
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function renderWorkbench(overrides: Partial<Parameters<typeof EnterpriseWorkbench>[0]> = {}) {
  return render(
    <EnterpriseWorkbench
      workspaceId="ws-1"
      activeState={candidateState}
      editable
      saveStatus="idle"
      onOpenCatalog={vi.fn()}
      {...overrides}
    />,
  );
}

describe("EnterpriseWorkbench", () => {
  it("loads the model and lists objects by kind", async () => {
    renderWorkbench();
    expect(await screen.findByText("Grow revenue")).toBeTruthy();
    expect(screen.getByText("Payment processing")).toBeTruthy();
    expect(screen.getByText("Card settlement")).toBeTruthy();
    expect(screen.getByText("Data residency")).toBeTruthy();
    expect(screen.getByText("Payments Team")).toBeTruthy();
    // Plural group headings must be spelled correctly (not "Capabilitys"/"Processs").
    expect(screen.getByText("Capabilities")).toBeTruthy();
    expect(screen.getByText("Processes")).toBeTruthy();
    expect(screen.queryByText("Capabilitys")).toBeNull();
    expect(screen.queryByText("Processs")).toBeNull();
  });

  it("opens the object inspector and shows typed relationships", async () => {
    renderWorkbench();
    fireEvent.click(await screen.findByRole("button", { name: /Grow revenue/ }));
    const panel = await screen.findByRole("complementary", { name: "Enterprise object details" });
    expect(panel.textContent).toContain("drives");
    expect(panel.textContent).toContain("Real-time payments");
  });

  it("renders the capability map with processes and applications", async () => {
    renderWorkbench();
    await screen.findByText("Grow revenue");
    fireEvent.click(screen.getByRole("button", { name: "Capability Map" }));
    const card = await screen.findByText("Payment processing");
    expect(card).toBeTruthy();
    expect(screen.getByText("Card settlement")).toBeTruthy();
    expect(screen.getAllByText("Core Banking").length).toBeGreaterThan(0);
  });

  it("renders process impact with an impacted badge", async () => {
    renderWorkbench();
    await screen.findByText("Grow revenue");
    fireEvent.click(screen.getByRole("button", { name: "Process Impact" }));
    expect(await screen.findByText("impacted")).toBeTruthy();
    expect(screen.getByText("Core Banking")).toBeTruthy();
  });

  it("renders the strategy-to-execution trace", async () => {
    renderWorkbench();
    await screen.findByText("Grow revenue");
    fireEvent.click(screen.getByRole("button", { name: "Strategy Trace" }));
    expect(await screen.findByText("Real-time payments")).toBeTruthy();
    expect(screen.getByText("Applications")).toBeTruthy();
    expect(screen.getByText("Core Banking")).toBeTruthy();
  });

  it("renders the current-versus-candidate impact diff", async () => {
    renderWorkbench();
    await screen.findByText("Grow revenue");
    fireEvent.click(screen.getByRole("button", { name: "Impact" }));
    expect(await screen.findByText("Added")).toBeTruthy();
    expect(screen.getByText("Reused")).toBeTruthy();
    expect(screen.getByText("Constraint 'Data residency' governs no object")).toBeTruthy();
  });

  it("creates an enterprise object through the API", async () => {
    renderWorkbench();
    await screen.findByText("Grow revenue");
    fireEvent.change(screen.getByLabelText("New object name"), {
      target: { value: "Reduce risk" },
    });
    fireEvent.click(screen.getByRole("button", { name: "+ Add object" }));
    await waitFor(() => {
      const post = vi
        .mocked(fetch)
        .mock.calls.find(
          ([path, init]) =>
            String(path).includes("/enterprise/objects") && init?.method === "POST",
        );
      expect(post).toBeTruthy();
      expect(String(post?.[1]?.body)).toContain("Reduce risk");
    });
  });

  it("disables editing controls when the state is read-only", async () => {
    renderWorkbench({ editable: false });
    await screen.findByText("Grow revenue");
    expect(screen.getByRole("button", { name: "+ Add object" })).toHaveProperty("disabled", true);
  });
});
