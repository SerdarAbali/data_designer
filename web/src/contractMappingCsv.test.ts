import { describe, expect, it } from "vitest";
import type { GraphDocument, GraphNodeDocument } from "./contractGraphTypes";
import {
  CSV_COLUMNS, CSV_MAX_BYTES, CSV_MAX_ROWS, MappingCsvError, buildCsvProposal,
  exportMappingCsv, graphLimitIssues, isFormulaLike, issueReportCsv, parseMappingCsv,
  serializeCsv, suggestColumns, templateMappingCsv, type CsvField,
} from "./contractMappingCsv";

const senders: CsvField[] = [
  { id: "s1", name: "Customer ID", data_type: "string" },
  { id: "s2", name: "phone number", data_type: "string" },
];
const receivers: CsvField[] = [
  { id: "t1", name: "Customer ID", data_type: "string" },
  { id: "t2", name: "CustNo", data_type: "integer", required: true },
];
const endpoint = (id: string, type: "source" | "target"): GraphNodeDocument =>
  ({ id, type, config: {}, position: { x: type === "source" ? 80 : 700, y: 100 } });
const empty = (): GraphDocument => ({
  version: 1, nodes: [endpoint("src", "source"), endpoint("dst", "target")], edges: [],
});
const direct = (): GraphDocument => ({
  ...empty(), edges: [{
    id: "edge1", sourceNodeId: "src", sourcePortId: "field:s1",
    targetNodeId: "dst", targetPortId: "field:t1",
  }],
});
const fx = (config: Record<string, unknown> = { function: "toInt", errorPolicy: "skip" }): GraphDocument => ({
  version: 1,
  nodes: [...empty().nodes, { id: "fx1", type: "fx", position: { x: 300, y: 120 }, config }],
  edges: [
    { id: "e1", sourceNodeId: "src", sourcePortId: "field:s2", targetNodeId: "fx1", targetPortId: "input" },
    { id: "e2", sourceNodeId: "fx1", sourcePortId: "output", targetNodeId: "dst", targetPortId: "field:t2" },
  ],
});
const csv = (rows: string[][]) => serializeCsv(CSV_COLUMNS, rows);
const record = (source = "Customer ID", target = "Customer ID", transform = "") =>
  ["1", source, target, transform, "", "", "", ""];
function propose(text: string, graph = empty(), options: Partial<Parameters<typeof buildCsvProposal>[0]> = {}) {
  const table = parseMappingCsv(text);
  let id = 0;
  return buildCsvProposal({
    table, columns: suggestColumns(table.headers), graph,
    senderFields: senders, receiverFields: receivers, mode: "add",
    newId: () => `new-${++id}`, ...options,
  });
}

