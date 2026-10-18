import React from "react";
import { api } from "../apiClient";
import type { ArchitectureState } from "../architectureTypes";
import {
  baselineBlockingReason,
  baselineCanLock,
  baselineNeedsEmptyConfirmation,
  baselineSummary,
  issueLabel,
  type BaselineLockResponse,
  type BaselineValidation,
} from "./currentBaseline";

type Props = {
  workspaceId: string;
  state: ArchitectureState;
  onLocked: (state: ArchitectureState) => void;
  onClose: () => void;
};

/**
 * Review and lock the Current baseline.
 *
 * The dialog reads the bounded validation first (no write) and only then offers
 * the lock. Blocking errors disable it; an empty capture additionally requires an
 * explicit confirmation. There is no unlock control because this slice has none.
 */
export default function LockBaselineDialog({ workspaceId, state, onLocked, onClose }: Props) {
  const dialogRef = React.useRef<HTMLDialogElement>(null);
  const [validation, setValidation] = React.useState<BaselineValidation | null>(null);
  const [confirmed, setConfirmed] = React.useState(false);
  const [confirmedEmpty, setConfirmedEmpty] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const endpoint = `/api/workspaces/${workspaceId}/states/${state.id}/lock-baseline`;

  React.useEffect(() => {
    const previous = document.activeElement;
    dialogRef.current?.showModal();
    return () => {
      dialogRef.current?.close();
      if (previous instanceof HTMLElement) previous.focus();
    };
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const response = await api<BaselineLockResponse>(endpoint, {
          method: "POST",
          body: JSON.stringify({ validate_only: true }),
        });
        if (!cancelled) setValidation(response.validation);
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "The baseline could not be checked.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [endpoint]);

  async function lock() {
    setBusy(true);
    setError("");
    try {
      const response = await api<BaselineLockResponse>(endpoint, {
        method: "POST",
        body: JSON.stringify({ confirm_empty: confirmedEmpty }),
      });
      onLocked(response.state);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The baseline could not be locked.");
    } finally {
      setBusy(false);
    }
  }

  const blocking = validation?.blocking ?? [];
  const warnings = validation?.warnings ?? [];
  const blocked = baselineBlockingReason(validation);
  const needsEmpty = baselineNeedsEmptyConfirmation(validation);
  const ready = baselineCanLock(validation) && confirmed && (!needsEmpty || confirmedEmpty);

  return (
    <dialog ref={dialogRef} className="contract-dialog lock-baseline-dialog" aria-label="Lock Current baseline">
      <header className="contract-dialog-head">
        <div>
          <p className="eyebrow">Current baseline</p>
          <h2>Lock the Current baseline</h2>
          <span className="contract-dialog-scope">{state.name}</span>
        </div>
        <button type="button" className="secondary-button" onClick={onClose}>
          Close
        </button>
      </header>

      <section className="contract-dialog-body">
        {error ? (
          <p className="workbook-error" role="alert" data-testid="baseline-error">
            {error}
          </p>
        ) : null}

        {validation ? (
          <div data-testid="baseline-validation">
            <h3>Baseline summary</h3>
            <ul className="baseline-summary" data-testid="baseline-summary">
              {baselineSummary(validation).map((entry) => (
                <li key={entry.label}>
                  <strong>{entry.value}</strong> {entry.label}
                </li>
              ))}
            </ul>

            {blocking.length > 0 ? (
              <div>
                <h3>Blocking errors</h3>
                <ul className="baseline-blocking" data-testid="baseline-blocking">
                  {blocking.map((issue) => (
                    <li key={issue.code}>{issueLabel(issue)}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {warnings.length > 0 ? (
              <div>
                <h3>Warnings</h3>
                <ul className="baseline-warnings" data-testid="baseline-warnings">
                  {warnings.map((issue) => (
                    <li key={issue.code}>{issueLabel(issue)}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {needsEmpty ? (
              <label className="workbook-confirm">
                <input
                  type="checkbox"
                  data-testid="baseline-confirm-empty"
                  checked={confirmedEmpty}
                  disabled={!baselineCanLock(validation)}
                  onChange={(event) => setConfirmedEmpty(event.target.checked)}
                />
                <span>I understand and want to lock an empty Current baseline.</span>
              </label>
            ) : null}

            <label className="workbook-confirm">
              <input
                type="checkbox"
                data-testid="baseline-confirm"
                checked={confirmed}
                disabled={!baselineCanLock(validation)}
                onChange={(event) => setConfirmed(event.target.checked)}
              />
              <span>
                Lock this baseline. Current becomes read-only and cannot be unlocked in this
                version.
              </span>
            </label>
          </div>
        ) : (
          <p className="workbook-hint">Checking the baseline…</p>
        )}

        {blocked ? (
          <p className="workbook-hint" data-testid="baseline-blocked-reason">
            {blocked}
          </p>
        ) : null}

        <div className="contract-dialog-actions">
          <button
            type="button"
            className="btn btn--primary"
            data-testid="baseline-lock"
            disabled={!ready || busy}
            title={blocked ?? undefined}
            onClick={() => void lock()}
          >
            {busy ? "Locking…" : "Lock Current baseline"}
          </button>
          <p className="workbook-hint">
            Locking is irreversible in this version. Candidate and Target states stay editable.
          </p>
        </div>
      </section>
    </dialog>
  );
}
