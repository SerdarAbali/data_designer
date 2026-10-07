import { describe, expect, it } from "vitest";
import { sampleScenario, scenarioTestIndex } from "./scenarioTestFixtures";
import {
  deriveLifelines,
  detectMissingReferences,
  duplicateScenarioDocument,
  flattenSteps,
  insertAfter,
  isFragment,
  moveItem,
  parseSampleInput,
  removeItem,
  resolveStep,
  unwrapFragment,
  wrapItem,
  type ScenarioStep,
} from "./scenarioModel";

describe("scenario model", () => {
  it("derives contract step endpoints from the contract and adds implicit lifelines", async () => {
    const index = await scenarioTestIndex();
    const document = sampleScenario();
    const lifelines = deriveLifelines(document, index);
    expect(lifelines.map((item) => item.label)).toEqual(["Sales rep", "CRM", "ERP", "WMS"]);
    expect(lifelines.slice(2).every((item) => item.implicit)).toBe(true);

    const steps = flattenSteps(document.items);
    const error = resolveStep(steps.find((item) => item.step.id === "s3")!.step, lifelines, index);
    expect(error.fromLifelineId).toBe(lifelines[2]!.id);
    expect(error.toLifelineId).toBe("crm");
    expect(error.endpoints?.senderObjectId).toBe("erp-error");
  });

  it("numbers nested steps in document order", () => {
    const steps = flattenSteps(sampleScenario().items);
    expect(steps.map((item) => [item.step.id, item.number, item.depth])).toEqual([
      ["s0", "1", 0], ["s1", "2", 0], ["s2", "3", 1], ["s3", "4", 1], ["s4", "5", 1], ["s5", "6", 1],
    ]);
  });

  it("reorders within a sibling list and inserts after an item", () => {
    const items = sampleScenario().items;
    expect(moveItem(items, "s1", -1).map((item) => item.id)).toEqual(["s1", "s0", "f1", "f2"]);
    expect(moveItem(items, "s0", -1)).toEqual(items);
    const moved = moveItem(items, "s4", -1);
    const operand = (moved[2] as Extract<typeof moved[number], { operands: unknown }>).operands[1]!;
    expect(operand.items.map((item) => item.id)).toEqual(["s4", "s3"]);
    const step: ScenarioStep = { kind: "self", id: "new", fromParticipantId: "crm", label: "x" };
    expect(flattenSteps(insertAfter(items, "s3", step)).map((item) => item.step.id)).toEqual([
      "s0", "s1", "s2", "s3", "new", "s4", "s5",
    ]);
    expect(flattenSteps(removeItem(items, "s3")).map((item) => item.step.id)).not.toContain("s3");
  });

  it("wraps and unwraps blocks", () => {
    const wrapped = wrapItem(sampleScenario().items, "s1", "opt");
    expect(isFragment(wrapped[1]!)).toBe(true);
    const alt = wrapItem(sampleScenario().items, "s0", "alt");
    expect(isFragment(alt[0]!) && alt[0].operands).toHaveLength(2);
    const unwrapped = unwrapFragment(wrapped, wrapped[1]!.id);
    expect(unwrapped.map((item) => item.id)).toEqual(["s0", "s1", "f1", "f2"]);
  });

  it("duplicates with fresh IDs and remapped assertion references", () => {
    const original = sampleScenario();
    const copy = duplicateScenarioDocument(original);
    const originalIds = flattenSteps(original.items).map((item) => item.step.id);
    const copyIds = flattenSteps(copy.items).map((item) => item.step.id);
    expect(copyIds.some((id) => originalIds.includes(id))).toBe(false);
    expect(copy.assertions[0]!.stepId).toBe(copyIds[1]);
    expect(original.items[0]!.id).toBe("s0");
  });

  it("detects missing contracts, unconfigured phases, and stale fields", async () => {
    const index = await scenarioTestIndex();
    const document = sampleScenario();
    expect(detectMissingReferences(document, index)).toEqual([]);
    document.items.push(
      { kind: "contract", id: "x1", contractId: "gone", phase: "request" },
      { kind: "contract", id: "x2", contractId: "c-site", phase: "success-response" },
      { kind: "contract", id: "x3", contractId: "c-push", phase: "request", sampleValues: { "f-erp-code": 1 } },
    );
    const issues = detectMissingReferences(document, index);
    expect(issues.map((item) => item.stepId)).toEqual(["x1", "x2", "x3"]);
  });

  it("parses sample inputs as JSON literals when possible", () => {
    expect(parseSampleInput("42")).toBe(42);
    expect(parseSampleInput("true")).toBe(true);
    expect(parseSampleInput("{\"a\":1}")).toEqual({ a: 1 });
    expect(parseSampleInput("hello")).toBe("hello");
    expect(parseSampleInput("{bad")).toBe("{bad");
  });
});