describe("CSV parser and safety", () => {
  it("round trips quoted commas, quotes, multiline cells, Unicode, and BOM", () => {
    const value = 'Name, "quoted"\nİstanbul';
    const text = serializeCsv(["field", "other"], [[value, "00123"]]);
    expect(text.startsWith("\uFEFF")).toBe(true);
    expect(text).toContain("\r\n");
    expect(parseMappingCsv(text).rows).toEqual([[value, "00123"]]);
    expect(parseMappingCsv(text.slice(1).replace(/\r\n/g, "\n")).rows).toEqual([[value, "00123"]]);
  });
  it.each([";", "\t"])("detects %j delimiters", (delimiter) => {
    const table = parseMappingCsv(`source_field${delimiter}target_field\nfoo${delimiter}bar`);
    expect(table.delimiter).toBe(delimiter);
    expect(table.rows).toEqual([["foo", "bar"]]);
  });
  it("supports manual delimiter override", () => {
    expect(parseMappingCsv("one;two\nvalue;other", ";").headers).toEqual(["one", "two"]);
  });
  it.each(["", "\uFEFF\n", 'a,a\n1,2', 'a,\n1,2', 'a,b\n"broken,cell', "a,b\n1,2,3"])(
    "rejects empty or malformed CSV %j", (text) => {
      expect(() => parseMappingCsv(text)).toThrow(MappingCsvError);
    },
  );
  it("accepts headers-only export", () => {
    expect(parseMappingCsv(csv([])).rows).toEqual([]);
    expect(exportMappingCsv(empty(), senders, receivers)).toBe(csv([]));
  });
  it("enforces the exact UTF-8 upload boundary", () => {
    const atLimit = "a,b\n" + "x".repeat(CSV_MAX_BYTES - 6) + ",y";
    expect(new TextEncoder().encode(atLimit).length).toBe(CSV_MAX_BYTES);
    expect(parseMappingCsv(atLimit).rows).toHaveLength(1);
    expect(() => parseMappingCsv(atLimit + "x")).toThrow("1 MiB");
  });
  it("enforces 500 logical rows, not physical lines", () => {
    const atLimit = csv(Array.from({ length: CSV_MAX_ROWS }, () => record("multi\nline")));
    expect(parseMappingCsv(atLimit).rows).toHaveLength(CSV_MAX_ROWS);
    expect(() => parseMappingCsv(csv(Array.from({ length: CSV_MAX_ROWS + 1 }, () => record()))))
      .toThrow("500 mapping rows");
  });
  it.each(["=1+1", "+command", "-command", "@SUM(1)", " \t=1", "\nplain", "＝1", " ＋foo", "\u0000@foo"])(
    "rejects formula-like cells %j", (value) => {
      expect(isFormulaLike(value)).toBe(true);
      expect(() => serializeCsv(["field"], [[value]])).toThrow("Formula-like");
      const imported = `format_version,source_field,target_field\n1,"${value}",Customer ID`;
      expect(propose(imported).graph).toBeNull();
    },
  );
  it("does not confuse quoted text and plain values with formulas", () => {
    expect(isFormulaLike('"=value"')).toBe(false);
    expect(isFormulaLike("field-name")).toBe(false);
    expect(isFormulaLike("O'Brien")).toBe(false);
  });
  it("can safely download an issue report containing untrusted header text", () => {
    const report = issueReportCsv([{ row: 2, column: "=formula", message: "@unsafe" }]);
    expect(parseMappingCsv(report).rows[0]).toEqual(["2", '"=formula"', '"@unsafe"']);
  });
});

