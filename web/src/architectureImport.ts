import type ExcelJS from "exceljs";
import Papa from "papaparse";
import {
  CSV_MAX_BYTES,
  CSV_MAX_ROWS,
  downloadCsv,
  isFormulaLike,
  serializeCsv,
} from "./contractMappingCsv";

export const IMPORT_MAX_ROWS = CSV_MAX_ROWS;
export const IMPORT_MAX_CSV_BYTES = CSV_MAX_BYTES;
export const IMPORT_MAX_XLSX_BYTES = 2 * 1024 * 1024;
export const IMPORT_MAX_HEADERS = 64;

export type ImportKind = "system" | "information_object" | "integration" | "solution";
export type RowDecision = "create" | "update" | "use_existing" | "skip";
export type MatchMethod = "external_id" | "exact_name" | "alias" | "similar_name" | "none";
export type ImportIssue = { row: number; column: string; message: string };

export type ImportFieldSpec = {
  key: string;
  label: string;
  required: boolean;
  aliases: string[];
  multiple?: boolean;
};

export const IMPORT_KIND_FIELDS: Record<ImportKind, ImportFieldSpec[]> = {
  system: [
    { key: "name", label: "Name", required: true, aliases: ["system", "system name", "application"] },
    { key: "description", label: "Description", required: false, aliases: ["purpose"] },
    { key: "owner", label: "Owner", required: false, aliases: ["system owner"] },
    {
      key: "business_domain",
      label: "Business domain",
      required: false,
      aliases: ["domain", "business area"],
    },
    { key: "lifecycle", label: "Lifecycle", required: false, aliases: ["life cycle"] },
    { key: "status", label: "Status", required: false, aliases: [] },
    { key: "technology", label: "Technology", required: false, aliases: ["platform", "tech"] },
    {
      key: "external_id",
      label: "External ID",
      required: false,
      aliases: ["external id", "externalid", "source id"],
    },
    {
      key: "aliases",
      label: "Aliases",
      required: false,
      aliases: ["alias", "alternative names"],
      multiple: true,
    },
  ],
  information_object: [
    { key: "name", label: "Name", required: true, aliases: ["information object", "object"] },
    { key: "description", label: "Description", required: false, aliases: [] },
    { key: "owner", label: "Owner", required: true, aliases: ["data owner"] },
    {
      key: "authoritative_system",
      label: "Authoritative system",
      required: true,
      aliases: ["authoritative system name", "system of record"],
    },
    {
      key: "classification",
      label: "Classification",
      required: false,
      aliases: ["data classification", "sensitivity"],
    },
    { key: "external_id", label: "External ID", required: false, aliases: ["external id", "externalid"] },
  ],
  integration: [
    { key: "name", label: "Name", required: true, aliases: ["integration", "interface", "contract"] },
    { key: "description", label: "Description or purpose", required: false, aliases: ["purpose"] },
    { key: "source_system", label: "Source system", required: true, aliases: ["source", "from system"] },
    { key: "target_system", label: "Target system", required: true, aliases: ["target", "to system"] },
    {
      key: "source_object",
      label: "Source object",
      required: false,
      aliases: ["source object name", "from object"],
    },
    {
      key: "target_object",
      label: "Target object",
      required: false,
      aliases: ["target object name", "to object"],
    },
    {
      key: "integration_type",
      label: "Integration type",
      required: false,
      aliases: ["type", "interaction type", "pattern"],
    },
    { key: "owner", label: "Owner", required: false, aliases: [] },
    { key: "lifecycle", label: "Lifecycle", required: false, aliases: ["life cycle"] },
    { key: "external_id", label: "External ID", required: false, aliases: ["external id", "externalid"] },
    {
      key: "contract_reference",
      label: "Existing contract reference",
      required: false,
      aliases: ["contract", "existing contract", "contract name"],
    },
  ],
  solution: [
    { key: "name", label: "Solution name", required: true, aliases: ["solution"] },
    { key: "description", label: "Description", required: false, aliases: [] },
    { key: "owner", label: "Owner", required: false, aliases: ["solution owner"] },
    { key: "external_id", label: "External ID", required: false, aliases: ["external id", "externalid"] },
    {
      key: "included_systems",
      label: "Included systems",
      required: true,
      aliases: ["systems", "member systems", "system membership", "includes"],
      multiple: true,
    },
  ],
};

