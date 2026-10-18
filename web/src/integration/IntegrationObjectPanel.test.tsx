// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import IntegrationObjectPanel from "./IntegrationObjectPanel";
import type { IntegrationContractSummary } from "./integrationDesignModel";
import type { IntegrationTopologyNode } from "./integrationViews";

vi.mock("../components/architecture/ObjectTracePanel", () => ({ default: () => null }));

afterEach(cleanup);

const contractNode: IntegrationTopologyNode = {
  id: "contract:int-1",
  refId: "int-1",
  kind: "contract",
  name: "Customer push",
  subtitle: "Contract",
  detail: null,
  badge: null,
  pattern: "request_reply",
  status: "built",
  direction: null,
  runtime: false,
  mediated: false,
};

function contract(overrides: Partial<IntegrationContractSummary> = {}): IntegrationContractSummary {
  return {
    id: "int-1",
    name: "Customer push",
    description: null,
    interaction_type: "REQUEST_RESPONSE",
    pattern: "request_reply",
    implementation_status: "built",
    revision: 2,
    updated_at: null,
    status: "built",
    source: { system_id: "sys-a", system_name: "CRM", object_id: "obj-a", object_name: "Customer" },
    target: { system_id: "sys-b", system_name: "ERP", object_id: "obj-b", object_name: "Account" },
    producer_interface: null,
    consumer_interface: null,
    has_request_graph: false,
    has_response_graph: false,
    has_error_graph: false,
    specification: {},
    target_fields_mapped: 0,
    target_fields_total: 0,
    scenario_count: 0,
    lifecycle_stage: { value: "active", canonical: "active", override: null, overridden: false },
    operational_status: { value: "tested", canonical: "tested", override: null, overridden: false },
    environment_scope: { value: null, canonical: null, override: null, overridden: false },
    mediator: null,
    explicit_mediator: false,
    mediated: false,
    mediation_source: "none",
    ...overrides,
  };
}

function renderPanel(item: IntegrationContractSummary) {
  render(
    <IntegrationObjectPanel
      node={contractNode}
      workspaceId="ws-1"
      stateId="state-1"
      interfaces={[]}
      contracts={[item]}
      onOpenContract={vi.fn()}
      onClose={vi.fn()}
    />,
  );
}

function factText(label: string): string {
  return screen.getByText(label).nextElementSibling?.textContent ?? "";
}

describe("IntegrationObjectPanel contract facts", () => {
  it("shows effective values and labels unspecified facts", () => {
    renderPanel(contract());
    expect(factText("Lifecycle stage")).toBe("Active");
    expect(factText("Operational status")).toBe("Tested");
    expect(factText("Environment scope")).toBe("Unspecified");
  });

  it("flags a state override and shows the canonical baseline it departs from", () => {
    renderPanel(
      contract({
        lifecycle_stage: {
          value: "retiring",
          canonical: "active",
          override: "retiring",
          overridden: true,
        },
      }),
    );
    expect(factText("Lifecycle stage")).toBe("Retiring · override (baseline: Active)");
  });

  it("keeps a direct contract free of any mediation rows", () => {
    renderPanel(contract());
    expect(screen.getByText("Business source").nextElementSibling?.textContent).toBe(
      "CRM · Customer",
    );
    expect(screen.getByText("Business target").nextElementSibling?.textContent).toBe(
      "ERP · Account",
    );
    expect(screen.queryByText("Mediator")).toBeNull();
    expect(screen.queryByText("Mediation")).toBeNull();
  });

  it("shows an explicit mediator between the business source and target", () => {
    renderPanel(
      contract({
        mediated: true,
        explicit_mediator: true,
        mediation_source: "explicit",
        mediator: {
          system_id: "sys-frends",
          system_name: "FRENDS",
          system_kind: "runtime",
          is_runtime: true,
          responsibility: "Routes and translates the exchange.",
          explicit: true,
        },
      }),
    );
    expect(factText("Business source")).toBe("CRM · Customer");
    expect(factText("Mediator")).toBe("FRENDS");
    expect(factText("Mediator responsibility")).toBe("Routes and translates the exchange.");
    expect(factText("Mediation")).toBe("Explicit");
    // The mediator is never shown as (or labelled like) a business endpoint.
    expect(factText("Business target")).toBe("ERP · Account");
    expect(factText("Business target")).not.toContain("FRENDS");
  });

  it("distinguishes legacy heuristic mediation from explicit mediation in text", () => {
    renderPanel(
      contract({
        mediated: true,
        explicit_mediator: false,
        mediation_source: "legacy_endpoint_heuristic",
        mediator: {
          system_id: "sys-rt",
          system_name: "Integration Runtime",
          system_kind: "integration_runtime",
          is_runtime: true,
          responsibility: null,
          explicit: false,
        },
      }),
    );
    expect(factText("Mediation")).toBe("Inferred · legacy endpoint heuristic");
    expect(factText("Mediator")).toBe("Integration Runtime (inferred)");
    // No responsibility is invented for an inferred mediator.
    expect(factText("Mediator responsibility")).toBe("—");
  });
});
