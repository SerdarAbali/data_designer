// @vitest-environment jsdom
import ExcelJS from "exceljs";
import { describe, expect, it } from "vitest";

import {
  IMPORT_KIND_FIELDS,
  IMPORT_MAX_ROWS,
  ImportFileError,
  buildTemplateCsv,
  issueReportCsv,
  normalizeName,
  parseCsvTable,
  parseImportFile,
  suggestColumnMapping,
} from "./architectureImport";

const fields = IMPORT_KIND_FIELDS.system;

describe("parseCsvTable", () => {
  it("parses headers and rows and ignores blank lines", () => {
    const table = parseCsvTable("Name,Owner\nBilling,Finance\n\nCRM,Sales\n");
    expect(table.headers).toEqual(["Name", "Owner"]);
    expect(table.rows).toEqual([
      ["Billing", "Finance"],
      ["CRM", "Sales"],
    ]);
  });

  it("rejects formula-like cell values", () => {
    expect(() => parseCsvTable("Name\n=cmd|' /C calc'!A0\n")).toThrow(ImportFileError);
  });

  it("rejects duplicate headers and oversized files", () => {
    expect(() => parseCsvTable("Name,name\nA,B\n")).toThrow(ImportFileError);
    expect(() => parseCsvTable("Name\n" + "x".repeat(1024 * 1024 + 1))).toThrow(ImportFileError);
  });

  it("caps the number of data rows", () => {
    const rows = Array.from({ length: IMPORT_MAX_ROWS + 5 }, (_, index) => `System ${index}`);
    expect(() => parseCsvTable(`Name\n${rows.join("\n")}\n`)).toThrow(ImportFileError);
  });
});

describe("parseImportFile", () => {
  it("parses a CSV file into a single virtual sheet", async () => {
    const file = new File(["Name,External ID\nBilling,SYS-1\n"], "systems.csv", {
      type: "text/csv",
    });
    const workbook = await parseImportFile(file);
    expect(workbook.filename).toBe("systems.csv");
    expect(workbook.sheets).toHaveLength(1);
    expect(workbook.sheets[0].table.rows).toEqual([["Billing", "SYS-1"]]);
  });

  it("parses every worksheet of an xlsx workbook", async () => {
    const workbook = new ExcelJS.Workbook();
    const systems = workbook.addWorksheet("Systems");
    systems.addRow(["Name", "Owner"]);
    systems.addRow(["Billing", "Finance"]);
    const info = workbook.addWorksheet("Information");
    info.addRow(["Name", "Owner"]);
    info.addRow(["Customer", "Data Office"]);
    const buffer = await workbook.xlsx.writeBuffer();
    const file = new File([buffer], "architecture.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });

    const parsed = await parseImportFile(file);
    expect(parsed.sheets.map((sheet) => sheet.name)).toEqual(["Systems", "Information"]);
    expect(parsed.sheets[0].table.rows).toEqual([["Billing", "Finance"]]);
    expect(parsed.sheets[1].table.rows).toEqual([["Customer", "Data Office"]]);
  });

  it("rejects unsupported extensions", async () => {
    const file = new File(["Name\nBilling\n"], "systems.xls", { type: "application/vnd.ms-excel" });
    await expect(parseImportFile(file)).rejects.toThrow(ImportFileError);
  });
});

describe("column mapping and helpers", () => {
  it("suggests mappings from labels and synonyms without reusing a column", () => {
    const mapping = suggestColumnMapping(
      ["System Name", "Source ID", "Alternative Names", "Business Area"],
      fields,
    );
    expect(mapping).toEqual({
      name: "System Name",
      external_id: "Source ID",
      aliases: "Alternative Names",
      business_domain: "Business Area",
    });
  });

  it("normalizes names case- and whitespace-insensitively", () => {
    expect(normalizeName("  Payments   Hub ")).toBe("payments hub");
    expect(normalizeName("PAYMENTS HUB")).toBe("payments hub");
  });

  it("builds a template that parses back with the same headers", () => {
    const template = buildTemplateCsv(fields);
    const table = parseCsvTable(template);
    expect(table.headers[0]).toBe("Name *");
    expect(table.headers).toContain("External ID");
  });

  it("serializes an issue report that keeps user text out of formula positions", () => {
    const report = issueReportCsv([{ row: 2, column: "Name", message: "=SUM(A1:A2)" }]);
    const table = parseCsvTable(report);
    expect(table.headers).toEqual(["row", "column", "message"]);
    expect(table.rows[0][0]).toBe("2");
    expect(table.rows[0][2]).toContain("SUM(A1:A2)");
  });
});
