import { describe, expect, it } from "vitest";
import { ContextSaveQueue } from "./contextSaveQueue";

describe("context-owned saves", () => {
  it("serializes writes and waits for work appended during navigation", async () => {
    const queue = new ContextSaveQueue();
    const order: string[] = [];
    let release!: () => void;
    const first = queue.enqueue("candidate-a", async () => {
      await new Promise<void>((resolve) => { release = resolve; });
      order.push("a");
    });
    await Promise.resolve();
    const flushed = queue.flush();
    const second = queue.enqueue("candidate-b", async () => { order.push("b"); });
    expect(queue.pending).toBe(true);
    release();
    await Promise.all([first, second, flushed]);
    expect(order).toEqual(["a", "b"]);
    expect(queue.pending).toBe(false);
  });

  it("blocks navigation after failure without poisoning the queue", async () => {
    const queue = new ContextSaveQueue();
    await expect(queue.enqueue("candidate-a", async () => {
      throw new Error("Workspace not found");
    })).rejects.toThrow("Workspace not found");
    await expect(queue.flush()).rejects.toThrow("Workspace not found");
    await queue.enqueue("candidate-b", async () => {});
    await expect(queue.flush()).rejects.toThrow("Workspace not found");
    await queue.enqueue("candidate-a", async () => {});
    await expect(queue.flush()).resolves.toBeUndefined();
  });
});
