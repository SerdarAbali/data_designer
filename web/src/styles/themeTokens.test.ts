import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

// jsdom does not compute cascade-dependent colours, so the light/dark contract
// is asserted against the stylesheet source instead of getComputedStyle.
const css = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "studio.css"), "utf8");

function declarationBlock(selector: string): string {
  const start = css.indexOf(selector);
  expect(start, `missing selector ${selector}`).toBeGreaterThanOrEqual(0);
  const open = css.indexOf("{", start);
  const close = css.indexOf("}", open);
  return css.slice(open + 1, close);
}

describe("theme tokens", () => {
  it("defines the semantic warning token in both themes", () => {
    const light = declarationBlock(":root {");
    const dark = declarationBlock(':root[data-theme="dark"] {');
    for (const body of [light, dark]) {
      expect(body).toMatch(/--color-warning:\s*#/);
      expect(body).toMatch(/--color-warning-soft:\s*#/);
    }
    // The dark override must differ from the light token so contrast adapts.
    expect(light).not.toBe(dark);
    expect(declarationBlock(':root[data-theme="dark"] {')).toContain("--color-danger:");
  });

  it("routes integration status colours through semantic tokens, not fixed hex", () => {
    expect(css).not.toMatch(/#b03a3a/i);
    expect(css).not.toMatch(/#2f7a52/i);
    expect(css).toMatch(
      /\.integration-status-built[^{]*\{[^}]*color:\s*var\(--color-healthy\)/,
    );
    expect(css).toMatch(
      /\.integration-status-attention[^{]*\{[^}]*color:\s*var\(--color-danger\)/,
    );
    expect(css).toMatch(/\.integration-toolbar-error[^{]*\{[^}]*color:\s*var\(--color-danger\)/);
  });

  it("keeps enterprise primary names on the foreground token, not button on-accent", () => {
    expect(declarationBlock(".enterprise-object-card {")).toContain("color: var(--color-ink)");
    expect(declarationBlock(".enterprise-object-card strong {")).toContain("color: var(--color-ink)");
    expect(declarationBlock(".enterprise-capability-name {")).toContain("color: var(--color-ink)");
    // Owner is secondary metadata, never the primary name colour.
    expect(declarationBlock(".enterprise-object-card small {")).toContain("var(--color-muted)");
  });

  it("keeps the application support toolbar compact and the canvas full height", () => {
    expect(declarationBlock(".enterprise-app-support {")).toMatch(
      /grid-template-rows:\s*auto minmax\(0,\s*1fr\)/,
    );
  });
});
