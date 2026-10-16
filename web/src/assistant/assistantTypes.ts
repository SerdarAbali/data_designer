/** Shared types for the Architecture Assistant panel. */

export type RuntimeStatus =
  | "ready"
  | "disabled"
  | "unavailable"
  | "incompatible"
  | "misconfigured";

export type ChatRole = "user" | "assistant" | "notice";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  status: string;
  errorCode?: string | null;
}

export interface ToolActivity {
  id: string;
  name: string;
  status: string;
  errorCode?: string | null;
}

export interface ConversationSummary {
  id: string;
  title: string;
  status: string;
  state_id: string | null;
  state_type: string | null;
  discipline: string | null;
  workbench_view: string | null;
  message_count: number;
  tool_call_count: number;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: ChatMessage[];
  tool_calls: ToolActivity[];
}

export interface AssistantStatus {
  assistant_enabled: boolean;
  runtime_status: RuntimeStatus;
  expected_opencode_version: string;
  observed_opencode_version: string | null;
  probe_checked_at: string;
  reason_code: string;
  correlation_id: string;
  workspace_enabled?: boolean;
}

export interface ScopeSnapshot {
  stateId: string | null;
  discipline: string | null;
  workbenchView: string;
  selectionIds: string[];
}

export interface AssistantEvent {
  type: string;
  seq: number;
  at?: string;
  text?: string;
  tool?: string;
  status?: string;
  reason?: string;
  chars?: number;
}

export interface AssistantState {
  status: AssistantStatus | null;
  conversations: ConversationSummary[];
  activeId: string | null;
  messages: ChatMessage[];
  tools: ToolActivity[];
  streaming: boolean;
  error: string;
  loaded: boolean;
}

export function initialAssistantState(): AssistantState {
  return {
    status: null,
    conversations: [],
    activeId: null,
    messages: [],
    tools: [],
    streaming: false,
    error: "",
    loaded: false,
  };
}
