// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import EvidencePanel from "./EvidencePanel";
import type { EvidenceRecord } from "../../evidence";
import { createEvidence, deleteEvidence, listEvidence, updateEvidence } from "../../evidenceApi";

vi.mock("../../evidenceApi", () => ({
  listEvidence: vi.fn(),
  createEvidence: vi.fn(),
  updateEvidence: vi.fn(),
  deleteEvidence: vi.fn(),
}));

const listMock = vi.mocked(listEvidence);
const createMock = vi.mocked(createEvidence);
const updateMock = vi.mocked(updateEvidence);
const deleteMock = vi.mocked(deleteEvidence);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function record(overrides: Partial<EvidenceRecord> = {}): EvidenceRecord {
  return {
    id: "ev-1",
    tenant_id: "ws-1",
    target_kind: "architecture_object",
    target_id: "obj-1",
    evidence_classification: "confirmed_by_requirements_document",
    source_type: "document",
    source_title: "Onboarding requirements",
    source_reference: "https://docs.example.test/onboarding",
    source_locator: null,
    summary: "The onboarding flow is specified in the requirements document.",
    confidence: "high",
    verification_status: "unverified",
    recorded_by: "user-1",
    recorded_at: "2026-01-02T03:04:05Z",
    updated_at: "2026-01-02T03:04:05Z",
    created_in_state_id: null,
    state_applicability: "canonical",
    state_name: null,
    ...overrides,
  };
}

function renderPanel(overrides: Partial<React.ComponentProps<typeof EvidencePanel>> = {}) {
  return render(
    <EvidencePanel
      workspaceId="ws-1"
      stateId="state-1"
      targetKind="architecture_object"
      targetId="obj-1"
      readOnly={false}
      {...overrides}
    />,
  );
}

beforeEach(() => {
  listMock.mockResolvedValue([]);
});

