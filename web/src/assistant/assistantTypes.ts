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
  is_owner?: boolean;
}

export interface AssistantSettings {
  workspace_enabled: boolean;
  is_owner: boolean;
  provider?: string | null;
  model_id?: string | null;
  model_variant?: string | null;
  reasoning_effort?: string | null;
  max_input_tokens?: number | null;
  max_output_tokens?: number | null;
  timeout_seconds?: number | null;
  step_limit?: number | null;
  retention_days?: number | null;
  privacy_classification?: string | null;
  trains_on_data?: boolean | null;
  approved_for_sensitive?: boolean | null;
  fallback_provider?: string | null;
  fallback_model_id?: string | null;
  fallback_enabled?: boolean | null;
  credential_status?: string | null;
  credential_last_verified_at?: string | null;
  privacy_allowed?: boolean | null;
  privacy_reason?: string | null;
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
  change_set_id?: string;
}

export interface ProposalOperation {
  operation_id: string;
  ordinal: number;
  domain_action: string;
  target_type: string;
  target_id: string | null;
  temporary_id: string | null;
  proposed_value: Record<string, unknown>;
  depends_on: string[];
  validation_status: string;
  validation_issues: { code?: string; message?: string }[];
  resolution_state: string;
  explanation?: string | null;
}

export interface ProposalDecision {
  decision_id: string;
  operation_id: string;
  kind: string;
  question: string;
  explanation: string;
  options: { key: string; label: string; object_id?: string | null }[];
  required: boolean;
  affected_operation_ids: string[];
  resolution_state: string;
}

export interface ChangeSetDetail {
  id: string;
  helper_name: string;
  status: string;
  state_id: string | null;
  state_type: string | null;
  summary: string | null;
  proposal_hash: string | null;
  assumptions: unknown[];
  warnings: unknown[];
  unresolved_decisions: unknown[];
  unresolved_details: ProposalDecision[];
  reused_objects: { target_type?: string; target_id?: string; name?: string }[];
  proposed_objects: { temporary_id?: string; target_type?: string; name?: string }[];
  validation_summary: Record<string, unknown>;
  validated_at: string | null;
  approved_at: string | null;
  approved_hash: string | null;
  applied_at: string | null;
  undone_at: string | null;
  apply_summary: Record<string, unknown>;
  undo_summary: Record<string, unknown>;
  operations: ProposalOperation[];
}

export interface AppliedOperation {
  operation_id: string;
  domain_action: string;
  applied_id: string;
  role?: string;
  apply_status?: string;
  result?: Record<string, unknown>;
}

export interface ApplyResult {
  change_set: ChangeSetDetail;
  status: string;
  applied_operation_count: number;
  resolution_map: Record<string, string>;
  applied_operations: AppliedOperation[];
  contract_revisions: { contract_id: string; revision: number; role?: string }[];
  affected_objects: string[];
  affected_workbenches: string[];
  warnings: unknown[];
  conflicts: { code?: string; message?: string }[];
  audit_event_ref?: string | null;
}

export interface UndoResult {
  change_set: ChangeSetDetail;
  status: string;
  undone_operation_count: number;
  undone_operations: { operation_id: string; domain_action: string; action: string }[];
  preserved_objects: string[];
  warnings: unknown[];
  conflicts: { operation_id?: string; code?: string; message?: string }[];
  audit_event_ref?: string | null;
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
  proposalIds: string[];
  activeProposalId: string | null;
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
    proposalIds: [],
    activeProposalId: null,
  };
}
