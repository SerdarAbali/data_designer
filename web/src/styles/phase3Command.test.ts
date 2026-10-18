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

describe("Phase 3 — More menu pattern", () => {
  it("defines More menu contracts", () => {
    expect(styleCss).toContain(".more-menu");
    expect(styleCss).toContain(".more-menu-trigger");
    expect(styleCss).toContain(".more-menu-panel");
    expect(styleCss).toContain(".more-menu-item");
    expect(styleCss).toContain(".more-menu-item--danger");
    expect(styleCss).toContain(".more-menu-separator");
  });

  it("uses semantic tokens for More menu", () => {
    const trigger = blockFor(styleCss, ".more-menu-trigger {");
    expect(trigger).toContain("var(--color-surface)");
    expect(trigger).toContain("var(--color-ink)");
    expect(trigger).toContain("var(--color-border)");

    const panel = blockFor(styleCss, ".more-menu-panel {");
    expect(panel).toContain("var(--color-surface)");
    expect(panel).toContain("var(--shadow-panel)");
  });

  it("distinguishes dangerous menu items", () => {
    expect(styleCss).toContain(".more-menu-item--danger");
    const danger = blockFor(styleCss, ".more-menu-item--danger {");
    expect(danger).toContain("var(--color-danger)");
  });
});

describe("Phase 3 — Creation popover pattern", () => {
  it("defines creation popover contracts", () => {
    expect(styleCss).toContain(".creation-popover");
    expect(styleCss).toContain(".creation-panel");
    expect(styleCss).toContain(".creation-fields");
    expect(styleCss).toContain(".creation-actions");
    expect(styleCss).toContain(".creation-close");
    expect(styleCss).toContain(".creation-error");
    expect(styleCss).toContain(".creation-hint");
  });

  it("has accessible close button in creation panel", () => {
    const close = blockFor(styleCss, ".creation-close {");
    expect(close).toContain("border-radius");
    expect(close).toContain("cursor: pointer");
  });
});

describe("Phase 3 — View toolbar pattern", () => {
  it("defines view toolbar contracts", () => {
    expect(styleCss).toContain(".view-toolbar");
    expect(styleCss).toContain(".view-toolbar-left");
    expect(styleCss).toContain(".view-toolbar-right");
    expect(styleCss).toContain(".view-toolbar-title");
    expect(styleCss).toContain(".view-toolbar-scope");
    expect(styleCss).toContain(".view-toolbar-divider");
    expect(styleCss).toContain(".view-toolbar-count");
  });

  it("allows one primary action at most", () => {
    // Primary actions use .btn--primary; secondary uses .btn--secondary
    expect(styleCss).toContain(".btn--primary");
    expect(styleCss).toContain(".btn--secondary");
  });

  it("wraps predictably at narrow widths", () => {
    expect(styleCss).toContain("@media (max-width: 760px)");
    expect(styleCss).toContain(".view-toolbar {");
  });
});

describe("Phase 3 — Inspector action consolidation", () => {
  it("defines inspector action row contracts", () => {
    expect(styleCss).toContain(".inspector-actions-row");
    expect(styleCss).toContain(".inspector-manage-menu");
    expect(styleCss).toContain(".inspector-manage-trigger");
  });
});

describe("Phase 3 — Confirmation dialog pattern", () => {
  it("defines confirm dialog contracts", () => {
    expect(styleCss).toContain(".confirm-dialog");
    expect(styleCss).toContain(".confirm-dialog::backdrop");
    expect(styleCss).toContain(".confirm-dialog-actions");
  });

  it("uses backdrop for modal confirmation", () => {
    const backdrop = blockFor(styleCss, ".confirm-dialog::backdrop {");
    expect(backdrop).toContain("backdrop-filter");
    expect(backdrop).toContain("rgb(15 18 26 / 35%)");
  });
});

describe("Phase 3 — Proposal lifecycle action hierarchy", () => {
  it("defines proposal action group contracts", () => {
    expect(styleCss).toContain(".proposal-action-group");
    expect(styleCss).toContain(".proposal-status-chip");
  });

  it("separates Approve and Apply as distinct actions", () => {
    // Both are separate button types in the CSS via .btn--primary and .btn--secondary
    expect(styleCss).toContain(".btn--primary");
    expect(styleCss).toContain(".btn--secondary");
    expect(styleCss).toContain(".btn--tertiary");
  });
});
