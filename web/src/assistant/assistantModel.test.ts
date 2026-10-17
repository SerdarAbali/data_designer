import { describe, expect, it } from "vitest";

import {
  applyDetail,
  canApply,
  canApprove,
  canUndo,
  canValidate,
  humanizeId,
  humanizeIds,
  initialAssistantState,
  proposalLifecycle,
  reduceEvent,
  resolveAssistantScope,
  runtimeReady,
  statusMessage,
  DEFAULT_CANVAS_SCOPE,
  MAX_TOOL_ACTIVITY_ENTRIES,
} from "./assistantModel";
import type { AssistantEvent, ConversationDetail } from "./assistantTypes";

function event(partial: Partial<AssistantEvent> & { type: string; seq: number }): AssistantEvent {
  return { ...partial };
}

describe("assistant model", () => {
  it("streams assistant deltas into a single message", () => {
    let state = initialAssistantState();
    state = reduceEvent(state, event({ type: "turn.started", seq: 1 }));
    expect(state.streaming).toBe(true);
    state = reduceEvent(state, event({ type: "assistant.delta", seq: 2, text: "Hello" }));
    state = reduceEvent(state, event({ type: "assistant.delta", seq: 3, text: "Hello world" }));
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0].content).toBe("Hello world");
    expect(state.messages[0].status).toBe("streaming");
  });

  it("completes the streamed message", () => {
    let state = initialAssistantState();
    state = reduceEvent(state, event({ type: "assistant.delta", seq: 1, text: "Done" }));
    state = reduceEvent(state, event({ type: "assistant.message.completed", seq: 2 }));
    expect(state.streaming).toBe(false);
    expect(state.messages[0].status).toBe("complete");
  });

  it("records tool activity once per sequence", () => {
    let state = initialAssistantState();
    state = reduceEvent(
      state,
      event({ type: "tool.completed", seq: 1, tool: "architecture_get_workspace_context", status: "completed" }),
    );
    state = reduceEvent(
      state,
      event({ type: "tool.completed", seq: 1, tool: "architecture_get_workspace_context", status: "completed" }),
    );
    expect(state.tools).toHaveLength(1);
    expect(state.tools[0].name).toBe("architecture_get_workspace_context");
  });

  it("shortens opaque identifiers for display", () => {
    expect(humanizeId("5b54f3d8-dc67-49ff-84c1-7dd31e6421b4")).toBe("5b54f3d8…");
    expect(humanizeId("tmp:customer")).toBe("tmp:customer");
    expect(humanizeId("")).toBe("");
    expect(humanizeId(null)).toBe("");
    expect(
      humanizeIds("Created proposal `ace48dea-edb5-4254-af76-d70b02ae8c5e` and tmp:customer"),
    ).toBe("Created proposal `ace48dea…` and tmp:customer");
  });

  it("keeps only the most recent tool activity entries", () => {
    let state = initialAssistantState();
    for (let seq = 1; seq <= 25; seq++) {
      state = reduceEvent(
        state,
        event({ type: "tool.completed", seq, tool: `tool_${seq}`, status: "completed" }),
      );
    }
    expect(state.tools).toHaveLength(MAX_TOOL_ACTIVITY_ENTRIES);
    expect(state.tools[0].name).toBe("tool_6");
    expect(state.tools[MAX_TOOL_ACTIVITY_ENTRIES - 1].name).toBe("tool_25");
  });

  it("surfaces turn failures and cancellations", () => {
    let state = initialAssistantState();
    state = reduceEvent(state, event({ type: "assistant.delta", seq: 1, text: "partial" }));
    state = reduceEvent(state, event({ type: "turn.cancelled", seq: 2 }));
    expect(state.messages[0].status).toBe("cancelled");
    expect(state.streaming).toBe(false);

    state = reduceEvent(state, event({ type: "turn.failed", seq: 3, reason: "turn_timeout" }));
    expect(state.error).toBe("turn_timeout");
  });

  it("loads a conversation detail", () => {
    const detail: ConversationDetail = {
      id: "c1",
      title: "T",
      status: "active",
      state_id: null,
      state_type: null,
      discipline: null,
      workbench_view: null,
      message_count: 1,
      tool_call_count: 0,
      last_message_at: null,
      created_at: "",
      updated_at: "",
      messages: [{ id: "m1", role: "user", content: "hi", status: "complete" }],
      tool_calls: [],
    };
    const state = applyDetail(initialAssistantState(), detail);
    expect(state.activeId).toBe("c1");
    expect(state.messages).toHaveLength(1);
  });

  it("derives the proposal lifecycle and action gating", () => {
    const base = {
      id: "cs-1",
      helper_name: "h",
      status: "draft",
      state_id: "s",
      state_type: "candidate",
      summary: "s",
      proposal_hash: "hash",
      assumptions: [],
      warnings: [],
      unresolved_decisions: [],
      unresolved_details: [],
      reused_objects: [],
      proposed_objects: [],
      validation_summary: {},
      validated_at: null,
      approved_at: null,
      approved_hash: null,
      applied_at: null,
      undone_at: null,
      apply_summary: {},
      undo_summary: {},
      operations: [],
    };
    expect(proposalLifecycle(base)).toBe("draft");
    expect(canApprove(base)).toBe(false);
    expect(canApply(base)).toBe(false);
    expect(canUndo(base)).toBe(false);
    expect(canValidate(base)).toBe(true);

    const needsDecision = {
      ...base,
      unresolved_details: [
        {
          decision_id: "d",
          operation_id: "op-1",
          kind: "choose_canonical_object",
          question: "q",
          explanation: "e",
          options: [],
          required: true,
          affected_operation_ids: ["op-1"],
          resolution_state: "open",
        },
      ],
    };
    expect(proposalLifecycle(needsDecision)).toBe("needs_decisions");

    const ready = { ...base, status: "validated", validation_summary: { ready_for_approval: true } };
    expect(proposalLifecycle(ready)).toBe("ready_for_approval");
    expect(canApprove(ready)).toBe(true);

    const approved = { ...base, status: "approved" };
    expect(proposalLifecycle(approved)).toBe("approved");
    expect(canApply(approved)).toBe(true);
    expect(canApply({ ...approved, state_type: "current" })).toBe(false);

    const applied = { ...base, status: "applied" };
    expect(proposalLifecycle(applied)).toBe("undo_available");
    expect(canUndo(applied)).toBe(true);

    expect(proposalLifecycle(base, { applying: true })).toBe("applying");
    expect(proposalLifecycle(base, { applyFailed: true })).toBe("apply_failed");
    expect(proposalLifecycle(base, { undoConflict: true })).toBe("undo_conflict");
    expect(proposalLifecycle({ ...base, status: "stale" })).toBe("stale");
    expect(canValidate({ ...base, status: "applied" })).toBe(false);
  });

  it("resolves the assistant scope from the canvas context", () => {
    const integration = resolveAssistantScope(
      {
        ...DEFAULT_CANVAS_SCOPE,
        discipline: "integration",
        workbenchView: "integration",
        stateId: "s1",
        selectionIds: ["obj-1"],
      },
      "canvas",
    );
    expect(integration.discipline).toBe("integration");
    expect(integration.workbenchView).toBe("integration");
    expect(integration.selectionIds).toEqual(["obj-1"]);

    expect(resolveAssistantScope(DEFAULT_CANVAS_SCOPE, "catalog").workbenchView).toBe("catalog");
    expect(resolveAssistantScope(DEFAULT_CANVAS_SCOPE, "integrations").workbenchView).toBe(
      "integration",
    );
  });

  it("reports readiness and disabled states", () => {
    expect(runtimeReady(null)).toBe(false);
    expect(
      runtimeReady({
        assistant_enabled: true,
        runtime_status: "ready",
        expected_opencode_version: "2.0.30",
        observed_opencode_version: "2.0.30",
        probe_checked_at: "",
        reason_code: "ok",
        correlation_id: "cor",
        workspace_enabled: true,
      }),
    ).toBe(true);
    expect(
      statusMessage({
        assistant_enabled: false,
        runtime_status: "disabled",
        expected_opencode_version: "2.0.30",
        observed_opencode_version: null,
        probe_checked_at: "",
        reason_code: "assistant_disabled",
        correlation_id: "cor",
        workspace_enabled: false,
      }),
    ).toContain("disabled for this workspace");
  });
});
