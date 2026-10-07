import { describe, expect, it } from "vitest";
import { sampleScenario, scenarioTestIndex } from "./scenarioTestFixtures";
import { layoutSequence, SEQUENCE_METRICS } from "./scenarioSequenceLayout";

describe("sequence layout", () => {
  it("places lifelines, messages, return arrows and self-calls", async () => {
    const index = await scenarioTestIndex();
    const layout = layoutSequence(sampleScenario(), index, new Map([["s1", "ok"]]));
    expect(layout.lifelines.map((item) => item.label)).toEqual(["Sales rep", "CRM", "ERP", "WMS"]);
    const xs = layout.lifelines.map((item) => item.x);
    expect(xs[1]! - xs[0]!).toBe(SEQUENCE_METRICS.lifelineGap);

    const byId = new Map(layout.messages.map((item) => [item.stepId, item]));
    expect(byId.get("s1")).toMatchObject({
      fromX: xs[1], toX: xs[2], dashed: false, label: "Customer push · Request", outcome: "ok", phase: "request",
    });
    expect(byId.get("s2")).toMatchObject({ fromX: xs[2], toX: xs[1], dashed: true, label: "Customer push · Success response" });
    expect(byId.get("s4")).toMatchObject({ self: true, fromX: xs[1], toX: xs[1], contractId: null });
    const ys = layout.messages.map((item) => item.y);
    expect([...ys].sort((a, b) => a - b)).toEqual(ys);
  });

  it("frames alt/opt/loop blocks around their messages with guards", async () => {
    const index = await scenarioTestIndex();
    const layout = layoutSequence(sampleScenario(), index);
    const alt = layout.fragments.find((item) => item.id === "f1")!;
    const loop = layout.fragments.find((item) => item.id === "f2")!;
    expect(alt.operands.map((item) => item.guard)).toEqual(["accepted", "rejected"]);
    const s4 = layout.messages.find((item) => item.stepId === "s4")!;
    expect(s4.y).toBeGreaterThan(alt.y);
    expect(s4.y).toBeLessThan(alt.y + alt.height);
    expect(alt.x).toBeLessThan(layout.lifelines[1]!.x);
    expect(alt.x + alt.width).toBeGreaterThan(layout.lifelines[2]!.x);
    expect(loop.y).toBeGreaterThanOrEqual(alt.y + alt.height);
    expect(loop.x).toBeGreaterThan(layout.lifelines[1]!.x);
  });

  it("nests inner frames inside outer frames", async () => {
    const index = await scenarioTestIndex();
    const document = sampleScenario();
    document.items = [{
      kind: "opt",
      id: "outer",
      operands: [{ guard: "outer", items: [document.items[2]!] }],
    }];
    const layout = layoutSequence(document, index);
    const outer = layout.fragments.find((item) => item.id === "outer")!;
    const inner = layout.fragments.find((item) => item.id === "f1")!;
    expect(outer.x).toBeLessThan(inner.x);
    expect(outer.x + outer.width).toBeGreaterThan(inner.x + inner.width);
    expect(outer.y).toBeLessThan(inner.y);
    expect(outer.y + outer.height).toBeGreaterThan(inner.y + inner.height);
    expect(layout.fragments[0]!.id).toBe("outer");
  });

  it("marks messages for missing contracts", async () => {
    const index = await scenarioTestIndex();
    const document = sampleScenario();
    document.items = [{ kind: "contract", id: "gone", contractId: "missing", phase: "request" }];
    const layout = layoutSequence(document, index);
    expect(layout.messages[0]).toMatchObject({ missing: "Contract is missing or archived", label: "Missing contract · Request" });
  });
});
