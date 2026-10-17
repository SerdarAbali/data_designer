/**
 * Compact owner-only Assistant settings.
 *
 * Non-owners never see provider configuration or secrets; they see only safe
 * availability information. Credentials are entered nowhere in this UI — the
 * panel shows only configured / missing / invalid and the last verified time.
 */

import React from "react";

import {
  fetchAssistantSettings,
  updateAssistantSettings,
  updateWorkspaceEnabled,
} from "./assistantApi";
import type { AssistantSettings } from "./assistantTypes";

export interface AssistantSettingsPanelProps {
  workspaceId: string | null;
  onClose: () => void;
}

const CREDENTIAL_LABELS: Record<string, string> = {
  configured: "Configured",
  missing: "Missing",
  invalid: "Invalid",
};

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="assistant-setting-field">
      <span>{label}</span>
      {children}
    </label>
  );
}

export function AssistantSettingsPanel({ workspaceId, onClose }: AssistantSettingsPanelProps) {
  const [settings, setSettings] = React.useState<AssistantSettings | null>(null);
  const [draft, setDraft] = React.useState<Partial<AssistantSettings>>({});
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    setSettings(null);
    setError("");
    if (!workspaceId) return;
    let cancelled = false;
    void fetchAssistantSettings(workspaceId)
      .then((value) => {
        if (!cancelled) setSettings(value);
      })
      .catch((caught) => {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "Could not load settings");
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  if (!workspaceId) return null;

  async function save() {
    if (!workspaceId) return;
    setBusy(true);
    setError("");
    try {
      setSettings(await updateAssistantSettings(workspaceId, draft));
      setDraft({});
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save settings");
    } finally {
      setBusy(false);
    }
  }

  async function toggleWorkspace(next: boolean) {
    if (!workspaceId) return;
    setBusy(true);
    try {
      await updateWorkspaceEnabled(workspaceId, next);
      setSettings(await fetchAssistantSettings(workspaceId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not update the workspace");
    } finally {
      setBusy(false);
    }
  }

  const value = <K extends keyof AssistantSettings>(key: K, fallback: AssistantSettings[K]) =>
    (draft[key] ?? settings?.[key] ?? fallback) as AssistantSettings[K];

  return (
    <div className="assistant-settings" role="dialog" aria-modal="true" data-testid="assistant-settings">
      <header className="proposal-header">
        <h3>Assistant settings</h3>
        <button type="button" onClick={onClose} aria-label="Close settings">
          Close
        </button>
      </header>

      {error ? (
        <p className="assistant-error" role="alert">
          {error}
        </p>
      ) : null}
      {!settings ? <p>Loading settings…</p> : null}

      {settings && !settings.is_owner ? (
        <div data-testid="settings-readonly">
          <p>The assistant is {settings.workspace_enabled ? "enabled" : "disabled"} for this workspace.</p>
          <p>Privacy: {settings.privacy_classification ?? "internal"}</p>
          <p>Credential: {CREDENTIAL_LABELS[settings.credential_status ?? "missing"]}</p>
          <p>Only a workspace owner can change provider and privacy settings.</p>
        </div>
      ) : null}

      {settings?.is_owner ? (
        <div className="assistant-settings-body">
          <p className="proposal-meta">
            Runtime readiness: {settings.privacy_allowed ? "permitted" : settings.privacy_reason}
          </p>
          <Field label="Assistant enabled for this workspace">
            <input
              type="checkbox"
              aria-label="Assistant enabled for this workspace"
              checked={settings.workspace_enabled}
              disabled={busy}
              onChange={(event) => void toggleWorkspace(event.target.checked)}
            />
          </Field>
          <Field label="Provider">
            <input
              aria-label="Provider"
              value={String(value("provider", ""))}
              onChange={(event) => setDraft((current) => ({ ...current, provider: event.target.value }))}
            />
          </Field>
          <Field label="Model">
            <input
              aria-label="Model"
              value={String(value("model_id", ""))}
              onChange={(event) => setDraft((current) => ({ ...current, model_id: event.target.value }))}
            />
          </Field>
          <Field label="Reasoning effort">
            <select
              aria-label="Reasoning effort"
              value={String(value("reasoning_effort", "medium"))}
              onChange={(event) =>
                setDraft((current) => ({ ...current, reasoning_effort: event.target.value }))
              }
            >
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
            </select>
          </Field>
          <Field label="Max input tokens">
            <input
              aria-label="Max input tokens"
              type="number"
              value={Number(value("max_input_tokens", 16000))}
              onChange={(event) =>
                setDraft((current) => ({ ...current, max_input_tokens: Number(event.target.value) }))
              }
            />
          </Field>
          <Field label="Max output tokens">
            <input
              aria-label="Max output tokens"
              type="number"
              value={Number(value("max_output_tokens", 4000))}
              onChange={(event) =>
                setDraft((current) => ({ ...current, max_output_tokens: Number(event.target.value) }))
              }
            />
          </Field>
          <Field label="Timeout (seconds)">
            <input
              aria-label="Timeout (seconds)"
              type="number"
              value={Number(value("timeout_seconds", 180))}
              onChange={(event) =>
                setDraft((current) => ({ ...current, timeout_seconds: Number(event.target.value) }))
              }
            />
          </Field>
          <Field label="Tool-call step limit">
            <input
              aria-label="Tool-call step limit"
              type="number"
              value={Number(value("step_limit", 12))}
              onChange={(event) =>
                setDraft((current) => ({ ...current, step_limit: Number(event.target.value) }))
              }
            />
          </Field>
          <Field label="Conversation retention (days)">
            <input
              aria-label="Conversation retention (days)"
              type="number"
              min={1}
              max={90}
              value={Number(value("retention_days", 30))}
              onChange={(event) =>
                setDraft((current) => ({ ...current, retention_days: Number(event.target.value) }))
              }
            />
          </Field>
          <Field label="Privacy classification">
            <select
              aria-label="Privacy classification"
              value={String(value("privacy_classification", "internal"))}
              onChange={(event) =>
                setDraft((current) => ({ ...current, privacy_classification: event.target.value }))
              }
            >
              <option value="public">public</option>
              <option value="internal">internal</option>
              <option value="confidential">confidential</option>
              <option value="restricted">restricted</option>
            </select>
          </Field>
          <Field label="Request data may be used for training">
            <input
              type="checkbox"
              aria-label="Request data may be used for training"
              checked={Boolean(value("trains_on_data", false))}
              onChange={(event) =>
                setDraft((current) => ({ ...current, trains_on_data: event.target.checked }))
              }
            />
          </Field>
          <Field label="Approved for sensitive architecture data">
            <input
              type="checkbox"
              aria-label="Approved for sensitive architecture data"
              checked={Boolean(value("approved_for_sensitive", false))}
              onChange={(event) =>
                setDraft((current) => ({ ...current, approved_for_sensitive: event.target.checked }))
              }
            />
          </Field>
          <Field label="Fallback enabled">
            <input
              type="checkbox"
              aria-label="Fallback enabled"
              checked={Boolean(value("fallback_enabled", false))}
              onChange={(event) =>
                setDraft((current) => ({ ...current, fallback_enabled: event.target.checked }))
              }
            />
          </Field>
          <Field label="Fallback provider">
            <input
              aria-label="Fallback provider"
              value={String(value("fallback_provider", ""))}
              onChange={(event) =>
                setDraft((current) => ({ ...current, fallback_provider: event.target.value }))
              }
            />
          </Field>
          <Field label="Fallback model">
            <input
              aria-label="Fallback model"
              value={String(value("fallback_model_id", ""))}
              onChange={(event) =>
                setDraft((current) => ({ ...current, fallback_model_id: event.target.value }))
              }
            />
          </Field>

          <p className="proposal-meta" data-testid="credential-status">
            Credential: {CREDENTIAL_LABELS[settings.credential_status ?? "missing"]}
            {settings.credential_last_verified_at
              ? ` · last verified ${settings.credential_last_verified_at}`
              : ""}
          </p>

          <div className="proposal-dialog-actions">
            <button type="button" onClick={() => void save()} disabled={busy} data-testid="save-settings">
              Save settings
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