describe("mapping CSV proposals", () => {
  it("round trips direct and single-conversion mapping semantics", () => {
    for (const graph of [direct(), fx(), fx({
      function: "date", errorPolicy: "fail", inputFormat: "%Y,%m\n%d",
      outputFormat: "%d/%m/%Y", countryCallingCode: "358",
    })]) {
      const text = exportMappingCsv(graph, senders, receivers);
      const result = propose(text);
      expect(result.issues).toEqual([]);
      expect(result.graph).not.toBeNull();
      expect(exportMappingCsv(result.graph!, senders, receivers)).toBe(text);
    }
  });
  it("treats repeated imports as unchanged even with regenerated IDs and default policies", () => {
    const text = exportMappingCsv(fx({ function: "toInt" }), senders, receivers);
    const result = propose(text, fx());
    expect(result.rows[0].action).toBe("conflict");
    const first = propose(text);
    const again = propose(text, first.graph!);
    expect(again.rows[0].action).toBe("unchanged");
    expect(again.graph).toEqual(first.graph);
  });
  it("add-only blocks conflicts without mutating the graph; replace touches only listed targets", () => {
    const graph = { ...direct(), nodes: fx().nodes, edges: [...direct().edges, ...fx().edges] };
    const before = structuredClone(graph);
    const text = csv([record("phone number", "Customer ID")]);
    expect(propose(text, graph).graph).toBeNull();
    const result = propose(text, graph, { mode: "replace" });
    expect(result.rows[0].action).toBe("replace");
    expect(result.graph?.edges.filter((edge) => edge.id === "e1" || edge.id === "e2")).toEqual(fx().edges);
    expect(graph).toEqual(before);
  });
  it("does not partially apply valid rows mixed with invalid ones", () => {
    const graph = empty();
    const result = propose(csv([record(), record("missing", "CustNo")]), graph);
    expect(result.rows[0].action).toBe("add");
    expect(result.graph).toBeNull();
    expect(graph.edges).toEqual([]);
  });
  it("resolves missing/ambiguous names only through explicit current field selection", () => {
    const fields = [...senders, { ...senders[0], id: "s3" }];
    const text = csv([record()]);
    expect(propose(text, empty(), { senderFields: fields }).issues[0].message).toContain("ambiguous");
    expect(propose(text, empty(), {
      senderFields: fields, fieldSelections: { "2:source_field": "s3" },
    }).graph?.edges[0].sourcePortId).toBe("field:s3");
    expect(propose(text, empty(), { fieldSelections: { "2:source_field": "archived" } }).graph).toBeNull();
  });
  it("resolves response-direction fields from the supplied active phase, never request fields", () => {
    const result = propose(csv([record("CustNo", "phone number", "toString")]), empty(), {
      senderFields: receivers, receiverFields: senders,
    });
    expect(result.graph?.edges[0].sourcePortId).toBe("field:t2");
    expect(result.graph?.edges[1].targetPortId).toBe("field:s2");
    expect(propose(csv([record("CustNo", "phone number")])).graph).toBeNull();
  });
  it("blocks duplicate target assignments, invalid versions, functions, and settings", () => {
    const badRows = [
      [record(), record()],
      [["2", ...record().slice(1)]],
      [record("Customer ID", "CustNo", "arbitraryCode")],
      [["1", "Customer ID", "CustNo", "toInt", "default", "", "", ""]],
      [record("Customer ID", "CustNo", "parseDate")],
      [["1", "Customer ID", "CustNo", "e164", "fail", "", "", "0358"]],
      [["1", "Customer ID", "CustNo", "", "skip", "", "", ""]],
    ];
    for (const rows of badRows) expect(propose(csv(rows)).graph).toBeNull();
  });
  it("requires column mapping and refuses silently dropped nonempty columns", () => {
    const text = "Version,Sender,Receiver,secret\n1,Customer ID,Customer ID,unknown";
    const result = propose(text, empty(), { columns: { format_version: 0, source_field: 1, target_field: 2 } });
    expect(result.issues[0].message).toContain("Unrecognized");
    expect(propose(csv([record()]), empty(), { columns: {} }).graph).toBeNull();
    expect(propose(csv([record()]), empty(), {
      columns: { format_version: 0, source_field: 1, target_field: 1 },
    }).graph).toBeNull();
  });
  it("blocks direct type mismatches as the Save API does", () => {
    const result = propose(csv([record("Customer ID", "CustNo")]));
    expect(result.graph).toBeNull();
    expect(result.rows[0].issues[0].message).toContain("identical catalog data types");
  });
  it("keeps transformation type diagnostics visible without changing existing draft-save behavior", () => {
    const result = propose(csv([record("Customer ID", "CustNo", "trim")]));
    expect(result.graph).not.toBeNull();
    expect(result.rows[0].warning).toContain("Error");
  });
  it("creates fresh endpoints for an empty graph and leaves input immutable", () => {
    const graph: GraphDocument = { version: 1, nodes: [], edges: [] };
    const result = propose(csv([record()]), graph);
    expect(result.graph?.nodes.map((node) => node.type)).toEqual(["source", "target"]);
    expect(graph.nodes).toEqual([]);
  });
});