export const IMPORT_KINDS: { id: ImportKind; label: string; description: string }[] = [
  {
    id: "system",
    label: "Systems",
    description: "Catalog systems shared by every discipline and architecture state",
  },
  {
    id: "information_object",
    label: "Information objects",
    description: "Information objects with an owner and a canonical authoritative system",
  },
  {
    id: "integration",
    label: "Integrations",
    description: "Contracts between canonical systems, linked to existing contracts when referenced",
  },
  {
    id: "solution",
    label: "Solutions",
    description: "Solution boundaries that reuse canonical systems for membership",
  },
];

export type SheetTable = { headers: string[]; rows: string[][] };
export type ParsedWorkbook = {
  filename: string;
  sheets: { name: string; table: SheetTable }[];
  issues: ImportIssue[];
};

export class ImportFileError extends Error {
  constructor(readonly issues: ImportIssue[]) {
    super(issues.map((issue) => `${issue.row ? `Row ${issue.row}: ` : ""}${issue.message}`).join(" "));
    this.name = "ImportFileError";
  }
}

const byteLength = (text: string) => new TextEncoder().encode(text).length;
const problem = (message: string, row = 0, column = ""): ImportIssue => ({ row, column, message });

function tableFromRows(inputRows: string[][], issues: ImportIssue[], sheetLabel: string): SheetTable {
  const [rawHeaders = [], ...dataRows] = inputRows;
  const headers = rawHeaders.map((header) => header.trim());
  if (headers.length === 0) {
    issues.push(problem(`Sheet ${sheetLabel} has no header row.`));
    return { headers: [], rows: [] };
  }
  if (headers.length > IMPORT_MAX_HEADERS) {
    issues.push(problem(`Sheet ${sheetLabel} has more than ${IMPORT_MAX_HEADERS} columns.`));
  }
  if (
    headers.some((header) => !header)
    || new Set(headers.map((header) => header.toLowerCase())).size !== headers.length
  ) {
    issues.push(problem(`Sheet ${sheetLabel} headers must be nonempty and unique.`));
  }
  const rows: string[][] = [];
  for (const [index, row] of dataRows.entries()) {
    const values = headers.map((_, column) => (row[column] ?? "").toString());
    for (const [column, value] of values.entries()) {
      if (isFormulaLike(value)) {
        issues.push(
          problem(
            `Cell values starting with a formula character are rejected (column ${headers[column]}).`,
            index + 1,
            headers[column],
          ),
        );
      }
    }
    rows.push(values);
  }
  if (rows.length > IMPORT_MAX_ROWS) {
    issues.push(problem(`Sheet ${sheetLabel} must not exceed ${IMPORT_MAX_ROWS} data rows.`));
  }
  return { headers, rows: rows.slice(0, IMPORT_MAX_ROWS) };
}

export function parseCsvTable(text: string): SheetTable {
  if (byteLength(text) > IMPORT_MAX_CSV_BYTES) {
    throw new ImportFileError([problem("CSV must not exceed 1 MiB.")]);
  }
  const clean = text.replace(/^\uFEFF/, "");
  if (!clean.trim()) {
    throw new ImportFileError([problem("The file is empty.")]);
  }
  const result = Papa.parse<string[]>(clean, {
    delimiter: "",
    delimitersToGuess: [",", ";", "\t"],
    skipEmptyLines: "greedy",
    preview: IMPORT_MAX_ROWS + 2,
  });
  const issues = result.errors
    .filter((error) => error.code !== "UndetectableDelimiter")
    .map((error) => problem(error.message, (error.row ?? 0) + 1));
  if (issues.length) throw new ImportFileError(issues);
  const table = tableFromRows(result.data, issues, "CSV");
  if (issues.length) throw new ImportFileError(issues);
  return table;
}

export function cellText(cell: ExcelJS.Cell): { value: string; formula: boolean } {
  const raw = cell.value;
  if (raw === null || raw === undefined) return { value: "", formula: false };
  if (typeof raw === "object") {
    if ("formula" in raw || "sharedFormula" in raw) {
      const result = (raw as ExcelJS.CellFormulaValue).result;
      return { value: result === undefined || result === null ? "" : String(result), formula: true };
    }
    if (raw instanceof Date) return { value: raw.toISOString(), formula: false };
    if ("richText" in raw) {
      return { value: raw.richText.map((part) => part.text).join(""), formula: false };
    }
    if ("text" in raw && typeof raw.text === "string") return { value: raw.text, formula: false };
    if ("result" in raw) {
      const result = (raw as { result?: unknown }).result;
      return { value: result === undefined || result === null ? "" : String(result), formula: false };
    }
    return { value: String(raw), formula: false };
  }
  return { value: String(raw), formula: false };
}

