// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ObjectTracePanel from "../components/architecture/ObjectTracePanel";
import {
  traceKindLabel,
  traceMembershipLabel,
  traceRelationshipLabel,
  type ObjectTrace,
  type TraceObjectRef,
  type TraceResult,
} from "./workbenchTypes";

const root: TraceObjectRef = {
  id: "ent-1",
  kind: "information_object",
  name: "Customer",
  description: null,
  discipline: "information",
  state_membership: "candidate",
  external: false,
};

const attribute: TraceObjectRef = {
  id: "attr-1",
  kind: "information_attribute",
  name: "customer_id",
  description: null,
  discipline: "information",
  state_membership: "candidate",
  external: false,
};

const contract: TraceObjectRef = {
  id: "int-1",
  kind: "contract_ref",
  name: "Customer Sync",
  description: null,
  discipline: "integration",
  state_membership: "none",
  external: true,
};

const usages: ObjectTrace = {
  state_id: "candidate-a",
  object: root,
  disciplines: ["information", "integration"],
  outgoing: [
    { relationship_type: "has_attribute", direction: "outgoing", derived: true, object: attribute },
  ],
  incoming: [],
  groups: [
    { label: "Attributes", objects: [attribute] },
    { label: "Mapped into contracts", objects: [contract] },
  ],
  physical_refs: [attribute],
  tests: [],
  principles: [],
};

const trace: TraceResult = {
  state_id: "candidate-a",
  direction: "both",
  max_depth: 3,
  root,
  nodes: [root, attribute, contract],
  edges: [
    {
      id: "d-ent-1-attr-1-has_attribute",
      source_object_id: "ent-1",
      target_object_id: "attr-1",
      relationship_type: "has_attribute",
      derived: true,
    },
  ],
  depths: { "ent-1": 0, "attr-1": 1, "int-1": 2 },
};

function json(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response);
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/usages")) return json(usages);
      if (url.includes("/trace?")) return json(trace);
      throw new Error(`Unexpected request: ${url}`);
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("ObjectTracePanel", () => {
  it("renders grouped usages and navigates on selection", async () => {
    const onNavigate = vi.fn();
    render(
      <ObjectTracePanel
        workspaceId="ws-a"
        stateId="candidate-a"
        objectId="ent-1"
        onNavigate={onNavigate}
      />,
    );

    expect(await screen.findByText("Attributes")).toBeTruthy();
    expect(screen.getByText("Mapped into contracts")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Customer Sync/ }));
    expect(onNavigate).toHaveBeenCalledWith(contract);
  });

  it("loads the full trace on demand", async () => {
    render(
      <ObjectTracePanel workspaceId="ws-a" stateId="candidate-a" objectId="ent-1" />,
    );

    fireEvent.click(await screen.findByRole("button", { name: "View full trace" }));
    expect(await screen.findByText(/Hop 1/)).toBeTruthy();
    expect(screen.getByText(/Hop 2/)).toBeTruthy();
  });

  it("renders nothing without an object id", () => {
    const { container } = render(
      <ObjectTracePanel workspaceId="ws-a" stateId="candidate-a" objectId={null} />,
    );
    expect(container.querySelector(".object-trace-panel")).toBeNull();
  });
});

describe("trace label helpers", () => {
  it("resolves known and unknown labels", () => {
    expect(traceKindLabel("information_object")).toBe("Entity");
    expect(traceKindLabel("unknown_kind")).toBe("unknown kind");
    expect(traceRelationshipLabel("has_attribute")).toBe("has attribute");
    expect(traceRelationshipLabel("weird_edge")).toBe("weird edge");
    expect(traceMembershipLabel("candidate")).toBe("Candidate");
    expect(traceMembershipLabel("none")).toBe("Not on canvas");
  });

  it("re-fetches when depth changes", async () => {
    render(
      <ObjectTracePanel workspaceId="ws-a" stateId="candidate-a" objectId="ent-1" />,
    );
    fireEvent.click(await screen.findByRole("button", { name: "View full trace" }));
    await screen.findByText(/Hop 1/);
    fireEvent.change(screen.getByLabelText("Trace depth"), { target: { value: "5" } });
    await waitFor(() => {
      const calls = vi.mocked(fetch).mock.calls.map(([input]) => String(input));
      expect(calls.some((url) => url.includes("depth=5"))).toBe(true);
    });
  });
});
