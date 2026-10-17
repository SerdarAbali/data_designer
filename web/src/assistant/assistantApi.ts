/** Typed API access for the Architecture Assistant panel. */

import { api } from "../apiClient";
import type {
  ApplyResult,
  AssistantSettings,
  AssistantStatus,
  ChangeSetDetail,
  ChatMessage,
  ConversationDetail,
  ConversationSummary,
  ScopeSnapshot,
  UndoResult,
} from "./assistantTypes";

function base(workspaceId: string): string {
  return `/api/workspaces/${workspaceId}/assistant`;
}

export function fetchStatus(workspaceId: string): Promise<AssistantStatus> {
  return api<AssistantStatus>(`${base(workspaceId)}/status`);
}

export function fetchConversations(workspaceId: string): Promise<ConversationSummary[]> {
  return api<ConversationSummary[]>(`${base(workspaceId)}/conversations`);
}

export function fetchConversation(
  workspaceId: string,
  conversationId: string,
): Promise<ConversationDetail> {
  return api<ConversationDetail>(`${base(workspaceId)}/conversations/${conversationId}`);
}

export function createConversation(
  workspaceId: string,
  scope: ScopeSnapshot,
): Promise<ConversationSummary> {
  return api<ConversationSummary>(`${base(workspaceId)}/conversations`, {
    method: "POST",
    body: JSON.stringify({
      state_id: scope.stateId,
      discipline: scope.discipline,
      workbench_view: scope.workbenchView,
      selection_ids: scope.selectionIds,
    }),
  });
}

export function deleteConversation(workspaceId: string, conversationId: string): Promise<void> {
  return api<void>(`${base(workspaceId)}/conversations/${conversationId}`, { method: "DELETE" });
}

export function sendMessage(
  workspaceId: string,
  conversationId: string,
  content: string,
): Promise<ChatMessage> {
  return api<ChatMessage>(`${base(workspaceId)}/conversations/${conversationId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export function retryMessage(
  workspaceId: string,
  conversationId: string,
  messageId: string,
): Promise<{ status: string }> {
  return api<{ status: string }>(
    `${base(workspaceId)}/conversations/${conversationId}/messages/${messageId}/retry`,
    { method: "POST" },
  );
}

export function cancelTurn(
  workspaceId: string,
  conversationId: string,
): Promise<{ status: string }> {
  return api<{ status: string }>(`${base(workspaceId)}/conversations/${conversationId}/cancel`, {
    method: "POST",
  });
}

export function updateScope(
  workspaceId: string,
  conversationId: string,
  scope: ScopeSnapshot,
): Promise<ConversationSummary> {
  return api<ConversationSummary>(`${base(workspaceId)}/conversations/${conversationId}/scope`, {
    method: "POST",
    body: JSON.stringify({
      state_id: scope.stateId,
      discipline: scope.discipline,
      workbench_view: scope.workbenchView,
      selection_ids: scope.selectionIds,
    }),
  });
}

export function openEventStream(
  workspaceId: string,
  conversationId: string,
  since: number,
): EventSource {
  return new EventSource(
    `${base(workspaceId)}/conversations/${conversationId}/events?since=${since}`,
  );
}

// -- owner-only settings ----------------------------------------------------

export function fetchAssistantSettings(workspaceId: string): Promise<AssistantSettings> {
  return api<AssistantSettings>(`${base(workspaceId)}/settings`);
}

export function updateWorkspaceEnabled(
  workspaceId: string,
  enabled: boolean,
): Promise<{ assistant_enabled: boolean }> {
  return api<{ assistant_enabled: boolean }>(`${base(workspaceId)}/settings`, {
    method: "PUT",
    body: JSON.stringify({ assistant_enabled: enabled }),
  });
}

export function updateAssistantSettings(
  workspaceId: string,
  payload: Partial<AssistantSettings>,
): Promise<AssistantSettings> {
  return api<AssistantSettings>(`${base(workspaceId)}/settings/model`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

// -- helper change sets (authoritative proposal records) --------------------

function changeSetBase(workspaceId: string, changeSetId: string): string {
  return `/api/workspaces/${workspaceId}/helper-actions/change-sets/${changeSetId}`;
}

export function fetchChangeSet(workspaceId: string, changeSetId: string): Promise<ChangeSetDetail> {
  return api<ChangeSetDetail>(changeSetBase(workspaceId, changeSetId));
}

export function validateChangeSet(
  workspaceId: string,
  changeSetId: string,
): Promise<ChangeSetDetail> {
  return api<ChangeSetDetail>(`${changeSetBase(workspaceId, changeSetId)}/validate`, {
    method: "POST",
  });
}

export function resolveChangeSet(
  workspaceId: string,
  changeSetId: string,
  resolutions: Record<string, unknown>[],
): Promise<ChangeSetDetail> {
  return api<ChangeSetDetail>(`${changeSetBase(workspaceId, changeSetId)}/resolve`, {
    method: "POST",
    body: JSON.stringify({ resolutions }),
  });
}

export function approveChangeSet(
  workspaceId: string,
  changeSetId: string,
): Promise<ChangeSetDetail> {
  return api<ChangeSetDetail>(`${changeSetBase(workspaceId, changeSetId)}/approve`, {
    method: "POST",
  });
}

export function applyChangeSet(workspaceId: string, changeSetId: string): Promise<ApplyResult> {
  return api<ApplyResult>(`${changeSetBase(workspaceId, changeSetId)}/apply`, { method: "POST" });
}

export function undoChangeSet(workspaceId: string, changeSetId: string): Promise<UndoResult> {
  return api<UndoResult>(`${changeSetBase(workspaceId, changeSetId)}/undo`, { method: "POST" });
}

/** Record a bounded proposal lifecycle event for the originating conversation. */
export function recordProposalEvent(
  workspaceId: string,
  conversationId: string,
  changeSetId: string,
  action: string,
  reasonCode?: string | null,
): Promise<{ status: string }> {
  return api<{ status: string }>(
    `${base(workspaceId)}/conversations/${conversationId}/proposal-events`,
    {
      method: "POST",
      body: JSON.stringify({
        change_set_id: changeSetId,
        action,
        reason_code: reasonCode ?? null,
      }),
    },
  );
}
