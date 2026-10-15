import React from "react";
import {
  IMPORT_KIND_FIELDS,
  IMPORT_KINDS,
  ImportFileError,
  buildTemplateCsv,
  downloadIssues,
  parseImportFile,
  suggestColumnMapping,
  type ImportIssue,
  type ImportKind,
  type ParsedWorkbook,
  type RowDecision,
} from "../../architectureImport";
import {
  ImportApiError,
  commitImport,
  includeImportedObjects,
  listArchitectureStates,
  listImportBatches,
  previewImport,
  undoImportBatch,
  type ImportBatch,
  type ImportPreviewResponse,
  type ImportRowPreview,
} from "../../architectureImportApi";
import { downloadCsv } from "../../contractMappingCsv";

type Props = {
  workspaceId: string;
  currentStateId?: string | null;
  onClose: () => void;
  onCommitted: (message: string) => void;
  onOpenCanvas: () => void;
};

type DecisionState = { decision: RowDecision; targetId: string | null };

type IncludeSelection = {
  systems: Set<string>;
  objects: Set<string>;
  integrations: Set<string>;
  visualizeMembership: boolean;
};

const DECISION_LABELS: Record<RowDecision, string> = {
  create: "Create new",
  update: "Update existing",
  use_existing: "Use existing",
  skip: "Skip",
};

const STATUS_ORDER = ["created", "updated", "matched", "skipped", "blocked", "failed"];

const EMPTY_SELECTION: IncludeSelection = {
  systems: new Set(),
  objects: new Set(),
  integrations: new Set(),
  visualizeMembership: true,
};

function issueList(issues: ImportIssue[]): string {
  return issues.map((issue) => `${issue.row ? `Row ${issue.row}: ` : ""}${issue.message}`).join(" ");
}

function matchLabel(row: ImportRowPreview): string {
  const match = row.matches[0];
  if (!match) return "No match";
  const labels: Record<string, string> = {
    external_id: "matched by external ID",
    exact_name: "matched by name",
    alias: "matched by alias",
    similar_name: "similar name — confirm",
  };
  return `${match.name} (${labels[match.method] ?? match.method})`;
}

