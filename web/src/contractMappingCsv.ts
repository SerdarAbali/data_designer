import Papa from "papaparse";
import type { GraphDocument, GraphNodeDocument } from "./contractGraphTypes";
import { deriveMappingChains, transformationLabel, type MappingChain } from "./mappingGraphModel";
import { validateTypeChain } from "./mappingTypeValidation";

export const CSV_MAX_BYTES = 1024 * 1024;
export const CSV_MAX_ROWS = 500;
export const CSV_COLUMNS = [
  "format_version", "source_field", "target_field", "transformation",
  "error_policy", "input_format", "output_format", "country_calling_code",
] as const;
export type CsvColumn = typeof CSV_COLUMNS[number];
export const CSV_FUNCTIONS = [
  "trim", "title", "lower", "upper", "e164", "date", "toInt", "toNumber",
  "toString", "toBoolean", "parseDate", "formatDate",
] as const;
export type CsvField = {
  id: string;
  name: string;
  label?: string;
  data_type: string;
  required?: boolean;
  nullable?: boolean;
};
export type CsvIssue = { row: number; column: string; message: string };
export class MappingCsvError extends Error {
  constructor(public readonly issues: CsvIssue[]) {
    super(issues.map((issue) => `${issue.row ? `Row ${issue.row}: ` : ""}${issue.message}`).join(" "));
    this.name = "MappingCsvError";
  }
}
export type CsvTable = {
  headers: string[];
  rows: string[][];
  delimiter: string;
};
export type ColumnSelection = Partial<Record<CsvColumn, number>>;
export type FieldSelection = Record<string, string>;
export type CsvPreviewRow = {
  row: number;
  sourceName: string;
  targetName: string;
  sourceId: string | null;
  targetId: string | null;
  transformation: string;
  action: "add" | "unchanged" | "replace" | "conflict" | "invalid";
  issues: CsvIssue[];
  warning: string;
};
export type CsvProposal = {
  graph: GraphDocument | null;
  rows: CsvPreviewRow[];
  issues: CsvIssue[];
};

const byteLength = (text: string) => new TextEncoder().encode(text).length;
const configByteLength = (config: Record<string, unknown>) =>
  byteLength(JSON.stringify(config).replace(/[\u007f-\uffff]/g,
    (char) => `\\u${char.charCodeAt(0).toString(16).padStart(4, "0")}`));
const problem = (message: string, row = 0, column = ""): CsvIssue => ({ row, column, message });

export function isFormulaLike(value: string): boolean {
  return /^[\s\u0000-\u001f\u007f]*[=+\-@＝＋－＠]/u.test(value)
    || /^[\t\r\n]/u.test(value);
}

export function parseMappingCsv(text: string, delimiter?: string): CsvTable {
  if (byteLength(text) > CSV_MAX_BYTES) {
    throw new MappingCsvError([problem("CSV must not exceed 1 MiB.")]);
  }
  if (!text.replace(/^\uFEFF/, "").trim()) {
    throw new MappingCsvError([problem("The file is empty. Download a template to get started.")]);
  }
  const result = Papa.parse<string[]>(text.replace(/^\uFEFF/, ""), {
    delimiter: delimiter || "",
    delimitersToGuess: [",", ";", "\t"],
    skipEmptyLines: "greedy",
    preview: CSV_MAX_ROWS + 2,
  });
  const errors = result.errors
    .filter((error) => error.code !== "UndetectableDelimiter")
    .map((error) => problem(error.message, (error.row ?? 0) + 1));
  const [headers = [], ...rows] = result.data;
  if (rows.length > CSV_MAX_ROWS || result.meta.truncated) {
    errors.push(problem(`CSV must not exceed ${CSV_MAX_ROWS} mapping rows.`));
  }
  if (headers.some((header) => !header.trim())
    || new Set(headers.map((header) => header.trim().toLowerCase())).size !== headers.length) {
    errors.push(problem("Column headers must be nonempty and unique.", 1));
  }
  headers.forEach((header) => {
    if (isFormulaLike(header)) errors.push(problem("Formula-like column headers are not supported.", 1));
  });
  rows.forEach((row, index) => {
    if (row.length !== headers.length) {
      errors.push(problem(`Expected ${headers.length} cells; found ${row.length}. Check the delimiter and quotes.`, index + 2));
    }
  });
  if (errors.length) throw new MappingCsvError(errors);
  return { headers, rows, delimiter: result.meta.delimiter || delimiter || "," };
}

