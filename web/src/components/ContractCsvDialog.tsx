import React from "react";
import type { GraphDocument } from "../contractGraphTypes";
import {
  CSV_COLUMNS, CSV_FUNCTIONS, CSV_MAX_BYTES, MappingCsvError, buildCsvProposal,
  downloadCsv, exportMappingCsv, issueReportCsv, parseMappingCsv, suggestColumns,
  templateMappingCsv, type ColumnSelection, type CsvField, type CsvIssue,
  type FieldSelection,
} from "../contractMappingCsv";

type Props = {
  kind: "import" | "export";
  contractName: string;
  phase: string;
  dirty: boolean;
  graph: GraphDocument;
  senderFields: CsvField[];
  receiverFields: CsvField[];
  contextKey: string;
  newId: () => string;
  onApply: (graph: GraphDocument, contextKey: string, count: number) => void;
  onClose: () => void;
};

function FieldPicker({ label, fields, value, onChange }: {
  label: string;
  fields: CsvField[];
  value: string;
  onChange: (value: string) => void;
}) {
  const [search, setSearch] = React.useState("");
  const matches = fields.filter((field) => field.id === value
    || `${field.name} ${field.label ?? ""}`.toLowerCase().includes(search.toLowerCase()));
  return (
    <div className="csv-field-picker">
      <input aria-label={`Search ${label}`} placeholder="Search existing fields" value={search}
        onChange={(event) => setSearch(event.target.value)} />
      <select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">Select a field</option>
        {matches.map((field) => <option key={field.id} value={field.id}>
          {field.name} ({field.data_type}){fields.filter((other) => other.name === field.name).length > 1 ? ` · ${field.id}` : ""}
        </option>)}
      </select>
    </div>
  );
}

