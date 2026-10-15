// Generates fixtures/architecture-import/systems.xlsx from systems.csv so the
// guided import can be demonstrated with a real Excel workbook.
// Usage: node fixtures/architecture-import/make-sample-xlsx.mjs
import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import ExcelJS from "../../web/node_modules/exceljs/excel.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const csv = await readFile(path.join(here, "systems.csv"), "utf8");

function parseCsv(text) {
  return text
    .trim()
    .split("\n")
    .map((line) => line.split(","));
}

const [headers, ...rows] = parseCsv(csv);
const workbook = new ExcelJS.Workbook();
const sheet = workbook.addWorksheet("Systems");
sheet.addRow(headers);
for (const row of rows) sheet.addRow(row);
await writeFile(path.join(here, "systems.xlsx"), Buffer.from(await workbook.xlsx.writeBuffer()));
console.log(`Wrote systems.xlsx with ${rows.length} data rows.`);