function readFileText(file: File): Promise<string> {
  if (typeof file.text === "function") return file.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(new ImportFileError([problem("The file could not be read.")]));
    reader.readAsText(file);
  });
}

function readFileBuffer(file: File): Promise<ArrayBuffer> {
  if (typeof file.arrayBuffer === "function") return file.arrayBuffer();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = () => reject(new ImportFileError([problem("The file could not be read.")]));
    reader.readAsArrayBuffer(file);
  });
}

export async function parseImportFile(file: File): Promise<ParsedWorkbook> {
  const name = file.name || "import";
  const extension = name.slice(name.lastIndexOf(".")).toLowerCase();
  if (extension === ".csv" || extension === ".txt") {
    return {
      filename: name,
      sheets: [{ name: "CSV", table: parseCsvTable(await readFileText(file)) }],
      issues: [],
    };
  }
  if (extension !== ".xlsx") {
    throw new ImportFileError([
      problem("Unsupported file type. Upload a .csv or .xlsx file."),
    ]);
  }
  if (file.size > IMPORT_MAX_XLSX_BYTES) {
    throw new ImportFileError([problem("Workbook must not exceed 2 MiB.")]);
  }
  // Loaded on demand so the spreadsheet parser never ships in the initial bundle.
  const { default: ExcelJSWorkbook } = await import("exceljs");
  const workbook = new ExcelJSWorkbook.Workbook();
  await workbook.xlsx.load(await readFileBuffer(file));
  const sheets: ParsedWorkbook["sheets"] = [];
  const issues: ImportIssue[] = [];
  workbook.eachSheet((worksheet) => {
    const rows: string[][] = [];
    worksheet.eachRow({ includeEmpty: false }, (row) => {
      const values: string[] = [];
      const width = Math.max(row.cellCount, 1);
      for (let column = 1; column <= width; column += 1) {
        const cell = row.getCell(column);
        const parsed = cellText(cell);
        if (parsed.formula) {
          issues.push(
            problem(
              `Formulas are not supported. Replace the formula in ${worksheet.name}!${cell.address} with a value.`,
              row.number,
              String(column),
            ),
          );
        }
        values.push(parsed.value.trim());
      }
      rows.push(values);
    });
    sheets.push({ name: worksheet.name, table: tableFromRows(rows, issues, worksheet.name) });
  });
  if (sheets.length === 0) {
    throw new ImportFileError([problem("The workbook has no worksheets.")]);
  }
  if (issues.length) throw new ImportFileError(issues);
  return { filename: name, sheets, issues: [] };
}

export function normalizeName(value: string): string {
  return value.normalize("NFKC").trim().replace(/\s+/g, " ").toLocaleLowerCase();
}

export function suggestColumnMapping(
  headers: string[],
  fields: ImportFieldSpec[],
): Record<string, string> {
  const mapping: Record<string, string> = {};
  const used = new Set<string>();
  const normalized = headers.map((header) => ({
    header,
    key: header.trim().toLowerCase().replace(/\s+/g, " "),
  }));
  for (const field of fields) {
    const wanted = [field.label, field.key.replace(/_/g, " "), ...field.aliases].map((value) =>
      value.trim().toLowerCase().replace(/\s+/g, " "),
    );
    const hit = normalized.find(
      (candidate) => !used.has(candidate.header) && wanted.includes(candidate.key),
    );
    if (hit) {
      mapping[field.key] = hit.header;
      used.add(hit.header);
    }
  }
  return mapping;
}

export function buildTemplateCsv(fields: ImportFieldSpec[]): string {
  const headers = fields.map((field) => `${field.label}${field.required ? " *" : ""}`);
  const example = fields.map((field) => {
    if (field.multiple) return "Example A; Example B";
    return field.required ? `Example ${field.label}` : "";
  });
  return serializeCsv(headers, [example]);
}

export function issueReportCsv(issues: ImportIssue[]): string {
  return serializeCsv(
    ["row", "column", "message"],
    issues.map((issue) => [
      String(issue.row),
      JSON.stringify(issue.column),
      JSON.stringify(issue.message),
    ]),
  );
}

export function downloadIssues(issues: ImportIssue[], filename: string): void {
  downloadCsv(issueReportCsv(issues), filename);
}