export default function ContractCsvDialog(props: Props) {
  const { kind, graph, senderFields, receiverFields } = props;
  const dialogRef = React.useRef<HTMLDialogElement>(null);
  const readSequence = React.useRef(0);
  const [previewContext, setPreviewContext] = React.useState(props.contextKey);
  const [text, setText] = React.useState("");
  const [filename, setFilename] = React.useState("");
  const [delimiter, setDelimiter] = React.useState("");
  const [columns, setColumns] = React.useState<ColumnSelection>({});
  const [fieldSelections, setFieldSelections] = React.useState<FieldSelection>({});
  const [mode, setMode] = React.useState<"add" | "replace">("add");
  const [fileIssues, setFileIssues] = React.useState<CsvIssue[]>([]);
  const [reading, setReading] = React.useState(false);
  const [confirmed, setConfirmed] = React.useState(false);
  const stale = previewContext !== props.contextKey;
  const basename = `${props.contractName}-${props.phase}-mappings-v1`;

  React.useEffect(() => {
    const previousFocus = document.activeElement;
    dialogRef.current?.showModal();
    return () => {
      readSequence.current++;
      dialogRef.current?.close();
      if (previousFocus instanceof HTMLElement) previousFocus.focus();
    };
  }, []);

  const parsed = React.useMemo(() => {
    if (!text) return { table: null, issues: [] };
    try {
      return { table: parseMappingCsv(text, delimiter), issues: [] };
    } catch (error) {
      if (!(error instanceof MappingCsvError)) throw error;
      return { table: null, issues: error.issues };
    }
  }, [text, delimiter]);
  const proposal = React.useMemo(() => parsed.table ? buildCsvProposal({
    table: parsed.table, columns, fieldSelections, graph, senderFields, receiverFields,
    mode, newId: props.newId,
  }) : null, [parsed.table, columns, fieldSelections, graph, senderFields, receiverFields, mode, props.newId]);
  const exported = React.useMemo(() => {
    if (kind !== "export") return { text: "", issues: [] };
    try {
      return { text: exportMappingCsv(graph, senderFields, receiverFields), issues: [] };
    } catch (error) {
      if (!(error instanceof MappingCsvError)) throw error;
      return { text: "", issues: error.issues };
    }
  }, [kind, graph, senderFields, receiverFields]);
  const issues = [...fileIssues, ...parsed.issues, ...(proposal?.issues ?? []), ...exported.issues];
  const changedCount = proposal?.rows.filter((row) => row.action === "add" || row.action === "replace").length ?? 0;
  const summary = proposal ? ["add", "unchanged", "replace", "conflict", "invalid"].map((action) =>
    `${proposal.rows.filter((row) => row.action === action).length} ${action}`).join(" · ") : "";

  async function readFile(file: File) {
    const sequence = ++readSequence.current;
    setFileIssues([]);
    setText("");
    setFilename(file.name);
    setFieldSelections({});
    setColumns({});
    setConfirmed(false);
    setPreviewContext(props.contextKey);
    if (file.size > CSV_MAX_BYTES) {
      setFileIssues([{ row: 0, column: "", message: "CSV must not exceed 1 MiB." }]);
      return;
    }
    setReading(true);
    try {
      const content = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer());
      if (sequence !== readSequence.current) return;
      setText(content);
      if (!content.trim()) {
        setFileIssues([{ row: 0, column: "", message: "The file is empty. Download a template to get started." }]);
        return;
      }
      try {
        const table = parseMappingCsv(content, delimiter);
        setColumns(suggestColumns(table.headers));
      } catch (error) {
        if (!(error instanceof MappingCsvError)) throw error;
        // Keep the text available so a delimiter override can repair the preview.
      }
    } catch (error) {
      if (sequence === readSequence.current) setFileIssues([{
        row: 0, column: "", message: error instanceof Error
          ? `Could not read UTF-8 CSV: ${error.message}` : "Could not read UTF-8 CSV.",
      }]);
    } finally {
      if (sequence === readSequence.current) setReading(false);
    }
  }

  function changeDelimiter(value: string) {
    setDelimiter(value);
    setConfirmed(false);
    setFieldSelections({});
    if (!text) return;
    try {
      setColumns(suggestColumns(parseMappingCsv(text, value).headers));
    } catch (error) {
      if (!(error instanceof MappingCsvError)) throw error;
      setColumns({});
    }
  }

  return (
    <dialog ref={dialogRef} className="contract-csv-dialog" aria-labelledby="csv-dialog-title"
      onCancel={(event) => { event.preventDefault(); props.onClose(); }}>
      <header className="csv-dialog-header">
        <div>
          <h2 id="csv-dialog-title">{kind === "import" ? "Import mappings from CSV" : "Export mappings to CSV"}</h2>
          <p>{props.contractName} · {props.phase} · {props.dirty ? "Unsaved draft" : "Current draft"}</p>
        </div>
        <button type="button" className="secondary-button" onClick={props.onClose}>Close</button>
      </header>
      <p>Only this tab's mappings are exchanged. CSV v1 supports direct mappings or one conversion per target.
        Other tabs, catalog fields, and sample data stay unchanged.</p>
      {stale && <div role="alert" className="csv-error">
        The contract, tab, schema, or draft changed. Refresh the preview before continuing.
        <button type="button" className="secondary-button" onClick={() => {
          setPreviewContext(props.contextKey); setFieldSelections({}); setConfirmed(false);
        }}>Refresh preview</button>
      </div>}
      {kind === "import" && <>
        <div className="csv-upload" onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            if (event.dataTransfer.files.length !== 1) {
              setFileIssues([{ row: 0, column: "", message: "Choose exactly one CSV file." }]);
            } else void readFile(event.dataTransfer.files[0]);
          }}>
          <label>Choose CSV (or drop one here)
            <input type="file" accept=".csv,text/csv" onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void readFile(file);
              event.target.value = "";
            }} />
          </label>
          <p>UTF-8 · up to 1 MiB / 500 mapping rows. Format version 1 is required.</p>
          <button type="button" className="secondary-button" onClick={() =>
            downloadCsv(templateMappingCsv(senderFields, receiverFields), `${basename}-template.csv`)}>
            Download template
          </button>
          <p>The template includes one example using compatible current fields when available.
            Review it before importing. Format spreadsheet columns as Text to avoid autoformatting.</p>
        </div>
        <label>Delimiter
          <select value={delimiter} onChange={(event) => changeDelimiter(event.target.value)}>
            <option value="">Auto-detect</option><option value=",">Comma</option>
            <option value=";">Semicolon</option><option value={"\t"}>Tab</option>
          </select>
        </label>
        {reading && <p role="status">Reading CSV…</p>}
        {parsed.table && <>
          <p>{filename} · {parsed.table.rows.length} mapping rows · detected {
            parsed.table.delimiter === "\t" ? "tab" : parsed.table.delimiter === ";" ? "semicolon" : "comma"
          } delimiter</p>
          <fieldset className="csv-column-grid">
            <legend>Match spreadsheet columns</legend>
            {CSV_COLUMNS.map((column) => <label key={column}>{column}
              {["format_version", "source_field", "target_field"].includes(column) ? " (required)" : ""}
              <select value={columns[column] ?? ""} onChange={(event) => {
                setColumns((current) => {
                  const next = { ...current };
                  if (event.target.value === "") delete next[column];
                  else next[column] = Number(event.target.value);
                  return next;
                });
                setFieldSelections({}); setConfirmed(false);
              }}>
                <option value="">Not provided</option>
                {parsed.table!.headers.map((header, index) =>
                  <option key={index} value={index}>{header}</option>)}
              </select>
            </label>)}
          </fieldset>
          <label>Existing mappings
            <select value={mode} onChange={(event) => {
              setMode(event.target.value === "replace" ? "replace" : "add"); setConfirmed(false);
            }}>
              <option value="add">Add only (preserve existing mappings)</option>
              <option value="replace">Replace matching targets (unlisted targets stay unchanged)</option>
            </select>
          </label>
        </>}
        {proposal && <>
          <p role="status">{summary}</p>
          <div className="csv-preview-table" tabIndex={0} aria-label="Mapping change preview">
            <table><thead><tr>
              <th scope="col">CSV row</th><th scope="col">Source field</th><th scope="col">Transformation</th>
              <th scope="col">Target field</th><th scope="col">Change / validation</th>
            </tr></thead><tbody>
              {proposal.rows.map((row) => <tr key={row.row}>
                <td>{row.row}</td>
                <td>{row.sourceName}
                  {(!row.sourceId || fieldSelections[`${row.row}:source_field`]) &&
                    <FieldPicker label={`Source field for row ${row.row}`} fields={senderFields}
                      value={fieldSelections[`${row.row}:source_field`] ?? ""}
                      onChange={(value) => {
                        setFieldSelections((current) => ({ ...current, [`${row.row}:source_field`]: value }));
                        setConfirmed(false);
                      }} />}
                </td>
                <td>{row.transformation}</td>
                <td>{row.targetName}
                  {(!row.targetId || fieldSelections[`${row.row}:target_field`]) &&
                    <FieldPicker label={`Target field for row ${row.row}`} fields={receiverFields}
                      value={fieldSelections[`${row.row}:target_field`] ?? ""}
                      onChange={(value) => {
                        setFieldSelections((current) => ({ ...current, [`${row.row}:target_field`]: value }));
                        setConfirmed(false);
                      }} />}
                </td>
                <td><strong>{row.action}</strong>
                  {row.issues.map((issue, index) => <p className="csv-error" key={index}>{issue.message}</p>)}
                  {row.warning && <p>{row.warning} This design issue will remain visible in the editor.</p>}
                </td>
              </tr>)}
            </tbody></table>
          </div>
        </>}
        <details className="csv-help"><summary>CSV format and supported conversions</summary>
          <p>Use exact field names, not display labels. Leave transformation and its settings empty for direct mappings.
            Available function keys: {CSV_FUNCTIONS.join(", ")}.</p>
          <p>Error policy: fail (default) or skip. date/parseDate require input_format;
            date/formatDate require output_format. country_calling_code is 1-3 digits without a leading zero.
            JSON/default-value settings, advanced nodes, and chains are outside v1.</p>
          <p>Formula-like text is rejected rather than modified. Spreadsheet software may change values when editing.
            CSV row numbers count records, including the header, not physical lines inside quoted cells.</p>
        </details>
      </>}
      {kind === "export" && <p role="status">{exported.text
        ? `${Math.max(0, parseMappingCsv(exported.text).rows.length)} mappings ready to export, including unsaved changes. No matrix filters are applied.`
        : "This tab cannot be exported without losing information. Nothing will be downloaded."}</p>}
      {issues.length > 0 && <section role="alert" className="csv-issues">
        <h3>Resolve these issues before continuing</h3>
        <ul>{issues.slice(0, 30).map((issue, index) => <li key={index}>
          {issue.row > 0 ? `Row ${issue.row}: ` : ""}{issue.message}
        </li>)}</ul>
        {issues.length > 30 && <p>{issues.length - 30} more issues are included in the report.</p>}
        <button type="button" className="secondary-button" onClick={() =>
          downloadCsv(issueReportCsv(issues), `${basename}-issues.csv`)}>Download issue report</button>
      </section>}
      <footer className="csv-dialog-footer">
        {kind === "import" ? <>
          <label className="csv-confirm">
            <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)}
              disabled={!proposal?.graph || issues.length > 0 || stale || reading || !changedCount} />
            I reviewed the changes{mode === "replace" ? " and the mappings being replaced" : ""}.
          </label>
          <button type="button" disabled={!confirmed || !proposal?.graph || issues.length > 0 || stale || reading || !changedCount}
            onClick={() => {
              if (proposal?.graph && !stale && confirmed && !issues.length) {
                props.onApply(proposal.graph, previewContext, changedCount);
              }
            }}>Apply {changedCount} changes to draft</button>
          <p>Nothing is saved until you use Save in the editor. Invalid or conflicting rows are never partially applied.</p>
        </> : <button type="button" disabled={!exported.text || stale} onClick={() =>
          downloadCsv(exported.text, `${basename}.csv`)}>Download CSV</button>}
      </footer>
    </dialog>
  );
}
