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

describe("shared component contracts", () => {
  const contracts = [
    ".btn",
    ".btn--primary",
    ".btn--secondary",
    ".btn--tertiary",
    ".btn--danger",
    ".btn--quiet",
    ".btn--icon",
    ".btn--loading",
    ".input",
    "textarea.input",
    ".checkbox",
    ".tabs",
    ".tab",
    ".segmented-control",
    ".segmented-control-item",
    ".badge",
    ".badge--success",
    ".badge--warning",
    ".badge--danger",
    ".badge--draft",
    ".badge--validated",
    ".badge--approved",
    ".badge--applied",
    ".badge--undone",
    ".badge--added",
    ".badge--changed",
    ".badge--removed",
    ".badge--reused",
    ".card",
    ".card--compact",
    ".card--elevated",
    ".panel",
    ".panel--elevated",
    ".toolbar",
    ".dialog",
    ".dialog::backdrop",
    ".dialog-header",
    ".dialog-actions",
    ".dialog-close",
    ".tooltip",
    ".loading",
    ".loading--page",
    ".empty-state",
    ".empty-state--page",
    ".empty-icon",
    ".error-banner",
    ".warning-banner",
    ".info-banner",
  ];

  it("defines every shared component contract", () => {
    for (const selector of contracts) {
      expect(styleCss).toContain(selector);
    }
  });

  it("defines the .primary-button compatibility alias", () => {
    expect(styleCss).toContain(".primary-button");
  });

  it("uses token values, not fixed foreground colors, in button variants", () => {
    const primary = blockFor(styleCss, ".btn--primary {");
    expect(primary).toContain("var(--color-accent)");
    expect(primary).toContain("var(--color-on-accent)");
    const danger = blockFor(styleCss, ".btn--danger {");
    expect(danger).toContain("var(--color-danger)");
  });

  it("scopes h1 to .page so diagram metadata is not affected", () => {
    expect(styleCss).toContain(".page h1");
    expect(styleCss).not.toMatch(/^h1\s*\{/m);
  });

  it("defines badge status modifiers without color-only meaning", () => {
    const badge = blockFor(styleCss, ".badge {");
    expect(badge).not.toContain("!important");
    expect(badge).toContain("var(--color-secondary)");
    for (const status of [
      "info", "success", "warning", "danger", "draft", "validated",
      "approved", "applied", "undone", "added", "changed", "removed", "reused",
    ]) {
      expect(styleCss).toContain(`.badge--${status}`);
    }
  });
});

describe("global defect fixes", () => {
  it("removes near-white workspace-header background", () => {
    expect(styleCss).not.toContain("rgb(255 255 255 / 94%)");
  });

  it("removes near-white data-preview-drawer background", () => {
    expect(styleCss).not.toContain("rgb(255 255 255 / 97%)");
  });

  it("removes parent opacity from .import-steps", () => {
    const steps = blockFor(styleCss, ".import-dialog .import-steps {");
    expect(steps).not.toContain("opacity: 0.7");
  });

  it("has a single authoritative focus-visible rule in style.css", () => {
    const matches = styleCss.match(/^button:focus-visible/m);
    expect(matches).not.toBeNull();
    const allMatches = styleCss.match(/^button:focus-visible/gm);
    expect(allMatches).toHaveLength(1);
  });

  it("does not redeclare global button:disabled in studio.css", () => {
    const studioCss = readFileSync(
      resolve(dirname(fileURLToPath(import.meta.url)), "studio.css"),
      "utf8",
    );
    const globalDisabled = studioCss.match(/^button:disabled/m);
    expect(globalDisabled).toBeNull();
  });

  it("defines semantic tokens in tokens.css only, not studio.css", () => {
    const studioCss = readFileSync(
      resolve(dirname(fileURLToPath(import.meta.url)), "studio.css"),
      "utf8",
    );
    const lines = studioCss.split("\n");
    let inRoot = false;
    for (const line of lines) {
      if (line.startsWith(":root") || line.startsWith(":root[")) {
        inRoot = true;
        continue;
      }
      if (inRoot && line.startsWith("}")) {
        inRoot = false;
        continue;
      }
      if (inRoot && line.match(/^--/)) {
        // eslint-disable-next-line no-console
        console.error(
          `Unexpected token declaration in studio.css: ${line.trim()}`,
        );
        throw new Error(
          `studio.css should not redeclare theme tokens: ${line.trim()}`,
        );
      }
    }
  });

  it("preserves React Flow --xy-* variables in studio.css", () => {
    const studioCss = readFileSync(
      resolve(dirname(fileURLToPath(import.meta.url)), "studio.css"),
      "utf8",
    );
    expect(studioCss).toContain("--xy-background-color");
    expect(studioCss).toContain("--xy-controls-button-color");
    expect(studioCss).toContain("--xy-minimap-background-color");
    expect(studioCss).toContain("--xy-edge-label-background-color");
  });
});
