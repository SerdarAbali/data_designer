// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import useStudioTheme from "./useStudioTheme";

function Theme() {
  const { theme, toggleTheme } = useStudioTheme();
  return <button onClick={toggleTheme}>{theme}</button>;
}
afterEach(() => { cleanup(); localStorage.clear(); vi.unstubAllGlobals(); });
describe("studio themes", () => {
  it("follows system preference initially and remembers an explicit choice", () => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true })));
    render(<Theme />);
    expect(document.documentElement.dataset.theme).toBe("dark");
    fireEvent.click(screen.getByRole("button", { name: "dark" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem("dd_studio_theme")).toBe("light");
    cleanup();
    render(<Theme />);
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});