export function suggestColumns(headers: string[]): ColumnSelection {
  const result: ColumnSelection = {};
  for (const column of CSV_COLUMNS) {
    const index = headers.findIndex((header) =>
      header.trim().toLowerCase().replace(/[\s-]+/g, "_") === column);
    if (index >= 0) result[column] = index;
  }
  return result;
}

function readConfig(values: Record<CsvColumn, string>, row: number): {
  config: Record<string, unknown> | null;
  issues: CsvIssue[];
} {
  const issues: CsvIssue[] = [];
  const fn = values.transformation;
  if (!fn) {
    if (["error_policy", "input_format", "output_format", "country_calling_code"]
      .some((key) => values[key as CsvColumn])) {
      issues.push(problem("Direct mappings cannot have transformation settings.", row, "transformation"));
    }
    return { config: null, issues };
  }
  if (!CSV_FUNCTIONS.some((value) => value === fn)) {
    issues.push(problem("Choose a supported transformation function key.", row, "transformation"));
  }
  const policy = values.error_policy || "fail";
  if (policy !== "fail" && policy !== "skip") {
    issues.push(problem("Error policy must be fail or skip. Default-value policies are outside CSV v1.", row, "error_policy"));
  }
  if ((fn === "date" || fn === "parseDate") && !values.input_format) {
    issues.push(problem("This transformation requires input_format.", row, "input_format"));
  }
  if ((fn === "date" || fn === "formatDate") && !values.output_format) {
    issues.push(problem("This transformation requires output_format.", row, "output_format"));
  }
  if (values.country_calling_code && !/^[1-9]\d{0,2}$/.test(values.country_calling_code)) {
    issues.push(problem("Calling code must be 1-3 digits without a leading zero.", row, "country_calling_code"));
  }
  const config: Record<string, unknown> = { function: fn, errorPolicy: policy };
  for (const [column, key] of [
    ["input_format", "inputFormat"], ["output_format", "outputFormat"],
    ["country_calling_code", "countryCallingCode"],
  ] as const) {
    if (values[column]) config[key] = values[column];
  }
  if (configByteLength(config) > 8192) {
    issues.push(problem("Transformation settings must not exceed 8 KiB.", row, "transformation"));
  }
  return { config, issues };
}

function configValues(config: Record<string, unknown>): Record<CsvColumn, string> | null {
  const allowed = new Set(["function", "errorPolicy", "inputFormat", "outputFormat", "countryCallingCode"]);
  if (Object.keys(config).some((key) => !allowed.has(key))
    || Object.values(config).some((value) => typeof value !== "string")) return null;
  const values: Record<CsvColumn, string> = {
    format_version: "1", source_field: "", target_field: "",
    transformation: String(config.function ?? ""),
    error_policy: String(config.errorPolicy ?? "fail"),
    input_format: String(config.inputFormat ?? ""),
    output_format: String(config.outputFormat ?? ""),
    country_calling_code: String(config.countryCallingCode ?? ""),
  };
  // Empty optional config keys cannot be faithfully represented by an empty cell.
  if (["errorPolicy", "inputFormat", "outputFormat", "countryCallingCode"].some((key) => config[key] === "")) return null;
  return values.transformation && !readConfig(values, 0).issues.length ? values : null;
}

type SimpleMapping = {
  sourceId: string;
  targetId: string;
  config: Record<string, unknown> | null;
  nodeIds: string[];
  edgeIds: string[];
};

function simpleMapping(chain: MappingChain, graph: GraphDocument): SimpleMapping | null {
  const sourceId = chain.inputs[0]?.senderFieldId;
  if (!chain.receiverFieldId || !sourceId || chain.inputs.length !== 1
    || chain.issues.length || chain.transformations.length > 1) return null;
  const transform = chain.transformations[0];
  if (transform && (transform.nodeType !== "fx" || !configValues(transform.config)
    || graph.edges.filter((edge) => edge.sourceNodeId === transform.nodeId).length !== 1
    || graph.edges.filter((edge) => edge.targetNodeId === transform.nodeId).length !== 1)) return null;
  return {
    sourceId, targetId: chain.receiverFieldId, config: transform?.config ?? null,
    nodeIds: chain.transformationNodeIds, edgeIds: chain.edgeIds,
  };
}

