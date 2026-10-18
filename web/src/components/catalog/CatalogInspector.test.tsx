// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CatalogInspector from "./CatalogInspector";

const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

const system = {
  id: "sys-1",
  name: "CRM",
  kind: "application",
  description: "Customer system",
  icon: null,
  color: null,
  position: { x: 12, y: 34 },
  metadata: { tier: 1 },
  lifecycle_stage: null,
  operational_status: null,
  environment_scope: null,
};

const object = {
  id: "obj-1",
  system_id: "sys-1",
  name: "customer",
  label: "Customer",
  description: null,
  external_identifier: null,
  position: 0,
  metadata: {},
};

const baseProps = {
  workspaceId: "ws-1",
  objects: [object],
  fields: [],
  fieldCounts: {},
  loadingObjects: false,
  loadingFields: false,
  saving: false,
  onSaveSystem: vi.fn(),
  onSaveObject: vi.fn(),
  onSaveField: vi.fn(),
  onCreateObject: vi.fn(),
  onCreateField: vi.fn(),
  onSelectObject: vi.fn(),
  onSelectField: vi.fn(),
  onAddObject: vi.fn(),
  onAddField: vi.fn(),
  modal: null,
  onCloseModal: vi.fn(),
  onArchive: vi.fn(),
};

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async (path: string) => {
    const url = String(path);
    if (url.includes("/states")) return reply([{ id: "state-1", state_type: "current" }]);
    if (url.includes("/usages")) {
      return reply({
        state_id: "state-1",
        object: { id: "sys-1", kind: "system", name: "CRM", description: null, discipline: null, state_membership: "current", external: false },
        disciplines: ["integration"],
        outgoing: [],
        incoming: [],
        groups: [],
        physical_refs: [],
        tests: [],
        principles: [],
      });
    }
    return reply({});
  }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("CatalogInspector", () => {
  it("gives a system General/Objects/Usage/Metadata tabs without position fields", () => {
    render(<CatalogInspector {...baseProps} system={system} object={null} field={null} />);
    expect(screen.getByRole("button", { name: "General" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Objects (1)" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Usage" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Metadata" })).toBeTruthy();
    expect(screen.queryByText("Position X")).toBeNull();
    expect(screen.queryByText("Position Y")).toBeNull();
    // Archive lives in a secondary danger menu, not the primary heading.
    expect(screen.getByText("Manage system")).toBeTruthy();
    // Objects render within their tab.
    fireEvent.click(screen.getByRole("button", { name: "Objects (1)" }));
    expect(screen.getByRole("button", { name: "Open object" })).toBeTruthy();
  });

  it("gives an object General/Fields/Relationships/Usage tabs", () => {
    render(<CatalogInspector {...baseProps} system={null} object={object} field={null} />);
    expect(screen.getByRole("button", { name: "General" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Fields" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Relationships" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Usage" })).toBeTruthy();
  });

  it("moves raw metadata JSON behind the Metadata tab", () => {
    render(<CatalogInspector {...baseProps} system={system} object={null} field={null} />);
    const metadataTab = screen.getByRole("button", { name: "Metadata" });
    fireEvent.click(metadataTab);
    expect(screen.getByText("Raw metadata JSON").closest(".inspector-tab-panel")?.hasAttribute("hidden")).toBe(false);
  });

  it("shows lifecycle, operational and environment facts with an unspecified default", () => {
    render(<CatalogInspector {...baseProps} system={system} object={null} field={null} />);
    const lifecycle = screen.getByLabelText(/Lifecycle stage/) as HTMLSelectElement;
    const operational = screen.getByLabelText(/Operational status/) as HTMLSelectElement;
    const environment = screen.getByLabelText(/Environment scope/) as HTMLSelectElement;

    // Unspecified stays the default; null is never coerced into a value.
    expect(lifecycle.value).toBe("");
    expect(operational.value).toBe("");
    expect(environment.value).toBe("");
    expect(screen.getAllByRole("option", { name: "Unspecified" })).toHaveLength(3);

    expect(within(lifecycle).getByRole("option", { name: "Retired" })).toBeTruthy();
    expect(within(operational).getByRole("option", { name: "Decommissioned" })).toBeTruthy();
    expect(within(environment).getByRole("option", { name: "Production" })).toBeTruthy();
  });

  it("preselects the stored fact values", () => {
    render(
      <CatalogInspector
        {...baseProps}
        system={{ ...system, lifecycle_stage: "legacy", operational_status: "degraded", environment_scope: "production" }}
        object={null}
        field={null}
      />,
    );
    expect((screen.getByLabelText(/Lifecycle stage/) as HTMLSelectElement).value).toBe("legacy");
    expect((screen.getByLabelText(/Operational status/) as HTMLSelectElement).value).toBe("degraded");
    expect((screen.getByLabelText(/Environment scope/) as HTMLSelectElement).value).toBe("production");
  });

  it("separates field archiving into the danger menu", () => {
    const onArchive = vi.fn();
    render(
      <CatalogInspector
        {...baseProps}
        system={null}
        object={null}
        field={{ ...object, object_id: "obj-1", label: "Email", data_type: "string", required: false, nullable: true, default_value: null, origin: "manual" }}
        onArchive={onArchive}
      />,
    );
    fireEvent.click(screen.getByText("Manage field"));
    fireEvent.click(screen.getByRole("button", { name: "Archive field" }));
    expect(onArchive).toHaveBeenCalledWith("field");
  });
});
