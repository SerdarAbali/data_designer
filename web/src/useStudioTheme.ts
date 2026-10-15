import React from "react";

type Theme = "light" | "dark";

function initialTheme(): Theme {
  try {
    const stored = localStorage.getItem("dd_studio_theme");
    if (stored === "light" || stored === "dark") return stored;
  } catch (error) {
    console.warn("Theme preference storage is unavailable.", error);
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function useStudioTheme() {
  const [theme, setTheme] = React.useState<Theme>(initialTheme);
  React.useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
  }, [theme]);
  function toggleTheme() {
    const next = theme === "light" ? "dark" : "light";
    setTheme(next);
    try {
      localStorage.setItem("dd_studio_theme", next);
    } catch (error) {
      console.warn("Could not remember the theme preference.", error);
    }
  }
  return { theme, toggleTheme };
}
