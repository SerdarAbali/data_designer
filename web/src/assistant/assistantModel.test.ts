import { describe, expect, it } from "vitest";

import {
  applyDetail,
  initialAssistantState,
  reduceEvent,
  runtimeReady,
  statusMessage,
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