function signature(mapping: Pick<SimpleMapping, "sourceId" | "config">): string {
  const values = mapping.config ? configValues(mapping.config) : null;
  return JSON.stringify([mapping.sourceId, values
    ? [values.transformation, values.error_policy, values.input_format,
      values.output_format, values.country_calling_code]
    : null]);
}

export function serializeCsv(headers: readonly string[], rows: string[][]): string {
  const issues: CsvIssue[] = [];
  [Array.from(headers), ...rows].forEach((cells, index) => cells.forEach((cell, column) => {
    if (isFormulaLike(cell)) {
      issues.push(problem("Formula-like text cannot be safely exported. Change the value before exporting.", index + 1, headers[column] ?? ""));
    }
  }));
  if (issues.length) throw new MappingCsvError(issues);
  return "\uFEFF" + Papa.unparse({ fields: Array.from(headers), data: rows }, {
    quotes: true, newline: "\r\n",
  });
}

export function exportMappingCsv(graph: GraphDocument, senderFields: CsvField[], receiverFields: CsvField[]): string {
  const issues: CsvIssue[] = graphLimitIssues(graph);
  const chains = deriveMappingChains({ graph, senderFields, receiverFields });
  const claimedEdges = new Set<string>();
  const claimedTransforms = new Set<string>();
  const targets = new Set<string>();
  const rows: string[][] = [];
  if (graph.nodes.filter((node) => node.type === "source").length > 1
    || graph.nodes.filter((node) => node.type === "target").length > 1
    || graph.nodes.some((node) => (node.type === "source" || node.type === "target")
      && Object.keys(node.config).length > 0)) {
    issues.push(problem("The phase has unsupported endpoint structure or settings."));
  }
  for (const chain of chains) {
    if (!chain.receiverEdgeId && !chain.edgeIds.length && !chain.transformations.length) continue;
    const mapping = simpleMapping(chain, graph);
    if (!mapping) {
      issues.push(problem(`Mapping to ${receiverFields.find((field) => field.id === chain.receiverFieldId)?.name ?? "an unknown target"} has advanced or invalid structure. CSV v1 supports direct mappings or one independent conversion.`));
      continue;
    }
    const source = senderFields.find((field) => field.id === mapping.sourceId);
    const target = receiverFields.find((field) => field.id === mapping.targetId);
    if (!source || !target) {
      issues.push(problem("A mapping references a missing catalog field."));
      continue;
    }
    if (!mapping.config && source.data_type.trim().toLowerCase() !== target.data_type.trim().toLowerCase()) {
      issues.push(problem(`Direct mapping to ${target.name} has incompatible catalog data types. Add a conversion before exporting.`));
    }
    if (senderFields.filter((field) => field.name === source.name).length !== 1
      || receiverFields.filter((field) => field.name === target.name).length !== 1) {
      issues.push(problem("Mapped field names must be unique in each endpoint object for export."));
    }
    if (targets.has(target.id)) issues.push(problem(`Target ${target.name} has multiple assignments.`));
    targets.add(target.id);
    mapping.edgeIds.forEach((id) => claimedEdges.add(id));
    mapping.nodeIds.forEach((id) => claimedTransforms.add(id));
    const values = mapping.config ? configValues(mapping.config)! : {
      format_version: "1", source_field: "", target_field: "", transformation: "",
      error_policy: "", input_format: "", output_format: "", country_calling_code: "",
    };
    values.source_field = source.name;
    values.target_field = target.name;
    rows.push(CSV_COLUMNS.map((column) => values[column]));
  }
  if (graph.edges.some((edge) => !claimedEdges.has(edge.id))
    || graph.nodes.some((node) => node.type !== "source" && node.type !== "target" && !claimedTransforms.has(node.id))) {
    issues.push(problem("The phase contains disconnected or unsupported graph elements; nothing was exported."));
  }
  if (issues.length) throw new MappingCsvError(issues);
  return serializeCsv(CSV_COLUMNS, rows);
}

