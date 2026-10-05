import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// What a shared link shows. LinkedIn reads these Open Graph tags and wants a picture of at least
// 1200 x 627 pixels, about 1.91:1, and under 5 MB.
const read = (path: string) => readFileSync(new URL(path, import.meta.url));
const html = read("../index.html").toString("utf8");
const meta = (key: string) => html.match(new RegExp(`<meta (?:property|name)="${key}" content="([^"]*)"`))?.[1];

describe("link previews", () => {
  it("the page has the tags that sharing sites read", () => {
    for (const key of ["og:title", "og:description", "og:url", "og:image", "og:image:alt"]) expect(meta(key), key).toBeTruthy();
    expect(meta("og:url")).toBe("https://ronak-mahidharia.github.io/car-safety-checker/");
    expect(meta("og:image")?.startsWith(meta("og:url")!)).toBe(true);
    expect(meta("twitter:card")).toBe("summary_large_image");
  });

  it("the picture is in public/, at the size the tags give", () => {
    const png = read(`../public/${meta("og:image")!.slice(meta("og:url")!.length)}`);
    expect(png.subarray(1, 4).toString("latin1")).toBe("PNG");
    // A PNG stores its width and height as 4-byte numbers at bytes 16 and 20.
    const [width, height] = [png.readUInt32BE(16), png.readUInt32BE(20)];
    expect([String(width), String(height)]).toEqual([meta("og:image:width"), meta("og:image:height")]);
    expect(width).toBeGreaterThanOrEqual(1200);
    expect(height).toBeGreaterThanOrEqual(627);
    expect(Math.abs(width / height - 1.91)).toBeLessThan(0.02);
    expect(png.length).toBeLessThan(5 * 1024 * 1024);
  });
});
