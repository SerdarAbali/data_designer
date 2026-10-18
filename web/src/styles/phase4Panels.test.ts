import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const styleCss = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), "../style.css"),
  "utf8",
);
const assistantCss = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), "../assistant/assistant.css"),
  "utf8",
);

function blockFor(css: string, selector: string): string {
  const start = css.indexOf(selector);
  expect(start, `missing selector ${selector}`).toBeGreaterThanOrEqual(0);
  const open = css.indexOf("{", start);
  const close = css.indexOf("}", open);
  return css.slice(open + 1, close);
}

describe("Phase 4 — shared side-panel contract", () => {
  it("defines the shared side-panel classes", () => {
    for (const selector of [
      ".side-panel",
      ".side-panel-header",
      ".side-panel-heading",
      ".side-panel-title",
      ".side-panel-context",
      ".side-panel-id",
      ".side-panel-controls",
      ".side-panel-tabs",
      ".side-panel-scroll",
      ".side-panel-actions",
      ".side-panel-footer",
    ]) {
      expect(styleCss).toContain(selector);
    }
  });

  it("keeps headers sticky and body scrolling local", () => {
    expect(blockFor(styleCss, ".side-panel-header {")).toContain("position: sticky");
    const scroll = blockFor(styleCss, ".side-panel-scroll {");
    expect(scroll).toContain("overflow-y: auto");
    expect(scroll).toContain("min-height: 0");
  });

  it("overlays panels at narrow widths", () => {
    expect(styleCss).toMatch(/@media \(max-width: 900px\)[\s\S]*\.side-panel \{/);
  });

  it("uses semantic tokens only", () => {
    const panel = blockFor(styleCss, ".side-panel {");
    expect(panel).toContain("var(--color-surface)");
    expect(panel).toContain("var(--color-ink)");
    expect(panel).not.toMatch(/#fff/i);
    expect(panel).not.toMatch(/#000/i);
  });

  it("defines inspector manage-menu and field patterns", () => {
    for (const selector of [
      ".inspector-section",
      ".inspector-field-label",
      ".inspector-field-help",
      ".inspector-readonly-value",
      ".inspector-code",
      ".inspector-advanced",
      ".inspector-relationship-list",
      ".inspector-empty",
      ".inspector-manage-menu",
      ".inspector-manage-trigger",
      ".inspector-form-actions",
    ]) {
      expect(styleCss).toContain(selector);
    }
  });

  it("defines semantic status badges with text, not color alone", () => {
    expect(styleCss).toContain(".status-badge");
    expect(styleCss).toContain('.status-badge[data-tone="success"]');
    expect(styleCss).toContain('.status-badge[data-tone="danger"]');
  });
});

describe("Phase 4 — assistant and proposal layout", () => {
  it("uses the side-panel scroll and sticky composer structure", () => {
    expect(blockFor(assistantCss, ".assistant-panel {")).toContain("overflow: hidden");
    expect(blockFor(assistantCss, ".assistant-panel-scroll {")).toContain("overflow-y: auto");
    const composer = blockFor(assistantCss, ".assistant-composer {");
    expect(composer).toContain("flex-shrink: 0");
    expect(composer).toContain("border-top");
  });

  it("defines collapsible context and tool activity", () => {
    expect(assistantCss).toContain(".assistant-context");
    expect(assistantCss).toContain(".assistant-context-summary");
    expect(assistantCss).toContain(".assistant-tools > ul");
    expect(assistantCss).toContain(".assistant-tools li > details > summary");
  });

  it("defines progressive proposal sections and summary grid", () => {
    expect(assistantCss).toContain(".proposal-summary-grid");
    expect(assistantCss).toContain(".proposal-section");
    expect(assistantCss).toContain(".proposal-section[open] > summary");
  });

  it("distinguishes reused and proposed objects with text", () => {
    expect(assistantCss).toContain('li[data-badge="reused"]::before');
    expect(assistantCss).toContain('li[data-badge="added"]::before');
  });
});