export function templateMappingCsv(senderFields: CsvField[], receiverFields: CsvField[]): string {
  const source = senderFields.find((field) => !isFormulaLike(field.name)
    && senderFields.filter((other) => other.name === field.name).length === 1);
  const target = receiverFields.find((field) => !isFormulaLike(field.name)
    && field.data_type === source?.data_type
    && receiverFields.filter((other) => other.name === field.name).length === 1);
  return serializeCsv(CSV_COLUMNS, source && target
    ? [["1", source.name, target.name, "", "", "", "", ""]] : []);
}

export function graphLimitIssues(graph: GraphDocument): CsvIssue[] {
  const issues: CsvIssue[] = [];
  if (graph.nodes.length > 200) issues.push(problem("The resulting graph exceeds 200 nodes."));
  if (graph.edges.length > 500) issues.push(problem("The resulting graph exceeds 500 edges."));
  if (byteLength(JSON.stringify(graph)) > 262144) issues.push(problem("The resulting graph exceeds 256 KiB."));
  if (graph.nodes.some((node) => configByteLength(node.config) > 8192)) {
    issues.push(problem("A node configuration exceeds 8 KiB."));
  }
  return issues;
}

export function buildCsvProposal(input: {
  table: CsvTable;
  columns: ColumnSelection;
  fieldSelections?: FieldSelection;
  graph: GraphDocument;
  senderFields: CsvField[];
  receiverFields: CsvField[];
  mode: "add" | "replace";
  newId: () => string;
}): CsvProposal {
  const { table, columns, graph, senderFields, receiverFields, mode, newId } = input;
  const issues: CsvIssue[] = [];
  const mappedIndexes = Object.values(columns).filter((index) => index !== undefined);
  if (new Set(mappedIndexes).size !== mappedIndexes.length) {
    issues.push(problem("Each CSV column can be assigned only once."));
  }
  if (mappedIndexes.some((index) => !Number.isInteger(index) || index < 0 || index >= table.headers.length)) {
    issues.push(problem("A selected column is unavailable. Remap the headers."));
  }
  for (const required of ["format_version", "source_field", "target_field"] as const) {
    if (columns[required] === undefined) issues.push(problem(`Select a column for ${required}.`, 1, required));
  }
  table.headers.forEach((header, index) => {
    if (!mappedIndexes.includes(index) && table.rows.some((row) => row[index])) {
      issues.push(problem(`Unrecognized nonempty column "${header}". Map it or remove it from the file.`, 1, header));
    }
  });
  if (table.rows.length > CSV_MAX_ROWS) issues.push(problem(`CSV must not exceed ${CSV_MAX_ROWS} mapping rows.`));
  const next: GraphDocument = {
    version: 1, nodes: graph.nodes.map((node) => ({ ...node, position: { ...node.position }, config: { ...node.config } })),
    edges: graph.edges.map((edge) => ({ ...edge })),
  };
  const sourceNodes = next.nodes.filter((node) => node.type === "source");
  const targetNodes = next.nodes.filter((node) => node.type === "target");
  if (sourceNodes.length > 1 || targetNodes.length > 1) {
    issues.push(problem("The existing graph has multiple endpoint nodes."));
  }
  const endpoint = (type: "source" | "target"): GraphNodeDocument => {
    const existing = next.nodes.find((node) => node.type === type);
    if (existing) return existing;
    const node: GraphNodeDocument = {
      id: newId(), type, config: {}, position: { x: type === "source" ? 80 : 700, y: 100 },
    };
    next.nodes.push(node);
    return node;
  };
  const sourceNode = endpoint("source");
  const targetNode = endpoint("target");
  const chains = deriveMappingChains({ graph, senderFields, receiverFields });
  const seenTargets = new Set<string>();
  const previews: CsvPreviewRow[] = [];
  for (const [index, cells] of table.rows.entries()) {
    const row = index + 2;
    const values = Object.fromEntries(CSV_COLUMNS.map((column) =>
      [column, columns[column] === undefined ? "" : cells[columns[column]] ?? ""])) as Record<CsvColumn, string>;
    const rowIssues: CsvIssue[] = [];
    cells.forEach((cell, cellIndex) => {
      if (isFormulaLike(cell)) rowIssues.push(problem("Formula-like text is not supported. Use plain text values.", row, table.headers[cellIndex]));
    });
    if (values.format_version !== "1") rowIssues.push(problem("format_version must be 1.", row, "format_version"));
    const resolve = (column: "source_field" | "target_field", fields: CsvField[]): CsvField | undefined => {
      const selected = input.fieldSelections?.[`${row}:${column}`];
      const matches = selected ? fields.filter((field) => field.id === selected)
        : fields.filter((field) => field.name === values[column]);
      if (matches.length !== 1) {
        rowIssues.push(problem(matches.length > 1
          ? `Field name is ambiguous. Select the intended ${column}.`
          : `Field was not found. Select an existing ${column}; no schema will be created.`, row, column));
        return undefined;
      }
      return matches[0];
    };
    const source = resolve("source_field", senderFields);
    const target = resolve("target_field", receiverFields);
    if (target && seenTargets.has(target.id)) rowIssues.push(problem("This receiver field is assigned more than once in the file.", row, "target_field"));
    if (target) seenTargets.add(target.id);
    const { config, issues: configIssues } = readConfig(values, row);
    rowIssues.push(...configIssues);
    const preview: CsvPreviewRow = {
      row, sourceName: values.source_field, targetName: values.target_field,
      sourceId: source?.id ?? null, targetId: target?.id ?? null,
      transformation: config ? transformationLabel("fx", config) : "Direct",
      action: "invalid", issues: rowIssues, warning: "",
    };
    previews.push(preview);
    if (!source || !target || rowIssues.length) continue;
    if (!config && source.data_type.trim().toLowerCase() !== target.data_type.trim().toLowerCase()) {
      rowIssues.push(problem("Direct mappings require identical catalog data types. Add a conversion before importing.", row, "transformation"));
      continue;
    }
    const validation = validateTypeChain({
      senderType: source.data_type, receiverType: target.data_type,
      receiverNullable: target.nullable || !target.required,
      transformations: config ? [{ nodeType: "fx", config, label: preview.transformation }] : [],
    });
    preview.warning = validation.status === "Valid" ? "" : `${validation.status}: ${validation.issue}`;
    const existingChains = chains.filter((chain) => chain.receiverFieldId === target.id && chain.receiverEdgeId);
    const existing = existingChains.length === 1 ? simpleMapping(existingChains[0], graph) : null;
    if (existingChains.length) {
      if (existing && signature(existing) === signature({ sourceId: source.id, config })) {
        preview.action = "unchanged";
        continue;
      }
      preview.action = "conflict";
      if (mode === "add") {
        rowIssues.push(problem("Target is already mapped differently. Choose Replace matching to change it.", row, "target_field"));
        continue;
      }
      if (!existing) {
        rowIssues.push(problem("Existing mapping has advanced/shared structure. Edit it in the canvas before replacing through CSV.", row, "target_field"));
        continue;
      }
      next.edges = next.edges.filter((edge) => !existing.edgeIds.includes(edge.id));
      next.nodes = next.nodes.filter((node) => !existing.nodeIds.includes(node.id));
      preview.action = "replace";
    } else {
      preview.action = "add";
    }
    let outputNode = sourceNode;
    let outputPort = `field:${source.id}`;
    if (config) {
      outputNode = {
        id: newId(), type: "fx", config,
        position: { x: (sourceNode.position.x + targetNode.position.x) / 2, y: 100 + index * 60 },
      };
      next.nodes.push(outputNode);
      next.edges.push({
        id: newId(), sourceNodeId: sourceNode.id, sourcePortId: outputPort,
        targetNodeId: outputNode.id, targetPortId: "input",
      });
      outputPort = "output";
    }
    next.edges.push({
      id: newId(), sourceNodeId: outputNode.id, sourcePortId: outputPort,
      targetNodeId: targetNode.id, targetPortId: `field:${target.id}`,
    });
  }
  issues.push(...previews.flatMap((row) => row.issues), ...graphLimitIssues(next));
  return { graph: issues.length ? null : next, rows: previews, issues };
}

export function issueReportCsv(issues: CsvIssue[]): string {
  // JSON wrappers keep user-controlled header names away from formula prefixes.
  return serializeCsv(["row", "column", "message"], issues.map((issue) =>
    [String(issue.row), JSON.stringify(issue.column), JSON.stringify(issue.message)]));
}

export function downloadCsv(text: string, filename: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename.replace(/[^a-zA-Z0-9._-]/g, "_");
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