describe("unsupported graph export and safe replacement", () => {
  it.each([
    { function: "toInt", errorPolicy: "default", defaultValue: 0 },
    { function: "unknown" },
    { function: "trim", inputFormat: "" },
    { function: "trim", errorPolicy: "" },
    { function: "trim", arbitrary: "setting" },
  ])("rejects unrepresentable settings %j", (config) => {
    expect(() => exportMappingCsv(fx(config), senders, receivers)).toThrow(MappingCsvError);
  });
  it("blocks shared transforms, multi-step chains, disconnected nodes, and constants", () => {
    const shared = fx();
    shared.edges.push({ id: "e3", sourceNodeId: "fx1", sourcePortId: "output", targetNodeId: "dst", targetPortId: "field:t1" });
    const chain = fx();
    chain.nodes.push({ ...chain.nodes[2], id: "fx2" });
    chain.edges[1].sourceNodeId = "fx2";
    chain.edges.push({ id: "e3", sourceNodeId: "fx1", sourcePortId: "output", targetNodeId: "fx2", targetPortId: "input" });
    const disconnected = direct();
    disconnected.nodes.push({ ...fx().nodes[2] });
    const constant = fx();
    constant.nodes[2].type = "constant";
    constant.nodes[2].config = { value: 1 };
    constant.edges.shift();
    for (const graph of [shared, chain, disconnected, constant]) {
      expect(() => exportMappingCsv(graph, senders, receivers)).toThrow(MappingCsvError);
    }
    const replacement = propose(csv([record("Customer ID", "CustNo", "toInt")]), shared, { mode: "replace" });
    expect(replacement.graph).toBeNull();
    expect(replacement.issues[0].message).toContain("advanced/shared");
  });
  it("blocks invalid ports and missing fields rather than exporting a convenient subset", () => {
    const graph = direct();
    graph.edges[0].sourcePortId = "field:missing";
    expect(() => exportMappingCsv(graph, senders, receivers)).toThrow(MappingCsvError);
    expect(() => exportMappingCsv(direct(), [...senders, { ...senders[0], id: "duplicate" }], receivers))
      .toThrow("unique");
  });
  it("preserves unrelated advanced mappings when adding a new target", () => {
    const graph = fx({ function: "trim", errorPolicy: "default", defaultValue: "safe" });
    const result = propose(csv([record()]), graph);
    expect(result.graph?.nodes.find((node) => node.id === "fx1")).toEqual(graph.nodes[2]);
    expect(result.graph?.edges.slice(0, 2)).toEqual(graph.edges);
  });
  it("only templates compatible current fields; an empty schema gets headers, not fake mappings", () => {
    expect(parseMappingCsv(templateMappingCsv(senders, receivers)).rows[0].slice(0, 3))
      .toEqual(["1", "Customer ID", "Customer ID"]);
    expect(parseMappingCsv(templateMappingCsv([], receivers)).rows).toEqual([]);
  });
});

describe("existing graph limits", () => {
  it("checks exactly 200 nodes and 500 edges and one beyond each", () => {
    const graph = empty();
    graph.nodes = Array.from({ length: 200 }, (_, i) => ({ ...endpoint(`node-${i}`, "source") }));
    graph.edges = Array.from({ length: 500 }, (_, i) => ({ ...direct().edges[0], id: `edge-${i}` }));
    expect(graphLimitIssues(graph)).toEqual([]);
    expect(graphLimitIssues({ ...graph, nodes: [...graph.nodes, endpoint("extra", "target")] })[0].message)
      .toContain("200 nodes");
    expect(graphLimitIssues({ ...graph, edges: [...graph.edges, direct().edges[0]] })[0].message)
      .toContain("500 edges");
  });
  it("matches the server's ASCII-escaped 8 KiB config limit, including Unicode", () => {
    const graph = fx();
    graph.nodes[2].config = { value: "x".repeat(8180) };
    expect(graphLimitIssues(graph)).toEqual([]);
    graph.nodes[2].config = { value: "x".repeat(8181) };
    expect(graphLimitIssues(graph)[0].message).toContain("8 KiB");
    graph.nodes[2].config = { value: "😀".repeat(700) };
    expect(graphLimitIssues(graph)[0].message).toContain("8 KiB");
  });
  it("checks exactly 256 KiB of graph JSON and one byte beyond", () => {
    const graph = empty();
    graph.nodes[0].id = "x".repeat(262144 - JSON.stringify(graph).length + graph.nodes[0].id.length);
    expect(new TextEncoder().encode(JSON.stringify(graph)).length).toBe(262144);
    expect(graphLimitIssues(graph)).toEqual([]);
    graph.nodes[0].id += "x";
    expect(graphLimitIssues(graph)[0].message).toContain("256 KiB");
  });
  it("includes preexisting mappings when enforcing the resulting graph limit", () => {
    const graph = empty();
    graph.edges = Array.from({ length: 500 }, (_, i) => ({
      ...direct().edges[0], id: `e${i}`, targetPortId: `field:other-${i}`,
    }));
    expect(propose(csv([record()]), graph).issues.some((issue) => issue.message.includes("500 edges"))).toBe(true);
  });
});
