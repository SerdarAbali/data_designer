/** Typed API access for the Architecture Assistant panel. */

import { api } from "../apiClient";
import type {
  AssistantStatus,
  ChatMessage,
  ConversationDetail,
  ConversationSummary,
  ScopeSnapshot,
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
