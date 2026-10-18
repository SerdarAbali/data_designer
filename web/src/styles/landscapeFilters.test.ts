import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

// jsdom does not compute the cascade, so the light/dark and responsive contracts
// for the Landscape filter bar are asserted against the stylesheet source.
const sourceDir = dirname(fileURLToPath(import.meta.url));
const componentCss = readFileSync(resolve(sourceDir, "..", "style.css"), "utf8");

function landscapeFilterCss(): string {
  const start = componentCss.indexOf("--- Integration Landscape filters");
  expect(start).toBeGreaterThanOrEqual(0);
  return componentCss.slice(start);
}

describe("landscape filter styles", () => {
  const css = landscapeFilterCss();

  it("drives every colour from theme tokens so light and dark both stay valid", () => {
    const declarations = css.match(/(?:color|background|border(?:-[a-z]+)?):[^;]+;/g) ?? [];
    expect(declarations.length).toBeGreaterThan(10);
    const hardCoded = declarations.filter((entry) => /#[0-9a-f]{3,8}\b|rgb\(/i.test(entry));
    expect(hardCoded).toEqual([]);
    for (const token of ["--color-surface", "--color-ink", "--color-border", "--color-muted"]) {
      expect(css).toContain(token);
    }
  });

  it("stacks the filter columns on narrow screens", () => {
    expect(css).toMatch(/@media \(max-width: 720px\)/);
    const media = css.slice(css.indexOf("@media (max-width: 720px)"));
    expect(media).toMatch(/\.landscape-filter-columns\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/);
  });

  it("contains long option labels instead of stretching the toolbar", () => {
    expect(css).toMatch(
      /\.landscape-filter-option-label\s*\{[^}]*text-overflow:\s*ellipsis/,
    );
    expect(css).toMatch(
      /\.landscape-filter-chip-label\s*\{[^}]*text-overflow:\s*ellipsis/,
    );
    expect(css).toMatch(/\.landscape-filter-chips\s*\{[^}]*flex-wrap:\s*wrap/);
  });

  it("lets the topology fill the remaining height under the filter bar", () => {
    expect(css).toMatch(/\.integration-landscape\s*\{[^}]*flex-direction:\s*column/);
    expect(css).toMatch(
      /\.integration-landscape\s*>\s*\.integration-topology-view\s*\{[^}]*flex:\s*1/,
    );
  });

  it("keeps the toolbar compact", () => {
    expect(css).toMatch(/\.landscape-filter-bar\s*\{[^}]*gap:\s*8px/);
    expect(css).toMatch(/\.landscape-filter-columns\s*\{[^}]*max-height:\s*min\(/);
  });
});
