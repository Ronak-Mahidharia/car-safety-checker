// Light or dark. Until someone uses the switch, the page follows the device's setting, which the CSS
// handles on its own. A choice is saved in this browser only (no cookie), and public/theme.js applies
// it before the page is drawn, so the other theme never flashes first.
export type Theme = "light" | "dark";

// public/theme.js repeats these two values; a test checks that they match.
export const THEME_KEY = "car-safety-checker-theme";
export const THEME_COLORS: Record<Theme, string> = { light: "#f4f6fa", dark: "#0b1020" }; // each theme's page background

/** The theme saved in this browser, or null when there's none or storage is blocked. */
export function savedTheme(storage: Pick<Storage, "getItem"> | undefined): Theme | null {
  try {
    const value = storage?.getItem(THEME_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

/** The theme the page shows: the saved choice, or else the device's setting. */
export function currentTheme(saved: Theme | null, prefersDark: boolean): Theme {
  return saved ?? (prefersDark ? "dark" : "light");
}

/**
 * Shows a theme and saves the choice. The browser's toolbar color follows it. Saving can fail, in
 * some private windows for example; the theme still applies until the page is closed.
 */
export function chooseTheme(
  theme: Theme,
  root: { dataset: DOMStringMap },
  toolbarColors: Iterable<{ content: string }>,
  storage: Pick<Storage, "setItem"> | undefined,
): void {
  root.dataset.theme = theme;
  for (const meta of toolbarColors) meta.content = THEME_COLORS[theme];
  try {
    storage?.setItem(THEME_KEY, theme);
  } catch {
    // not saved: the next visit follows the device's setting again
  }
}