export default function ArchitectureImportDialog(props: Props) {
  const dialogRef = React.useRef<HTMLDialogElement>(null);
  const [step, setStep] = React.useState<"upload" | "preview" | "results">("upload");
  const [workbook, setWorkbook] = React.useState<ParsedWorkbook | null>(null);
  const [sheetName, setSheetName] = React.useState("");
  const [importKind, setImportKind] = React.useState<ImportKind>("system");
  const [mapping, setMapping] = React.useState<Record<string, string>>({});
  const [decisions, setDecisions] = React.useState<Record<number, DecisionState>>({});
  const [preview, setPreview] = React.useState<ImportPreviewResponse | null>(null);
  const [batch, setBatch] = React.useState<ImportBatch | null>(null);
  const [batches, setBatches] = React.useState<ImportBatch[]>([]);
  const [selection, setSelection] = React.useState<IncludeSelection>(EMPTY_SELECTION);
  const [confirmed, setConfirmed] = React.useState(false);
  const [fileIssues, setFileIssues] = React.useState<ImportIssue[]>([]);
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [currentStateId, setCurrentStateId] = React.useState<string | null>(
    props.currentStateId ?? null,
  );

  const fields = IMPORT_KIND_FIELDS[importKind];
  const sheet = workbook?.sheets.find((item) => item.name === sheetName) ?? workbook?.sheets[0] ?? null;

  React.useEffect(() => {
    if (props.currentStateId !== undefined) {
      setCurrentStateId(props.currentStateId);
      return;
    }
    let active = true;
    void (async () => {
      try {
        const states = await listArchitectureStates(props.workspaceId);
        if (!active) return;
        setCurrentStateId(states.find((state) => state.state_type === "current")?.id ?? null);
      } catch {
        if (active) setCurrentStateId(null);
      }
    })();
    return () => {
      active = false;
    };
  }, [props.currentStateId, props.workspaceId]);

  React.useEffect(() => {
    const previousFocus = document.activeElement;
    dialogRef.current?.showModal();
    return () => {
      dialogRef.current?.close();
      if (previousFocus instanceof HTMLElement) previousFocus.focus();
    };
  }, []);

  const refreshBatches = React.useCallback(async () => {
    try {
      setBatches(await listImportBatches(props.workspaceId));
    } catch {
      setBatches([]);
    }
  }, [props.workspaceId]);

  React.useEffect(() => {
    void refreshBatches();
  }, [refreshBatches]);

  function remap(headers: string[], kind: ImportKind) {
    setMapping(suggestColumnMapping(headers, IMPORT_KIND_FIELDS[kind]));
  }

  async function handleFile(file: File | null) {
    if (!file) return;
    setError("");
    setFileIssues([]);
    setPreview(null);
    setBatch(null);
    setConfirmed(false);
    try {
      const parsed = await parseImportFile(file);
      setWorkbook(parsed);
      const first = parsed.sheets[0];
      setSheetName(first?.name ?? "");
      remap(first?.table.headers ?? [], importKind);
    } catch (caught) {
      if (caught instanceof ImportFileError) {
        setFileIssues(caught.issues);
        setWorkbook(null);
      } else {
        setError(caught instanceof Error ? caught.message : "The file could not be read.");
      }
    }
  }

  function missingRequired(): string[] {
    return fields.filter((field) => field.required && !mapping[field.key]).map((field) => field.label);
  }

  async function runPreview() {
    if (!sheet) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await previewImport(props.workspaceId, {
        import_type: importKind,
        headers: sheet.table.headers,
        rows: sheet.table.rows,
        column_mapping: mapping,
        source_filename: workbook?.filename ?? "import",
        sheet_name: sheet.name,
      });
      const next: Record<number, DecisionState> = {};
      for (const row of result.rows) {
        next[row.row_number] = {
          decision: row.suggested_decision,
          targetId: row.matches[0]?.id ?? null,
        };
      }
      setDecisions(next);
      setPreview(result);
      setConfirmed(false);
      setStep("preview");
    } catch (caught) {
      setError(caught instanceof ImportApiError ? caught.message : "The preview could not be built.");
    } finally {
      setBusy(false);
    }
  }

  const changedCount = preview
    ? preview.rows.filter((row) => decisions[row.row_number]?.decision !== "skip").length
    : 0;
  const blockedCount = preview ? preview.rows.filter((row) => row.issues.length > 0).length : 0;
  const canCommit =
    Boolean(preview) && confirmed && !busy && changedCount > 0;

  async function runCommit() {
    if (!preview || !sheet || !canCommit) return;
    setBusy(true);
    setError("");
    try {
      const result = await commitImport(props.workspaceId, {
        import_type: importKind,
        headers: sheet.table.headers,
        rows: sheet.table.rows,
        column_mapping: mapping,
        source_filename: workbook?.filename ?? "import",
        sheet_name: sheet.name,
        decisions: preview.rows.map((row) => ({
          row_number: row.row_number,
          decision: decisions[row.row_number]?.decision ?? row.suggested_decision,
          target_id: decisions[row.row_number]?.targetId ?? row.matches[0]?.id ?? null,
        })),
      });
      setBatch(result);
      setStep("results");
      const counts = STATUS_ORDER.filter((key) => result.counts[key])
        .map((key) => `${result.counts[key]} ${key}`)
        .join(", ");
      props.onCommitted(
        `Import finished: ${counts || "no rows applied"} from ${result.source_filename}.`,
      );
      setSelection(EMPTY_SELECTION);
      await refreshBatches();
    } catch (caught) {
      setError(caught instanceof ImportApiError ? caught.message : "The import could not be committed.");
    } finally {
      setBusy(false);
    }
  }
  const createdTargets = React.useMemo(() => {
    if (!batch) return [];
    return batch.rows
      .filter(
        (row) =>
          Boolean(row.target_id) &&
          (row.status === "created" || row.status === "matched" || row.status === "updated"),
      )
      .map((row) => ({
        rowNumber: row.row_number,
        kind: row.target_kind ?? "system",
        id: row.target_id as string,
        name:
          preview?.rows.find((item) => item.row_number === row.row_number)?.name ?? "(unnamed)",
      }));
  }, [batch, preview]);

  function toggleSelection(kind: string, id: string) {
    setSelection((current) => {
      const next: IncludeSelection = {
        systems: new Set(current.systems),
        objects: new Set(current.objects),
        integrations: new Set(current.integrations),
        visualizeMembership: current.visualizeMembership,
      };
      const bucket =
        kind === "system" ? next.systems : kind === "integration" ? next.integrations : next.objects;
      if (bucket.has(id)) bucket.delete(id);
      else bucket.add(id);
      return next;
    });
  }

  async function applyToCurrent() {
    if (!currentStateId || !batch) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await includeImportedObjects(props.workspaceId, currentStateId, {
        system_ids: [...selection.systems],
        architecture_object_ids: [...selection.objects],
        integration_ids: [...selection.integrations],
        visualize_solution_membership: selection.visualizeMembership,
      });
      setNotice(
        `Current architecture updated: ${result.added_occurrences} object(s) and `
          + `${result.added_relationships} relationship(s) added`
          + (result.skipped.length ? `; ${result.skipped.length} skipped.` : "."),
      );
    } catch (caught) {
      setError(
        caught instanceof ImportApiError ? caught.message : "The Current architecture could not be updated.",
      );
    } finally {
      setBusy(false);
    }
  }

  function downloadErrors(target: ImportBatch) {
    const issues: ImportIssue[] = target.rows.flatMap((row) => {
      if (row.issues.length) return row.issues;
      if (["blocked", "failed", "conflict"].includes(row.status) && row.message) {
        return [{ row: row.row_number, column: "", message: row.message }];
      }
      return [];
    });
    if (!issues.length) {
      setNotice("This batch has no row-level errors to download.");
      return;
    }
    downloadIssues(issues, `${target.source_filename || "import"}-row-errors.csv`);
  }

  async function runUndo(target: ImportBatch) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const updated = await undoImportBatch(props.workspaceId, target.id);
      setBatch((current) => (current && current.id === updated.id ? updated : current));
      await refreshBatches();
      setNotice(
        updated.status === "undone"
          ? "Import batch undone. Only that batch's changes were reversed."
          : "Some rows could not be undone; review the row messages.",
      );
    } catch (caught) {
      setError(caught instanceof ImportApiError ? caught.message : "The import could not be undone.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <dialog
      ref={dialogRef}
      className="contract-csv-dialog import-dialog"
      aria-label="Import architecture from Excel or CSV"
    >
      <header className="csv-dialog-header">
        <div>
          <p className="eyebrow">IMPORT FROM CATALOG</p>
          <h2>Import existing architecture</h2>
          <p>
            Upload an Excel or CSV file, map its columns, review every proposed change, then commit
            or undo the whole batch.
          </p>
        </div>
        <button type="button" className="quiet-button" onClick={props.onClose} aria-label="Close import">
          ✕
        </button>
      </header>

      <ol className="import-steps" aria-label="Import steps">
        <li className={step === "upload" ? "active" : "done"}>1 · File, sheet &amp; mapping</li>
        <li className={step === "preview" ? "active" : step === "results" ? "done" : ""}>
          2 · Review changes
        </li>
        <li className={step === "results" ? "active" : ""}>3 · Results, undo &amp; Current view</li>
      </ol>

      {error && (
        <p role="alert" className="csv-error">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}

      {step === "upload" && (
        <section className="csv-upload">
          <label>
            Excel or CSV file
            <input
              type="file"
              accept=".csv,.txt,.xlsx"
              aria-label="Import file"
              onChange={(event) => void handleFile(event.target.files?.[0] ?? null)}
            />
          </label>
          {fileIssues.length > 0 && (
            <ul className="csv-error" role="alert">
              {fileIssues.slice(0, 10).map((issue, index) => (
                <li key={index}>
                  {issue.row ? `Row ${issue.row}: ` : ""}
                  {issue.message}
                </li>
              ))}
            </ul>
          )}
          {workbook && (
            <>
              <div className="import-selects">
                <label>
                  Sheet
                  <select
                    aria-label="Sheet"
                    value={sheet?.name ?? ""}
                    onChange={(event) => {
                      setSheetName(event.target.value);
                      const next = workbook.sheets.find((item) => item.name === event.target.value);
                      remap(next?.table.headers ?? [], importKind);
                    }}
                  >
                    {workbook.sheets.map((item) => (
                      <option key={item.name} value={item.name}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Import type
                  <select
                    aria-label="Import type"
                    value={importKind}
                    onChange={(event) => {
                      const next = event.target.value as ImportKind;
                      setImportKind(next);
                      remap(sheet?.table.headers ?? [], next);
                    }}
                  >
                    {IMPORT_KINDS.map((kind) => (
                      <option key={kind.id} value={kind.id}>
                        {kind.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <p className="muted">
                {IMPORT_KINDS.find((kind) => kind.id === importKind)?.description}
              </p>
              <div className="csv-column-grid">
                {fields.map((field) => (
                  <label key={field.key}>
                    {field.label}
                    {field.required ? " *" : ""}
                    <select
                      aria-label={`Column for ${field.label}`}
                      value={mapping[field.key] ?? ""}
                      onChange={(event) =>
                        setMapping((current) => ({ ...current, [field.key]: event.target.value }))
                      }
                    >
                      <option value="">Not mapped</option>
                      {(sheet?.table.headers ?? []).map((header) => (
                        <option key={header} value={header}>
                          {header}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
              {missingRequired().length > 0 && (
                <p className="csv-error">
                  Map these required columns to continue: {missingRequired().join(", ")}.
                </p>
              )}
              <p className="muted">
                {sheet?.table.rows.length ?? 0} data row(s) detected. Lists such as aliases and included
                systems use semicolons.
              </p>
            </>
          )}
        </section>
      )}

      {step === "preview" && preview && (
        <section className="csv-preview-table">
          <p>
            {preview.rows.length} row(s) parsed · {blockedCount} blocked · {changedCount} to apply.
            Nothing is written until you commit.
          </p>
          <table>
            <thead>
              <tr>
                <th>Row</th>
                <th>Name</th>
                <th>Match</th>
                <th>Decision</th>
                <th>Target</th>
                <th>Issues</th>
              </tr>
            </thead>
            <tbody>
              {preview.rows.map((row) => {
                const state = decisions[row.row_number];
                return (
                  <tr key={row.row_number}>
                    <td>{row.row_number}</td>
                    <td>{row.name ?? "—"}</td>
                    <td>{matchLabel(row)}</td>
                    <td>
                      <select
                        aria-label={`Decision for row ${row.row_number}`}
                        value={state?.decision ?? row.suggested_decision}
                        onChange={(event) => {
                          const decision = event.target.value as RowDecision;
                          setDecisions((current) => ({
                            ...current,
                            [row.row_number]: {
                              decision,
                              targetId:
                                decision === "create" || decision === "skip"
                                  ? null
                                  : current[row.row_number]?.targetId ?? row.matches[0]?.id ?? null,
                            },
                          }));
                          setConfirmed(false);
                        }}
                      >
                        {(Object.keys(DECISION_LABELS) as RowDecision[]).map((decision) => (
                          <option key={decision} value={decision}>
                            {DECISION_LABELS[decision]}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      {row.matches.length > 1 &&
                      state?.decision !== "create" &&
                      state?.decision !== "skip" ? (
                        <select
                          aria-label={`Match for row ${row.row_number}`}
                          value={state?.targetId ?? row.matches[0].id}
                          onChange={(event) => {
                            setDecisions((current) => ({
                              ...current,
                              [row.row_number]: {
                                decision: current[row.row_number]?.decision ?? "use_existing",
                                targetId: event.target.value,
                              },
                            }));
                            setConfirmed(false);
                          }}
                        >
                          {row.matches.map((match) => (
                            <option key={match.id} value={match.id}>
                              {match.name} ({match.method})
                            </option>
                          ))}
                        </select>
                      ) : (
                        <span className="muted">{row.matches[0]?.name ?? "New record"}</span>
                      )}
                    </td>
                    <td>
                      {row.issues.map((issue, index) => (
                        <p className="csv-error" key={index}>
                          {issue.message}
                        </p>
                      ))}
                      {row.warnings.map((warning, index) => (
                        <p key={index} className="muted">
                          {warning.message}
                        </p>
                      ))}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <label className="csv-confirm">
            <input
              type="checkbox"
              checked={confirmed}
              disabled={busy || changedCount === 0}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            I reviewed the proposed changes, including any matched records being updated.
          </label>
        </section>
      )}

      {step === "results" && batch && (
        <section className="import-results">
          <h3>Import results</h3>
          <ul className="import-counts">
            {STATUS_ORDER.map((status) => (
              <li key={status}>
                <strong>{batch.counts[status] ?? 0}</strong> {status}
              </li>
            ))}
          </ul>
          <p className="muted">
            Batch {batch.id.slice(0, 8)} · {batch.source_filename}
            {batch.sheet_name ? ` · sheet ${batch.sheet_name}` : ""} · {batch.import_type}
          </p>
          <div className="csv-preview-table">
            <table>
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Status</th>
                  <th>Message</th>
                </tr>
              </thead>
              <tbody>
                {batch.rows.map((row) => (
                  <tr key={row.row_number}>
                    <td>{row.row_number}</td>
                    <td>
                      <strong>{row.status}</strong>
                    </td>
                    <td>{row.message ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="import-actions">
            <button type="button" className="secondary-button" onClick={() => downloadErrors(batch)}>
              Download row errors
            </button>
            {batch.status !== "undone" && (
              <button
                type="button"
                className="secondary-button"
                disabled={busy}
                onClick={() => void runUndo(batch)}
              >
                Undo import
              </button>
            )}
          </div>

          <h3>Use in Current architecture</h3>
          {currentStateId ? (
            createdTargets.length === 0 ? (
              <p className="muted">
                This batch has no created or matched objects to place on the canvas.
              </p>
            ) : (
              <>
                <p className="muted">
                  Select exactly which imported objects appear in Current. Nothing is placed
                  automatically.
                </p>
                <ul className="import-targets">
                  {createdTargets.map((target) => (
                    <li key={`${target.kind}:${target.id}`}>
                      <label>
                        <input
                          type="checkbox"
                          aria-label={`Include ${target.name}`}
                          checked={
                            target.kind === "system"
                              ? selection.systems.has(target.id)
                              : target.kind === "integration"
                                ? selection.integrations.has(target.id)
                                : selection.objects.has(target.id)
                          }
                          onChange={() => toggleSelection(target.kind, target.id)}
                        />
                        {target.name} <small>{target.kind.replace("_", " ")}</small>
                      </label>
                    </li>
                  ))}
                </ul>
                <label className="csv-confirm">
                  <input
                    type="checkbox"
                    checked={selection.visualizeMembership}
                    onChange={(event) =>
                      setSelection((current) => ({
                        ...current,
                        visualizeMembership: event.target.checked,
                      }))
                    }
                  />
                  Visualize solution membership as containment
                </label>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={
                    busy ||
                    selection.systems.size +
                      selection.objects.size +
                      selection.integrations.size ===
                      0
                  }
                  onClick={() => void applyToCurrent()}
                >
                  Add selected to Current architecture
                </button>
              </>
            )
          ) : (
            <p className="muted">
              Open the Canvas once so Current architecture exists, then return here to place the
              selected imported objects.{" "}
              <button type="button" className="quiet-button" onClick={props.onOpenCanvas}>
                Open Canvas
              </button>
            </p>
          )}
        </section>
      )}

      {batches.length > 0 && (
        <details className="csv-help import-history">
          <summary>Recent imports</summary>
          <ul>
            {batches.slice(0, 10).map((item) => (
              <li key={item.id}>
                {item.source_filename} · {item.import_type} · {item.status}
                {item.status !== "undone" && (
                  <button
                    type="button"
                    className="quiet-button"
                    disabled={busy}
                    onClick={() => void runUndo(item)}
                  >
                    Undo
                  </button>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}

      <footer className="csv-dialog-footer">
        {step === "upload" && (
          <>
            <button
              type="button"
              className="secondary-button"
              onClick={() => downloadCsv(buildTemplateCsv(fields), `architecture-${importKind}-template.csv`)}
            >
              Download CSV template
            </button>
            <button
              type="button"
              disabled={!sheet || busy || missingRequired().length > 0}
              onClick={() => void runPreview()}
            >
              {busy ? "Validating…" : "Preview parsed rows"}
            </button>
          </>
        )}
        {step === "preview" && (
          <>
            <button type="button" className="secondary-button" onClick={() => setStep("upload")}>
              Back to mapping
            </button>
            <button type="button" disabled={!canCommit} onClick={() => void runCommit()}>
              {busy ? "Applying…" : `Apply ${changedCount} changes`}
            </button>
          </>
        )}
        {step === "results" && (
          <button type="button" onClick={props.onClose}>
            Done
          </button>
        )}
      </footer>
    </dialog>
  );
}