describe("EvidencePanel", () => {
  it("shows a loading state while the list is in flight", () => {
    listMock.mockReturnValue(new Promise(() => {}));
    renderPanel();
    expect(screen.getByRole("status").textContent).toContain("Loading evidence");
  });

  it("shows an empty state and a bounded add action", async () => {
    renderPanel();
    await screen.findByText("No evidence recorded");
    expect(screen.getByText(/Nothing recorded yet/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "+ Add evidence" })).toBeTruthy();
  });

  it("renders confirmed evidence in its own labelled group", async () => {
    listMock.mockResolvedValue([
      record({ evidence_classification: "confirmed_by_current_implementation" }),
    ]);
    const { container } = renderPanel();
    await screen.findByText("Confirmed facts");
    expect(screen.getByText("Confirmed · current implementation")).toBeTruthy();
    expect(container.querySelector(".evidence-item-meta em")?.textContent).toContain("Document");
    expect(screen.getByText(/specified in the requirements document/)).toBeTruthy();
  });

  it("separates assumptions, open decisions and future scope textually", async () => {
    listMock.mockResolvedValue([
      record({ id: "a", evidence_classification: "assumption", summary: "We assume nightly batch." }),
      record({ id: "b", evidence_classification: "open_decision", summary: "Retry policy undecided." }),
      record({ id: "c", evidence_classification: "future_scope", summary: "Multi-region is deferred." }),
    ]);
    renderPanel();
    await screen.findByText("Assumptions");
    // The group heading and the per-record classification label both say it.
    expect(screen.getAllByText("Open decisions").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Future scope").length).toBeGreaterThan(0);
    expect(screen.getByText("Assumption")).toBeTruthy();
    expect(screen.getByText("Open decision")).toBeTruthy();
  });

  it("shows disputed and superseded status in words, not only colour", async () => {
    listMock.mockResolvedValue([
      record({ id: "d", verification_status: "disputed" }),
      record({ id: "s", verification_status: "superseded" }),
    ]);
    renderPanel();
    await screen.findByText("Disputed");
    expect(screen.getByText("Superseded")).toBeTruthy();
  });

  it("keeps long summaries and references inside the panel", async () => {
    const longSummary = "S".repeat(600);
    const longReference = `https://docs.example.test/${"segment/".repeat(60)}end`;
    listMock.mockResolvedValue([record({ summary: longSummary, source_reference: longReference })]);
    const { container } = renderPanel();
    await screen.findByText(longSummary);
    const reference = container.querySelector(".evidence-reference");
    expect(reference?.textContent).toBe(longReference);
    expect(container.querySelector(".evidence-panel")).toBeTruthy();
  });

  it("labels state applicability for canonical and state-scoped evidence", async () => {
    listMock.mockResolvedValue([
      record({ id: "c", state_applicability: "canonical", created_in_state_id: null }),
      record({
        id: "s",
        state_applicability: "state",
        created_in_state_id: "state-2",
        state_name: "Candidate Design",
      }),
    ]);
    renderPanel();
    await screen.findByText("All states (canonical)");
    expect(screen.getByText("Candidate Design state")).toBeTruthy();
  });

  it("does not offer writing controls in a read-only state", async () => {
    listMock.mockResolvedValue([record()]);
    renderPanel({ readOnly: true });
    await screen.findByText("Confirmed facts");
    expect(screen.queryByRole("button", { name: "+ Add evidence" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
  });

  it("rejects an incomplete evidence form before calling the API", async () => {
    const { container } = renderPanel();
    await screen.findByText("No evidence recorded");
    fireEvent.click(screen.getByRole("button", { name: "+ Add evidence" }));
    const form = container.querySelector("form.evidence-form");
    expect(form).toBeTruthy();
    fireEvent.submit(form as HTMLFormElement);
    expect((await screen.findByRole("alert")).textContent).toContain("source title is required");
    expect(createMock).not.toHaveBeenCalled();
  });

  it("creates evidence with the bounded payload", async () => {
    createMock.mockResolvedValue(record());
    const { container } = renderPanel();
    await screen.findByText("No evidence recorded");
    fireEvent.click(screen.getByRole("button", { name: "+ Add evidence" }));
    fireEvent.change(screen.getByLabelText(/^Source title/), {
      target: { value: "Onboarding requirements" },
    });
    fireEvent.change(screen.getByLabelText(/^Source reference/), {
      target: { value: "https://docs.example.test/onboarding" },
    });
    fireEvent.change(screen.getByLabelText(/^Summary/), {
      target: { value: "The flow is specified." },
    });
    fireEvent.submit(container.querySelector("form.evidence-form") as HTMLFormElement);
    await waitFor(() => expect(createMock).toHaveBeenCalledTimes(1));
    expect(createMock).toHaveBeenCalledWith("ws-1", {
      evidence_classification: "confirmed_by_requirements_document",
      source_type: "document",
      source_title: "Onboarding requirements",
      source_reference: "https://docs.example.test/onboarding",
      source_locator: null,
      summary: "The flow is specified.",
      confidence: "medium",
      verification_status: "unverified",
      target_kind: "architecture_object",
      target_id: "obj-1",
      created_in_state_id: null,
    });
  });

  it("edits metadata without touching provenance", async () => {
    listMock.mockResolvedValue([record()]);
    updateMock.mockResolvedValue(record({ verification_status: "disputed" }));
    const { container } = renderPanel();
    await screen.findByText("Confirmed facts");
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText(/^Verification status/), {
      target: { value: "disputed" },
    });
    fireEvent.submit(container.querySelector("form.evidence-form") as HTMLFormElement);
    await waitFor(() => expect(updateMock).toHaveBeenCalledTimes(1));
    const [, , payload] = updateMock.mock.calls[0];
    expect(payload).not.toHaveProperty("recorded_by");
    expect(payload).not.toHaveProperty("recorded_at");
    expect(payload).not.toHaveProperty("target_id");
    expect(payload.verification_status).toBe("disputed");
  });

  it("deletes only after an explicit confirmation", async () => {
    listMock.mockResolvedValue([record()]);
    deleteMock.mockResolvedValue(undefined);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderPanel();
    await screen.findByText("Confirmed facts");
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(deleteMock).not.toHaveBeenCalled();
    confirmSpy.mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(deleteMock).toHaveBeenCalledWith("ws-1", "ev-1"));
    confirmSpy.mockRestore();
  });

  it("never fetches the source reference", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch" as never);
    listMock.mockResolvedValue([record()]);
    renderPanel();
    await screen.findByText("Confirmed facts");
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
