import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

// jsdom does not compute cascade-dependent colours, so the light/dark contract
// is asserted against the stylesheet source instead of getComputedStyle.
// Theme tokens now live in tokens.css; component rules remain in studio.css.
const tokensCss = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), "tokens.css"),
  "utf8",
);
const componentCss = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), "studio.css"),
  "utf8",
);

function declarationBlock(css: string, selector: string): string {
  const start = css.indexOf(selector);
  expect(start, `missing selector ${selector}`).toBeGreaterThanOrEqual(0);
  const open = css.indexOf("{", start);
  const close = css.indexOf("}", open);
  return css.slice(open + 1, close);
}

describe("theme tokens", () => {
  it("defines the semantic warning token in both themes", () => {
    const light = declarationBlock(tokensCss, ":root {");
    const dark = declarationBlock(tokensCss, ':root[data-theme="dark"] {');
    for (const body of [light, dark]) {
      expect(body).toMatch(/--color-warning:\s*#/);
      expect(body).toMatch(/--color-warning-soft:\s*#/);
    }
    // The dark override must differ from the light token so contrast adapts.
    expect(light).not.toBe(dark);
    expect(declarationBlock(tokensCss, ':root[data-theme="dark"] {')).toContain(
      "--color-danger:",
    );
  });

  it("defines the full semantic token set in both themes", () => {
    const light = declarationBlock(tokensCss, ":root {");
    const dark = declarationBlock(tokensCss, ':root[data-theme="dark"] {');
    const required = [
      "--color-app",
      "--color-canvas",
      "--color-surface",
      "--color-surface-muted",
      "--color-surface-elevated",
      "--color-surface-overlay",
      "--color-ink",
      "--color-secondary",
      "--color-muted",
      "--color-inverse",
      "--color-border",
      "--color-border-strong",
      "--color-accent",
      "--color-accent-hover",
      "--color-accent-active",
      "--color-accent-soft",
      "--color-on-accent",
      "--color-selected",
      "--color-hover-state",
      "--color-disabled-bg",
      "--color-disabled-text",
      "--color-focus-ring",
      "--color-info",
      "--color-success",
      "--color-warning",
      "--color-warning-soft",
      "--color-danger",
      "--color-danger-soft",
      "--color-added",
      "--color-changed",
      "--color-removed",
      "--color-reused",
      "--color-draft",
      "--color-validated",
      "--color-approved",
      "--color-applied",
      "--color-undone",
      "--color-healthy",
      "--color-attention",
      "--shadow-1",
      "--shadow-2",
      "--shadow-3",
      "--shadow-panel",
      "--radius-sm",
      "--radius-md",
      "--radius-lg",
      "--radius-full",
      "--space-1",
      "--space-2",
      "--space-3",
      "--space-4",
      "--space-6",
      "--space-8",
    ];
    for (const token of required) {
      expect(light).toContain(token);
      expect(dark).toContain(token);
    }
  });

  it("routes integration status colours through semantic tokens, not fixed hex", () => {
    expect(componentCss).not.toMatch(/#b03a3a/i);
    expect(componentCss).not.toMatch(/#2f7a52/i);
    expect(tokensCss).not.toMatch(/#b03a3a/i);
    expect(tokensCss).not.toMatch(/#2f7a52/i);
    expect(componentCss).toMatch(
      /\.integration-status-built[^{]*\{[^}]*color:\s*var\(--color-healthy\)/,
    );
    expect(componentCss).toMatch(
      /\.integration-status-attention[^{]*\{[^}]*color:\s*var\(--color-danger\)/,
    );
    expect(componentCss).toMatch(
      /\.integration-toolbar-error[^{]*\{[^}]*color:\s*var\(--color-danger\)/,
    );
  });

  it("keeps enterprise primary names on the foreground token, not button on-accent", () => {
    expect(declarationBlock(componentCss, ".enterprise-object-card {")).toContain(
      "color: var(--color-ink)",
    );
    expect(
      declarationBlock(componentCss, ".enterprise-object-card strong {"),
    ).toContain("color: var(--color-ink)");
    expect(
      declarationBlock(componentCss, ".enterprise-capability-name {"),
    ).toContain("color: var(--color-ink)");
    // Owner is secondary metadata, never the primary name colour.
    expect(
      declarationBlock(componentCss, ".enterprise-object-card small {"),
    ).toContain("var(--color-muted)");
  });

  it("keeps the application support toolbar compact and the canvas full height", () => {
    expect(
      declarationBlock(componentCss, ".enterprise-app-support {"),
    ).toMatch(/grid-template-rows:\s*auto minmax\(0,\s*1fr\)/);
  });

  it("preserves React Flow --xy-* token overrides in studio.css", () => {
    expect(componentCss).toContain("--xy-background-color");
    expect(componentCss).toContain("--xy-controls-button-color");
    expect(componentCss).toContain("--xy-minimap-background-color");
    expect(componentCss).toContain("--xy-edge-label-background-color");
  });
});
