/** Assistant panel state hook: conversations, streaming, and lifecycle. */

import React from "react";

import * as assistantApi from "./assistantApi";
import { applyDetail, initialAssistantState, reduceEvent } from "./assistantModel";
import type {
  AssistantEvent,
  AssistantState,
  AssistantStatus,
  ConversationDetail,
  ConversationSummary,
  ScopeSnapshot,
} from "./assistantTypes";

type Action =
  | { type: "status"; status: AssistantStatus }
  | { type: "conversations"; conversations: ConversationSummary[] }
  | { type: "detail"; detail: ConversationDetail }
  | { type: "event"; event: AssistantEvent }
  | { type: "error"; message: string }
  | { type: "reset" };

function reducer(state: AssistantState, action: Action): AssistantState {
  switch (action.type) {
    case "status":
      return { ...state, status: action.status, loaded: true };
    case "conversations":
      return {
        ...state,
        conversations: action.conversations,
        activeId:
          state.activeId && action.conversations.some((c) => c.id === state.activeId)
            ? state.activeId
            : (action.conversations[0]?.id ?? null),
      };
    case "detail":
      return applyDetail(state, action.detail);
    case "event":
      return reduceEvent(state, action.event);
    case "error":
      return { ...state, error: action.message, streaming: false };
    case "reset":
      return initialAssistantState();
    default:
      return state;
  }
}

export function useAssistant(workspaceId: string | null, scope: ScopeSnapshot) {
  const [state, dispatch] = React.useReducer(reducer, undefined, initialAssistantState);
  const lastSeq = React.useRef(0);
  const sourceRef = React.useRef<EventSource | null>(null);
  const scopeRef = React.useRef(scope);
  scopeRef.current = scope;

  const refreshStatus = React.useCallback(async () => {
    if (!workspaceId) return;
    try {
      dispatch({ type: "status", status: await assistantApi.fetchStatus(workspaceId) });
    } catch (error) {
      dispatch({ type: "error", message: error instanceof Error ? error.message : "Status failed" });
    }
  }, [workspaceId]);

  const refreshConversations = React.useCallback(async () => {
    if (!workspaceId) return;
    try {
      const conversations = await assistantApi.fetchConversations(workspaceId);
      dispatch({ type: "conversations", conversations });
    } catch (error) {
      dispatch({
        type: "error",
        message: error instanceof Error ? error.message : "Could not load conversations",
      });
    }
  }, [workspaceId]);

  React.useEffect(() => {
    dispatch({ type: "reset" });
    lastSeq.current = 0;
    void refreshStatus();
    void refreshConversations();
  }, [workspaceId, refreshStatus, refreshConversations]);

  // Load the active conversation detail and subscribe to its durable events.
  React.useEffect(() => {
    if (!workspaceId || !state.activeId) return;
    const conversationId = state.activeId;
    lastSeq.current = 0;
    void assistantApi
      .fetchConversation(workspaceId, conversationId)
      .then((detail) => dispatch({ type: "detail", detail }))
      .catch((error) =>
        dispatch({
          type: "error",
          message: error instanceof Error ? error.message : "Could not load the conversation",
        }),
      );

    const source = assistantApi.openEventStream(workspaceId, conversationId, 0);
    sourceRef.current = source;
    source.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as AssistantEvent;
        if (typeof event.seq === "number" && event.seq <= lastSeq.current) return;
        if (typeof event.seq === "number") lastSeq.current = event.seq;
        dispatch({ type: "event", event });
      } catch {
        /* ignore malformed events */
      }
    };
    return () => {
      source.close();
      sourceRef.current = null;
    };
  }, [workspaceId, state.activeId]);

  const newConversation = React.useCallback(async () => {
    if (!workspaceId) return;
    try {
      const conversation = await assistantApi.createConversation(workspaceId, scopeRef.current);
      dispatch({ type: "conversations", conversations: [conversation, ...state.conversations] });
      dispatch({ type: "detail", detail: { ...conversation, messages: [], tool_calls: [] } });
      lastSeq.current = 0;
    } catch (error) {
      dispatch({ type: "error", message: error instanceof Error ? error.message : "Could not start" });
    }
  }, [workspaceId, state.conversations]);

  const removeConversation = React.useCallback(
    async (conversationId: string) => {
      if (!workspaceId) return;
      try {
        await assistantApi.deleteConversation(workspaceId, conversationId);
        await refreshConversations();
        dispatch({ type: "detail", detail: { ...emptyDetail(conversationId) } });
      } catch (error) {
        dispatch({ type: "error", message: error instanceof Error ? error.message : "Delete failed" });
      }
    },
    [workspaceId, refreshConversations],
  );

  const send = React.useCallback(
    async (content: string) => {
      if (!workspaceId || !state.activeId) return;
      dispatch({ type: "error", message: "" });
      try {
        const message = await assistantApi.sendMessage(workspaceId, state.activeId, content);
        dispatch({
          type: "detail",
          detail: { ...emptyDetail(state.activeId), messages: [message] },
        });
        await assistantApi.updateScope(workspaceId, state.activeId, scopeRef.current);
      } catch (error) {
        dispatch({ type: "error", message: error instanceof Error ? error.message : "Send failed" });
      }
    },
    [workspaceId, state.activeId],
  );

  const cancel = React.useCallback(async () => {
    if (!workspaceId || !state.activeId) return;
    try {
      await assistantApi.cancelTurn(workspaceId, state.activeId);
    } catch (error) {
      dispatch({ type: "error", message: error instanceof Error ? error.message : "Cancel failed" });
    }
  }, [workspaceId, state.activeId]);

  const retry = React.useCallback(
    async (messageId: string) => {
      if (!workspaceId || !state.activeId) return;
      try {
        await assistantApi.retryMessage(workspaceId, state.activeId, messageId);
      } catch (error) {
        dispatch({ type: "error", message: error instanceof Error ? error.message : "Retry failed" });
      }
    },
    [workspaceId, state.activeId],
  );

  return {
    state,
    refreshStatus,
    newConversation,
    removeConversation,
    selectConversation: (conversationId: string) => {
      lastSeq.current = 0;
      dispatch({ type: "detail", detail: emptyDetail(conversationId) });
    },
    send,
    cancel,
    retry,
  };
}

function emptyDetail(conversationId: string): ConversationDetail {
  return {
    id: conversationId,
    title: "",
    status: "active",
    state_id: null,
    state_type: null,
    discipline: null,
    workbench_view: null,
    message_count: 0,
    tool_call_count: 0,
    last_message_at: null,
    created_at: "",
    updated_at: "",
    messages: [],
    tool_calls: [],
  };
}
