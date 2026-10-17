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

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || !ready) return;
    setDraft("");
    void send(content);
  }

  return (
    <aside
      className="assistant-panel"
      data-testid="assistant-panel"
      hidden={!open}
      aria-label="Architecture Assistant"
      role="dialog"
      aria-modal="false"
    >
      <header className="assistant-header">
        <h2>Architecture Assistant</h2>
        <div className="assistant-header-actions">
          <button type="button" onClick={() => void newConversation()} disabled={!ready}>
            New
          </button>
          <button
            type="button"
            onClick={() => state.activeId && void removeConversation(state.activeId)}
            disabled={!state.activeId}
          >
            Delete
          </button>
          {state.status?.is_owner ? (
            <button type="button" data-testid="open-settings" onClick={() => setSettingsOpen(true)}>
              Settings
            </button>
          ) : null}
          <button type="button" aria-label="Close assistant" onClick={onClose}>
            Close
          </button>
        </div>
      </header>

      <p className="assistant-readonly" role="note">
        {READ_ONLY_NOTICE}
      </p>
      {isCurrent ? (
        <p className="assistant-readonly assistant-current-notice" role="note">
          {CURRENT_READ_ONLY_NOTICE}
        </p>
      ) : null}

      <div className="assistant-status" data-ready={ready} role="status">
        {statusMessage(state.status)}
        {state.status?.observed_opencode_version ? (
          <span className="assistant-version"> · OpenCode {state.status.observed_opencode_version}</span>
        ) : null}
      </div>

      {state.error ? (
        <p className="assistant-error" role="alert">
          {state.error}
        </p>
      ) : null}

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

      <div className="assistant-conversations">
        <label>
          Conversation
          <select
            aria-label="Conversation"
            value={state.activeId ?? ""}
            onChange={(event) => selectConversation(event.target.value)}
          >
            {state.conversations.map((conversation) => (
              <option key={conversation.id} value={conversation.id}>
                {conversation.title}
              </option>
            ))}
          </select>
        </label>
      </div>

      {state.tools.length > 0 ? (
        <div className="assistant-tools" data-testid="assistant-tools">
          <button
            type="button"
            className="assistant-tools-toggle"
            aria-expanded={toolsOpen}
            onClick={() => setToolsOpen((open) => !open)}
          >
            {toolsOpen ? "▾" : "▸"}
            Tool activity <span className="assistant-tools-count">{state.tools.length}</span>
          </button>
          {toolsOpen && (
            <ul>
              {state.tools.map((tool) => (
                <li key={tool.id} data-status={tool.status}>
                  <code>{tool.name}</code>
                  <span>{tool.status}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}

      <div className="assistant-transcript" data-testid="assistant-transcript">
        {state.messages.length === 0 ? (
          <p className="assistant-empty">
            Ask about this architecture. For example: “Explain this Candidate architecture and trace
            how Customer information reaches Billing.”
          </p>
        ) : null}
        {state.messages.map((message) => (
          <article key={message.id} className="assistant-message" data-role={message.role}>
            <header>
              <strong>{message.role}</strong>
              <span>{message.status}</span>
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

      <form className="assistant-composer" onSubmit={submit}>
        <textarea
          aria-label="Message the assistant"
          placeholder="Ask about this architecture…"
          value={draft}
          maxLength={8000}
          onChange={(event) => setDraft(event.target.value)}
          disabled={!ready}
        />
        <div className="assistant-composer-actions">
          <button type="submit" disabled={!ready || !state.activeId || !draft.trim()}>
            Send
          </button>
          {state.streaming ? (
            <button type="button" onClick={() => void cancel()}>
              Cancel
            </button>
          ) : (
            <button
              type="button"
              onClick={() => lastUserMessage && void retry(lastUserMessage.id)}
              disabled={!lastUserMessage}
            >
              Retry
            </button>
          )}
        </div>
      </form>
      {activeConversation ? (
        <p className="assistant-meta">
          {activeConversation.message_count} messages · {activeConversation.tool_call_count} tool
          calls
        </p>
      ) : null}
    </aside>
  );
}
