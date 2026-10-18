/**
 * Architecture Assistant panel.
 *
 * A custom, read-only panel: conversation selector, transcript, streaming,
 * cancel/retry, tool-activity timeline, context chips, and disabled/unavailable
 * states. It never embeds the generic OpenCode UI and offers no proposal,
 * approval, apply, or undo controls.
 */

import React from "react";

import {
  CURRENT_READ_ONLY_NOTICE,
  READ_ONLY_NOTICE,
  humanizeIds,
  runtimeReady,
  statusMessage,
} from "./assistantModel";
import type { ApplyResult, ScopeSnapshot } from "./assistantTypes";
import { ProposalPanel } from "./ProposalPanel";
import { AssistantSettingsPanel } from "./AssistantSettingsPanel";
import { useAssistant } from "./useAssistant";

export interface AssistantPanelProps {
  workspaceId: string | null;
  workspaceName: string;
  disciplines: string[];
  discipline: string;
  states: { id: string; name: string; state_type: string }[];
  stateId: string | null;
  workbenchView: string;
  selectionIds: string[];
  open: boolean;
  onClose: () => void;
  onProposalApplied?: (result: ApplyResult) => void;
  onProposalUndone?: () => void;
  onProposalHighlightsCleared?: () => void;
}

export function AssistantLauncher({ onOpen, open }: { onOpen: () => void; open: boolean }) {
  return (
    <button
      type="button"
      className="assistant-launcher"
      aria-label="Open the architecture assistant"
      aria-expanded={open}
      onClick={onOpen}
    >
      Assistant
    </button>
  );
}

