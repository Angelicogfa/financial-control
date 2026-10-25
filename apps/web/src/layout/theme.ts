/** Light/dark preference, applied on <html data-theme> (index.html sets it before paint). */

export type Theme = "light" | "dark";
const STORAGE_KEY = "fincontrol:theme";

export function currentTheme(): Theme {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute("data-theme", theme);
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Private mode: the choice lasts for this page only.
  }
}
