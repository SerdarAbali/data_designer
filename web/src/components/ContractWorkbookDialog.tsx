import React from "react";
import { api } from "../apiClient";
import {
  CLASSIFICATION_LABELS,
  CLASSIFICATION_ORDER,
  CLASSIFICATION_TONES,
  WORKBOOK_PHASE_LABELS,
  applyBlockedReason,
  changeSummary,
  groupRows,
  issueLabels,
  revisionSummary,
  rowLabel,
  type WorkbookApplyResult,
  type WorkbookPreview,
  type WorkbookRowPreview,
} from "../contractWorkbook";

type Props = {
  kind: "import" | "export";
  workspaceId: string;
  integrationId: string;
  contractName: string;
  revision: number;
  onApplied: (result: WorkbookApplyResult) => void;
  onClose: () => void;
};

function workbookPath(workspaceId: string, integrationId: string, suffix = ""): string {
  return (
    `/api/workspaces/${workspaceId}/integration-design/contracts/` +
    `${integrationId}/workbook${suffix}`
  );
}

function base64Payload(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("The workbook could not be read."));
    reader.onload = () => {
      const result = String(reader.result ?? "");
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.readAsDataURL(file);
  });
}

function RowList({ id, rows }: { id: string; rows: WorkbookRowPreview[] }) {
  if (rows.length === 0) return null;
  return (
    <ul className="workbook-rows" data-testid={id}>
      {rows.map((row) => (
        <li key={`${row.phase}-${row.row}`} data-classification={row.classification}>
          <code>
            {WORKBOOK_PHASE_LABELS[row.phase] ?? row.phase} row {row.row}
          </code>
          <span>{rowLabel(row)}</span>
          {row.classification === "invalid" || row.classification === "unresolved" ? (
            <em className="workbook-issue">{issueLabels(row)}</em>
          ) : null}
          {row.editable === false ? <em className="workbook-issue">Read only in the workbook</em> : null}
        </li>
      ))}
    </ul>
  );
}

