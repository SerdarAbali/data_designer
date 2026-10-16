/**
 * Pure reducers and selectors for the Architecture Assistant panel.
 *
 * Kept free of React so behaviour (streaming, cancellation, tool activity,
 * disabled states) is unit-testable without a DOM.
 */

import type {
  AssistantEvent,
  AssistantState,
  ChatMessage,
  ConversationDetail,
  RuntimeStatus,
  ToolActivity,
} from "./assistantTypes";

export { initialAssistantState } from "./assistantTypes";

const STREAMING_ID = "assistant-streaming";

export function reduceEvent(state: AssistantState, event: AssistantEvent): AssistantState {
  switch (event.type) {
    case "turn.started":
      return { ...state, streaming: true, error: "" };
    case "assistant.delta":
      return {
        ...state,
        streaming: true,
        messages: upsertStreaming(state.messages, event.text ?? ""),
      };
    case "assistant.message.completed": {
      const messages = state.messages.map((message) =>
        message.id === STREAMING_ID ? { ...message, status: "complete" } : message,
      );
      return { ...state, streaming: false, messages };
    }
    case "tool.completed":
      return { ...state, tools: appendTool(state.tools, event) };
    case "proposal.created": {
      const id = event.change_set_id ?? null;
      if (!id) return state;
      return {
        ...state,
        activeProposalId: id,
        proposalIds: state.proposalIds.includes(id) ? state.proposalIds : [...state.proposalIds, id],
      };
    }
    case "proposal.selected": {
      const id = event.change_set_id ?? null;
      return id ? { ...state, activeProposalId: id } : state;
    }
    case "proposal.validated":
    case "proposal.validation_failed":
    case "proposal.stale":
      return state;
    case "turn.cancelled":
      return {
        ...state,
        streaming: false,
        messages: state.messages.map((message) =>
          message.id === STREAMING_ID ? { ...message, status: "cancelled" } : message,
        ),
      };
    case "turn.failed":
      return { ...state, streaming: false, error: event.reason ?? "The assistant turn failed." };
    case "heartbeat":
      return state;
    default:
      return state;
  }
}

export function upsertStreaming(messages: ChatMessage[], text: string): ChatMessage[] {
  const existing = messages.find((message) => message.id === STREAMING_ID);
  if (existing) {
    return messages.map((message) =>
      message.id === STREAMING_ID ? { ...message, content: text, status: "streaming" } : message,
    );
  }
  return [
    ...messages,
    { id: STREAMING_ID, role: "assistant", content: text, status: "streaming", errorCode: null },
  ];
}

export function appendTool(tools: ToolActivity[], event: AssistantEvent): ToolActivity[] {
  const id = `${event.tool ?? "tool"}:${event.seq}`;
  if (tools.some((tool) => tool.id === id)) return tools;
  return [
    ...tools,
    {
      id,
      name: event.tool ?? "tool",
      status: event.status ?? "completed",
      errorCode: event.status === "error" ? "tool_error" : null,
    },
  ];
}

export function applyDetail(state: AssistantState, detail: ConversationDetail): AssistantState {
  return {
    ...state,
    activeId: detail.id,
    messages: detail.messages,
    tools: detail.tool_calls,
    streaming: false,
    error: "",
  };
}

export function runtimeReady(status: AssistantState["status"]): boolean {
  return Boolean(status && status.workspace_enabled !== false && status.runtime_status === "ready");
}

export function statusMessage(status: AssistantState["status"]): string {
  if (!status) return "Checking assistant availability…";
  if (status.workspace_enabled === false) {
    return "The assistant is disabled for this workspace. A workspace owner can enable it.";
  }
  switch (status.runtime_status as RuntimeStatus) {
    case "ready":
      return "Ready — read-only architecture assistant.";
    case "disabled":
      return "The assistant is disabled.";
    case "unavailable":
      return "The assistant runtime is unavailable. Retry shortly.";
    case "incompatible":
      return "The assistant runtime is incompatible with this build.";
    case "misconfigured":
      return "The assistant runtime is misconfigured.";
    default:
      return "The assistant is unavailable.";
  }
}

export const READ_ONLY_NOTICE =
  "The Assistant can inspect architecture and prepare proposals. It cannot approve, apply, or undo changes. Those actions require you.";

export const CURRENT_READ_ONLY_NOTICE =
  "Current is read-only. Switch to a Candidate or Target state to prepare proposals.";

/** The active context published by the architecture canvas. */
export interface CanvasScope {
  discipline: string;
  workbenchView: string;
  stateId: string | null;
  selectionIds: string[];
}

export const DEFAULT_CANVAS_SCOPE: CanvasScope = {
  discipline: "enterprise",
  workbenchView: "canvas",
  stateId: null,
  selectionIds: [],
};

/**
 * The assistant context for the active workspace view. The canvas is the source
 * of truth for discipline/state/selection; only the view label is adjusted for
 * the catalog and integration workspaces.
 */
export function resolveAssistantScope(canvasScope: CanvasScope, activeView: string): CanvasScope {
  if (activeView === "catalog") return { ...canvasScope, workbenchView: "catalog" };
  if (activeView === "integrations") return { ...canvasScope, workbenchView: "integration" };
  return canvasScope;
}
