import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const styleCss = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), "../style.css"),
  "utf8",
);

function blockFor(css: string, selector: string): string {
  const start = css.indexOf(selector);
  expect(start, `missing selector ${selector}`).toBeGreaterThanOrEqual(0);
  const open = css.indexOf("{", start);
  const close = css.indexOf("}", open);
  return css.slice(open + 1, close);
}

describe("Phase 2 — shell and navigation contracts", () => {
  it("defines global header contracts", () => {
    expect(styleCss).toContain(".workspace-header");
    expect(styleCss).toContain(".workspace-brand-group");
    expect(styleCss).toContain(".workspace-brand");
    expect(styleCss).toContain(".brand-mark");
    expect(styleCss).toContain(".workspace-nav");
    expect(styleCss).toContain(".nav-tab");
    expect(styleCss).toContain(".studio-search");
    expect(styleCss).toContain(".studio-icon-button");
    expect(styleCss).toContain(".studio-share");
    expect(styleCss).toContain(".workspace-account");
    expect(styleCss).toContain(".account-menu");
    expect(styleCss).toContain(".account-avatar");
  });

  it("uses semantic tokens for header surfaces, not fixed colors", () => {
    const header = blockFor(styleCss, ".workspace-header {");
    expect(header).toContain("var(--color-surface)");
    expect(header).toContain("var(--color-border)");
    expect(header).not.toMatch(/#ffffff/);
    expect(header).not.toMatch(/#000000/);
  });

  it("defines workspace selector contracts", () => {
    expect(styleCss).toContain(".workspace-switcher");
    expect(styleCss).toContain(".ws-switcher-trigger");
    expect(styleCss).toContain(".ws-switcher-name");
    expect(styleCss).toContain(".ws-switcher-dropdown");
    expect(styleCss).toContain(".ws-switcher-row");
    expect(styleCss).toContain(".ws-active-dot");
    expect(styleCss).toContain(".ws-demo-badge");
  });

  it("truncates long workspace names with ellipsis", () => {
    const name = blockFor(styleCss, ".ws-switcher-name {");
    expect(name).toContain("overflow: hidden");
    expect(name).toContain("text-overflow: ellipsis");
    expect(name).toContain("white-space: nowrap");
  });

  it("defines architecture top bar contracts", () => {
    expect(styleCss).toContain(".architecture-topbar");
    expect(styleCss).toContain(".studio-state-selector");
    expect(styleCss).toContain(".state-dot");
    expect(styleCss).toContain(".state-type-label");
    expect(styleCss).toContain(".state-readonly-hint");
    expect(styleCss).toContain(".architecture-discipline-tab");
    expect(styleCss).toContain(".architecture-save-status");
  });

  it("distinguishes state types without color alone (text labels)", () => {
    expect(styleCss).toContain(".state-current .state-type-label");
    expect(styleCss).toContain(".state-candidate .state-type-label");
    expect(styleCss).toContain(".state-target .state-type-label");
    expect(styleCss).toContain(".state-readonly-hint");
  });

  it("defines secondary workbench navigation contracts", () => {
    expect(styleCss).toContain(".enterprise-views");
    expect(styleCss).toContain(".information-views");
    expect(styleCss).toContain(".solution-views");
    expect(styleCss).toContain(".integration-views");
  });

  it("defines workbench toolbar contracts", () => {
    expect(styleCss).toContain(".enterprise-toolbar");
    expect(styleCss).toContain(".information-toolbar");
    expect(styleCss).toContain(".solution-toolbar");
    expect(styleCss).toContain(".integration-toolbar");
    expect(styleCss).toContain(".enterprise-title");
    expect(styleCss).toContain(".enterprise-toolbar-hint");
  });

  it("defines Enterprise Objects responsive grid contract", () => {
    expect(styleCss).toContain(".enterprise-objects");
    expect(styleCss).toContain(".enterprise-group");
    expect(styleCss).toContain(".information-section-heading");
    expect(styleCss).toContain(".enterprise-object-grid");
    expect(styleCss).toContain(".enterprise-object-card");
    expect(styleCss).toContain(".item-count");
  });

  it("uses responsive grid with sensible card widths", () => {
    const grid = blockFor(styleCss, ".enterprise-object-grid {");
    expect(grid).toContain("repeat(auto-fill, minmax(");
  });

  it("defines contract workspace shell header", () => {
    expect(styleCss).toContain(".integration-header");
  });

  it("has no fixed-width shell containers that force horizontal scroll", () => {
    // Shell containers should use relative/flex/grid sizing, not fixed widths
    expect(styleCss).not.toMatch(/\.workspace-header\s*\{[^}]*width:\s*\d+px/);
  });
});