export default function ContractWorkbookDialog(props: Props) {
  const { kind, workspaceId, integrationId, contractName, revision } = props;
  const dialogRef = React.useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [preview, setPreview] = React.useState<WorkbookPreview | null>(null);
  const [filename, setFilename] = React.useState("");
  const [contents, setContents] = React.useState("");
  const [confirmed, setConfirmed] = React.useState(false);
  const [result, setResult] = React.useState<WorkbookApplyResult | null>(null);

  React.useEffect(() => {
    const previous = document.activeElement;
    dialogRef.current?.showModal();
    return () => {
      dialogRef.current?.close();
      if (previous instanceof HTMLElement) previous.focus();
    };
  }, []);

  async function downloadWorkbook() {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(workbookPath(workspaceId, integrationId), {
        headers: { Accept: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
      });
      if (!response.ok) throw new Error("The workbook could not be exported.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${contractName.replace(/[^a-z0-9]/gi, "_")}-contract-r${revision}.xlsx`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The workbook could not be exported.");
    } finally {
      setBusy(false);
    }
  }

  async function review(file: File) {
    setBusy(true);
    setError("");
    setConfirmed(false);
    setResult(null);
    try {
      const content_base64 = await base64Payload(file);
      const reviewed = await api<WorkbookPreview>(
        workbookPath(workspaceId, integrationId, "/preview"),
        { method: "POST", body: JSON.stringify({ filename: file.name, content_base64 }) },
      );
      setFilename(file.name);
      setContents(content_base64);
      setPreview(reviewed);
    } catch (caught) {
      setPreview(null);
      setError(caught instanceof Error ? caught.message : "The workbook could not be reviewed.");
    } finally {
      setBusy(false);
    }
  }

  async function apply() {
    if (!preview || !preview.applyable || !confirmed) return;
    setBusy(true);
    setError("");
    try {
      const applied = await api<WorkbookApplyResult>(
        workbookPath(workspaceId, integrationId, "/apply"),
        {
          method: "POST",
          body: JSON.stringify({
            filename,
            content_base64: contents,
            expected_revision: preview.contract_revision,
            preview_hash: preview.preview_hash,
          }),
        },
      );
      setResult(applied);
      props.onApplied(applied);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The changes could not be applied.");
    } finally {
      setBusy(false);
    }
  }

  const grouped = preview ? groupRows(preview) : null;
  const blocked = preview ? applyBlockedReason(preview) : null;

  return (
    <dialog ref={dialogRef} className="contract-dialog workbook-dialog" aria-label="Mapping workbook">
      <header className="contract-dialog-head">
        <div>
          <p className="eyebrow">{kind === "export" ? "Export" : "Import"} mapping workbook</p>
          <h2>{contractName}</h2>
          <span className="contract-dialog-scope">Contract revision {revision}</span>
        </div>
        <button type="button" className="secondary-button" onClick={props.onClose}>
          Close
        </button>
      </header>

      {kind === "export" ? (
        <section className="contract-dialog-body">
          <p>
            The workbook contains an Instructions sheet, the Contract sheet, one sheet per mapping
            phase (request, success response, error response) and a read-only Transformations sheet.
            It carries the contract revision so a stale workbook can never be applied.
          </p>
          <p className="workbook-hint">
            Uploading it again produces a preview only. Nothing is written until you review the
            preview and confirm the apply.
          </p>
          <div className="contract-dialog-actions">
            <button
              type="button"
              className="btn btn--primary"
              data-testid="workbook-download"
              disabled={busy}
              onClick={() => void downloadWorkbook()}
            >
              {busy ? "Preparing…" : "Download workbook"}
            </button>
          </div>
        </section>
      ) : (
        <section className="contract-dialog-body">
          <label className="workbook-file-field">
            <span>Choose a mapping workbook (.xlsx)</span>
            <input
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              aria-label="Choose mapping workbook"
              data-testid="workbook-file"
              disabled={busy}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void review(file);
              }}
            />
          </label>

          {error ? (
            <p className="workbook-error" role="alert" data-testid="workbook-error">
              {error}
            </p>
          ) : null}

          {preview && grouped ? (
            <div className="workbook-preview" data-testid="workbook-preview">
              <p data-testid="workbook-revisions">{revisionSummary(preview)}</p>
              {preview.stale ? (
                <p className="workbook-stale" data-testid="workbook-stale" role="alert">
                  {preview.stale_reason ?? "This workbook is stale."} Export it again before applying.
                </p>
              ) : null}

              <ul className="workbook-counts" data-testid="workbook-counts">
                {CLASSIFICATION_ORDER.map((classification) => (
                  <li
                    key={classification}
                    data-tone={CLASSIFICATION_TONES[classification]}
                    data-classification={classification}
                  >
                    <strong>{preview.counts[classification] ?? 0}</strong>{" "}
                    {CLASSIFICATION_LABELS[classification]}
                  </li>
                ))}
                <li data-tone="muted">
                  <strong>{preview.counts.rejected ?? 0}</strong> Rejected
                </li>
              </ul>

              {preview.contract_changes.length > 0 ? (
                <div>
                  <h3>Contract metadata</h3>
                  <ul className="workbook-changes" data-testid="workbook-contract-changes">
                    {preview.contract_changes.map((change) => (
                      <li key={change.field}>
                        <strong>{change.label}</strong> <span>{changeSummary(change)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {preview.blocking_reasons.length > 0 ? (
                <div>
                  <h3>Cannot be applied</h3>
                  <ul className="workbook-blocking" data-testid="workbook-blocking">
                    {preview.blocking_reasons.map((issue, index) => (
                      <li key={`${issue.code}-${issue.row}-${index}`}>
                        <code>{issue.code}</code> {issue.message}
                        {issue.row ? ` (row ${issue.row})` : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {(
                [
                  ["add", "workbook-rows-added"],
                  ["update", "workbook-rows-updated"],
                  ["remove", "workbook-rows-removed"],
                  ["unchanged", "workbook-rows-unchanged"],
                  ["invalid", "workbook-rows-invalid"],
                  ["unresolved", "workbook-rows-unresolved"],
                ] as const
              ).map(([classification, testId]) => (
                <RowList key={classification} id={testId} rows={grouped[classification] ?? []} />
              ))}

              {result ? (
                <p className="workbook-result" data-testid="workbook-result" role="status">
                  {result.applied
                    ? `Applied. Revision ${result.revision}: ${result.counts.add} added, ` +
                      `${result.counts.update} updated, ${result.counts.remove} removed, ` +
                      `${result.counts.unchanged} unchanged, ${result.counts.rejected} rejected.`
                    : "No changes to apply; the contract was left untouched."}
                </p>
              ) : null}

              <div className="contract-dialog-actions">
                <label className="workbook-confirm">
                  <input
                    type="checkbox"
                    data-testid="workbook-confirm"
                    checked={confirmed}
                    disabled={!preview.applyable}
                    onChange={(event) => setConfirmed(event.target.checked)}
                  />
                  <span>
                    I have reviewed this preview and want to apply it to contract revision{" "}
                    {preview.contract_revision}.
                  </span>
                </label>
                <button
                  type="button"
                  className="btn btn--primary"
                  data-testid="workbook-apply"
                  disabled={!preview.applyable || !confirmed || busy || Boolean(result)}
                  title={blocked ?? undefined}
                  onClick={() => void apply()}
                >
                  {busy ? "Applying…" : "Apply reviewed changes"}
                </button>
                {!preview.applyable && blocked ? (
                  <p className="workbook-hint" data-testid="workbook-blocked-reason">
                    {blocked}
                  </p>
                ) : null}
                {preview.applyable && !preview.has_changes ? (
                  <p className="workbook-hint" data-testid="workbook-no-changes">
                    Nothing in this workbook changes the contract.
                  </p>
                ) : null}
              </div>
            </div>
          ) : null}
        </section>
      )}
    </dialog>
  );
}
