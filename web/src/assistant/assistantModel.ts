/**
 * Pure reducers and selectors for the Architecture Assistant panel.
 *
 * Kept free of React so behaviour (streaming, cancellation, tool activity,
 * disabled states) is unit-testable without a DOM.
 */

import type {
  AssistantEvent,
  AssistantState,
  ChangeSetDetail,
  ChatMessage,
  ConversationDetail,
  ProposalOperation,
  RuntimeStatus,
  ToolActivity,
} from "./assistantTypes";

export { initialAssistantState } from "./assistantTypes";

const STREAMING_ID = "assistant-streaming";

/** The tool-activity timeline keeps only the most recent entries so a long
 * multi-step turn does not fill the panel with identical rows. The durable
 * record (conversation detail / assistant tool calls table) still holds every
 * call, and the conversation meta line still reports the true total. */
export const MAX_TOOL_ACTIVITY_ENTRIES = 20;

function trimTools(tools: ToolActivity[]): ToolActivity[] {
  if (tools.length <= MAX_TOOL_ACTIVITY_ENTRIES) return tools;
  return tools.slice(tools.length - MAX_TOOL_ACTIVITY_ENTRIES);
}

const UUID_PATTERN = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
const UUID_ONLY = new RegExp(`^${UUID_PATTERN}$`);

/**
 * Collapse an opaque identifier for display. A bare UUID is shortened to its
 * first eight characters; readable temporary ids (e.g. `tmp:customer`) are left
 * untouched. Never mutates the stored value, only the rendered text.
 */
export function humanizeId(id: string | null | undefined): string {
  if (!id) return "";
  return UUID_ONLY.test(id) ? `${id.slice(0, 8)}…` : id;
}

/** Shorten every UUID embedded in free text (e.g. assistant prose) for display. */
export function humanizeIds(text: string): string {
  return text.replace(new RegExp(UUID_PATTERN, "g"), (match) => `${match.slice(0, 8)}…`);
}

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
  const next = [
    ...tools,
    {
      id,
      name: event.tool ?? "tool",
      status: event.status ?? "completed",
      errorCode: event.status === "error" ? "tool_error" : null,
    },
  ];
  return trimTools(next);
}

export function applyDetail(state: AssistantState, detail: ConversationDetail): AssistantState {
  return {
    ...state,
    activeId: detail.id,
    messages: detail.messages,
    tools: trimTools(detail.tool_calls),
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

// -- proposal lifecycle ----------------------------------------------------

export type ProposalLifecycle =
  | "draft"
  | "needs_decisions"
  | "validation_failed"
  | "validated"
  | "ready_for_approval"
  | "approved"
  | "applying"
  | "applied"
  | "apply_failed"
  | "undo_available"
  | "undo_conflict"
  | "undone"
  | "stale";

export const LIFECYCLE_LABELS: Record<ProposalLifecycle, string> = {
  draft: "Draft",
  needs_decisions: "Needs decisions",
  validation_failed: "Validation failed",
  validated: "Validated",
  ready_for_approval: "Ready for approval",
  approved: "Approved",
  applying: "Applying",
  applied: "Applied",
  apply_failed: "Apply failed",
  undo_available: "Undo available",
  undo_conflict: "Undo conflict",
  undone: "Undone",
  stale: "Stale",
};

export interface ProposalActionState {
  applying?: boolean;
  applyFailed?: boolean;
  undoConflict?: boolean;
}

export function hasRequiredUnresolved(changeSet: ChangeSetDetail | null): boolean {
  if (!changeSet) return false;
  return (changeSet.unresolved_details ?? []).some(
    (decision) => decision.required && decision.resolution_state !== "resolved",
  );
}

export function proposalLifecycle(
  changeSet: ChangeSetDetail | null,
  action: ProposalActionState = {},
): ProposalLifecycle {
  if (!changeSet) return "draft";
  if (action.applying) return "applying";
  if (action.applyFailed) return "apply_failed";
  if (action.undoConflict) return "undo_conflict";
  switch (changeSet.status) {
    case "stale":
      return "stale";
    case "undone":
      return "undone";
    case "applied":
      return "undo_available";
    case "approved":
      return "approved";
    case "validation_failed":
      return "validation_failed";
    case "validated":
      return changeSet.validation_summary?.ready_for_approval ? "ready_for_approval" : "validated";
    default:
      return hasRequiredUnresolved(changeSet) ? "needs_decisions" : "draft";
  }
}

/** Validate is allowed on a draft (or resolved) proposal that is not stale/terminal. */
export function canValidate(changeSet: ChangeSetDetail | null): boolean {
  if (!changeSet) return false;
  return !["stale", "applied", "undone"].includes(changeSet.status);
}

/** Approve requires a validated, ready proposal with no required unresolved decisions. */
export function canApprove(changeSet: ChangeSetDetail | null): boolean {
  if (!changeSet) return false;
  return (
    changeSet.status === "validated" &&
    Boolean(changeSet.validation_summary?.ready_for_approval) &&
    !hasRequiredUnresolved(changeSet)
  );
}

/** Apply requires an approved proposal in a Candidate or Target state. */
export function canApply(changeSet: ChangeSetDetail | null): boolean {
  if (!changeSet) return false;
  return changeSet.status === "approved" && changeSet.state_type !== "current";
}

/** Undo requires an applied proposal that has not already been undone. */
export function canUndo(changeSet: ChangeSetDetail | null): boolean {
  if (!changeSet) return false;
  return changeSet.status === "applied";
}

/** Count active operations by domain action (removed operations are excluded). */
export function operationCounts(operations: ProposalOperation[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const operation of operations) {
    if (operation.resolution_state === "removed") continue;
    counts[operation.domain_action] = (counts[operation.domain_action] ?? 0) + 1;
  }
  return counts;
}