export function AssistantPanel({
  workspaceId,
  workspaceName,
  disciplines,
  discipline,
  states,
  stateId,
  workbenchView,
  selectionIds,
  open,
  onClose,
  onProposalApplied,
  onProposalUndone,
  onProposalHighlightsCleared,
}: AssistantPanelProps) {
  const fallbackStateId =
    states.find((state) => state.state_type !== "current")?.id ?? states[0]?.id ?? null;
  const [stateOverride, setStateOverride] = React.useState<string | null>(null);
  const [draft, setDraft] = React.useState("");
  const [settingsOpen, setSettingsOpen] = React.useState(false);
  const [toolsOpen, setToolsOpen] = React.useState(false);
  const [assistantMoreOpen, setAssistantMoreOpen] = React.useState(false);

  React.useEffect(() => {
    setStateOverride(null);
  }, [stateId]);

  const effectiveStateId = stateOverride ?? stateId ?? fallbackStateId;
  const activeState = states.find((state) => state.id === effectiveStateId) ?? null;
  const isCurrent = activeState?.state_type === "current";

  const scope: ScopeSnapshot = React.useMemo(
    () => ({
      stateId: effectiveStateId,
      discipline,
      workbenchView,
      selectionIds,
    }),
    [effectiveStateId, discipline, workbenchView, selectionIds],
  );

  const { state, newConversation, removeConversation, selectConversation, send, cancel, retry } =
    useAssistant(workspaceId, scope);

  const ready = runtimeReady(state.status);
  const activeConversation = state.conversations.find((item) => item.id === state.activeId) ?? null;
  const lastUserMessage = [...state.messages].reverse().find((message) => message.role === "user");

  const toolErrors = state.tools.filter((tool) =>
    ["error", "failed", "cancelled"].includes(tool.status),
  ).length;
  const toolRunning = state.tools.filter((tool) =>
    ["running", "streaming", "started"].includes(tool.status),
  ).length;
  const toolComplete = state.tools.length - toolErrors - toolRunning;

  const previousFocus = React.useRef<HTMLElement | null>(null);
  React.useEffect(() => {
    if (open) {
      previousFocus.current =
        document.activeElement instanceof HTMLElement ? document.activeElement : null;
    } else if (previousFocus.current?.isConnected) {
      previousFocus.current.focus();
      previousFocus.current = null;
    }
  }, [open]);

  function statusTone(value: string): "info" | "success" | "warning" | "danger" | "muted" {
    const normalized = value.toLowerCase();
    if (["complete", "completed", "succeeded", "success", "ready"].includes(normalized)) return "success";
    if (["running", "streaming", "started", "thinking", "reading", "preparing"].includes(normalized)) return "info";
    if (["cancelled", "canceled", "stale", "paused"].includes(normalized)) return "warning";
    if (["error", "failed", "unavailable", "incompatible", "misconfigured", "disabled"].includes(normalized)) return "danger";
    return "muted";
  }


  function submit(event: React.FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || !ready) return;
    setDraft("");
    void send(content);
  }

  return (
    <aside
      className="assistant-panel side-panel"
      data-testid="assistant-panel"
      hidden={!open}
      aria-label="Architecture Assistant"
      role="dialog"
      aria-modal="false"
    >
      <header className="assistant-header side-panel-header">
        <div className="side-panel-heading">
          <h2 className="assistant-title side-panel-title">Architecture Assistant</h2>
          <div className="side-panel-context">
            <span
              className="status-badge"
              data-tone={ready ? "success" : statusTone(state.status?.runtime_status ?? "unavailable")}
              data-ready={ready}
            >
              {statusMessage(state.status)}
            </span>
          </div>
        </div>
        <div className="side-panel-controls assistant-header-actions">
          <div className="more-menu">
            <button
              type="button"
              className="more-menu-trigger"
              aria-expanded={assistantMoreOpen}
              aria-label="More assistant actions"
              onClick={() => setAssistantMoreOpen((open) => !open)}
            >
              More ⌄
            </button>
            <section className="more-menu-panel" hidden={!assistantMoreOpen} aria-label="More assistant actions">
              <button
                type="button"
                className="more-menu-item more-menu-item--danger"
                onClick={() => state.activeId && void removeConversation(state.activeId)}
                disabled={!state.activeId}
              >
                Delete conversation
              </button>
              {state.status?.is_owner ? (
                <button
                  type="button"
                  className="more-menu-item"
                  data-testid="open-settings"
                  onClick={() => setSettingsOpen(true)}
                >
                  Assistant settings
                </button>
              ) : null}
            </section>
          </div>
          <button
            type="button"
            className="side-panel-icon-button"
            aria-label="Close assistant"
            title="Close assistant"
            onClick={onClose}
          >
            ✕
          </button>
        </div>
      </header>

      <div className="assistant-toolbar-row">
        <label className="assistant-conversation-select">
          <span className="assistant-field-label">Conversation</span>
          <select
            aria-label="Conversation"
            value={state.activeId ?? ""}
            onChange={(event) => selectConversation(event.target.value)}
          >
            {state.conversations.length === 0 && <option value="">No conversations yet</option>}
            {state.conversations.map((conversation) => (
              <option key={conversation.id} value={conversation.id}>
                {conversation.title}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="btn btn--quiet" onClick={() => void newConversation()} disabled={!ready}>
          New conversation
        </button>
      </div>

      <div className="assistant-panel-scroll">
        <p className="assistant-readonly" role="note">
          {READ_ONLY_NOTICE}
        </p>
        {isCurrent ? (
          <p className="assistant-readonly assistant-current-notice" role="note">
            {CURRENT_READ_ONLY_NOTICE}
          </p>
        ) : null}

        {state.status?.observed_opencode_version ? (
          <p className="assistant-meta">
            Runtime ready · OpenCode {state.status.observed_opencode_version}
          </p>
        ) : null}

        {state.error ? (
          <p className="assistant-error" role="alert">
            {state.error}
            {state.status?.correlation_id ? (
              <span className="assistant-error-hint">
                Try again. Reference: {state.status.correlation_id}
              </span>
            ) : null}
          </p>
        ) : null}

        <details className="assistant-context" open>
          <summary className="assistant-context-summary">
            Context · {workspaceName || "Workspace"} · {activeState?.name ?? "No state"}
          </summary>
          <div className="assistant-chips">
            <span className="assistant-chip">{workspaceName || "Workspace"}</span>
            <label className="assistant-chip">
              State
              <select
                aria-label="Architecture state"
                value={effectiveStateId ?? ""}
                onChange={(event) => setStateOverride(event.target.value || null)}
              >
                {states.map((state) => (
                  <option key={state.id} value={state.id}>
                    {state.name} ({state.state_type})
                  </option>
                ))}
              </select>
            </label>
            <span className="assistant-chip">Discipline: {scope.discipline ?? "all"}</span>
            <span className="assistant-chip">View: {workbenchView}</span>
            <span className="assistant-chip">Selected: {selectionIds.length}</span>
          </div>
        </details>

        {state.tools.length > 0 ? (
          <details className="assistant-tools" data-testid="assistant-tools" open={toolsOpen} onToggle={(event) => setToolsOpen(event.currentTarget.open)}>
            <summary className="assistant-tools-toggle">
              <span>
                Tool activity <span className="assistant-tools-count">{state.tools.length}</span>
              </span>
              <span
                className="status-badge"
                data-tone={toolErrors > 0 ? "danger" : toolRunning > 0 ? "info" : "success"}
              >
                {toolErrors > 0
                  ? `${toolErrors} failed`
                  : toolRunning > 0
                    ? `${toolRunning} running`
                    : `${toolComplete} complete`}
              </span>
            </summary>
            <ul>
              {state.tools.map((tool) => (
                <li key={tool.id} data-status={tool.status}>
                  <details>
                    <summary>
                      <code>{tool.name}</code>
                      <span className="status-badge" data-tone={statusTone(tool.status)}>
                        {tool.status}
                      </span>
                    </summary>
                    <p className="assistant-meta">
                      Call {tool.id}
                      {tool.errorCode ? ` · ${tool.errorCode}` : ""}
                    </p>
                  </details>
                </li>
              ))}
            </ul>
          </details>
        ) : null}

        <div className="assistant-transcript" data-testid="assistant-transcript">
          {state.messages.length === 0 ? (
            <p className="assistant-empty">
              Ask about this architecture. For example: “Explain this Candidate architecture and trace
              how Customer information reaches Billing.”
            </p>
          ) : null}
          {state.messages.map((message) => (
            <article
              key={message.id}
              className="assistant-message"
              data-role={message.role}
              data-status={message.status}
            >
              <header>
                <strong>
                  {message.role === "user" ? "You" : message.role === "assistant" ? "Assistant" : "Notice"}
                </strong>
                <span className="status-badge" data-tone={statusTone(message.status)}>
                  {message.status}
                </span>
              </header>
              <p>{humanizeIds(message.content)}</p>
            </article>
          ))}
        </div>

        <ProposalPanel
          workspaceId={workspaceId}
          workspaceName={workspaceName}
          conversationId={state.activeId}
          changeSetId={state.activeProposalId}
          onApplied={onProposalApplied}
          onUndone={onProposalUndone}
          onClearHighlights={onProposalHighlightsCleared}
        />

        {settingsOpen ? (
          <AssistantSettingsPanel workspaceId={workspaceId} onClose={() => setSettingsOpen(false)} />
        ) : null}

        {activeConversation ? (
          <p className="assistant-meta">
            {activeConversation.message_count} messages · {activeConversation.tool_call_count} tool
            calls
          </p>
        ) : null}
      </div>

      <form className="assistant-composer" onSubmit={submit}>
        <label className="assistant-field-label" htmlFor="assistant-message-input">
          Message
        </label>
        <textarea
          id="assistant-message-input"
          aria-label="Message the assistant"
          placeholder="Ask about this architecture…"
          value={draft}
          maxLength={8000}
          onChange={(event) => setDraft(event.target.value)}
          disabled={!ready}
        />
        <div className="assistant-composer-actions">
          <button type="submit" className="btn btn--primary" disabled={!ready || !state.activeId || !draft.trim()}>
            {state.streaming ? "Send" : "Send"}
          </button>
          {state.streaming ? (
            <button type="button" className="btn btn--secondary" onClick={() => void cancel()}>
              Cancel
            </button>
          ) : (
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => lastUserMessage && void retry(lastUserMessage.id)}
              disabled={!lastUserMessage}
            >
              Retry
            </button>
          )}
        </div>
      </form>
    </aside>
  );
}
