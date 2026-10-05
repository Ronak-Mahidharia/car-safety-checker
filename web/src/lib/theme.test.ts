import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { chooseTheme, currentTheme, savedTheme, THEME_COLORS, THEME_KEY } from "./theme";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");

const memory = (start: Record<string, string> = {}) => {
  const values = { ...start };
  return { values, getItem: (key: string) => values[key] ?? null, setItem: (key: string, value: string) => void (values[key] = value) };
};
const blocked = {
  getItem: (): string | null => {
    throw new Error("storage blocked");
  },
  setItem: (): void => {
    throw new Error("storage blocked");
  },
};

describe("the saved theme", () => {
  it("reads light or dark, and ignores anything else", () => {
    expect(savedTheme(memory({ [THEME_KEY]: "dark" }))).toBe("dark");
    expect(savedTheme(memory({ [THEME_KEY]: "light" }))).toBe("light");
    expect(savedTheme(memory({ [THEME_KEY]: "blue" }))).toBeNull();
    expect(savedTheme(memory())).toBeNull();
  });

  it("is none when storage is blocked or missing", () => {
    expect(savedTheme(blocked)).toBeNull();
    expect(savedTheme(undefined)).toBeNull();
  });
});

describe("the theme the page shows", () => {
  it("is the saved choice, or else the device's setting", () => {
    expect(currentTheme("light", true)).toBe("light");
    expect(currentTheme("dark", false)).toBe("dark");
    expect(currentTheme(null, true)).toBe("dark");
    expect(currentTheme(null, false)).toBe("light");
  });
});

describe("choosing a theme", () => {
  it("shows it, colors the browser toolbar to match, and saves it", () => {
    const root = { dataset: {} as DOMStringMap };
    const metas = [{ content: THEME_COLORS.light }, { content: THEME_COLORS.dark }];
    const storage = memory();
    chooseTheme("dark", root, metas, storage);
    expect(root.dataset.theme).toBe("dark");
    expect(metas.map((m) => m.content)).toEqual([THEME_COLORS.dark, THEME_COLORS.dark]);
    expect(storage.values[THEME_KEY]).toBe("dark");
  });

  it("still applies when it can't be saved", () => {
    const root = { dataset: {} as DOMStringMap };
    chooseTheme("light", root, [], blocked);
    expect(root.dataset.theme).toBe("light");
  });
});

describe("the files the theme depends on", () => {
  it("public/theme.js uses the same storage key and colors", () => {
    const script = read("../../public/theme.js");
    expect(script).toContain(`"${THEME_KEY}"`);
    expect(script).toContain(`"${THEME_COLORS.dark}"`);
    expect(script).toContain(`"${THEME_COLORS.light}"`);
  });

  it("the page loads theme.js before its own code, so the saved theme shows first", () => {
    const html = read("../../index.html");
    expect(html.indexOf('src="/theme.js"')).toBeGreaterThan(-1);
    expect(html.indexOf('src="/theme.js"')).toBeLessThan(html.indexOf('src="/src/main.tsx"'));
  });

  it("the dark colors chosen with the switch are the same as the device-setting ones", () => {
    const css = read("../styles.css");
    const block = (selector: string) => {
      const start = css.indexOf(`${selector} {`);
      expect(start, selector).toBeGreaterThan(-1);
      const body = css.slice(start, css.indexOf("}", start));
      return body.match(/--[\w-]+:[^;]+;/g) ?? [];
    };
    const device = block(':root:not([data-theme="light"])');
    expect(device.length).toBeGreaterThan(20);
    expect(block(':root[data-theme="dark"]')).toEqual(device);
    // Each page background matches the toolbar color for that theme.
    expect(device).toContain(`--bg: ${THEME_COLORS.dark};`);
    expect(block(":root")).toContain(`--bg: ${THEME_COLORS.light};`);
  });
});
