// Masking must match src/carsafety/privacy.py: the fixture holds the Python answers
// (scripts/build_web_fixtures.py) for made-up text full of emails, phone numbers, and VINs.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { scrub } from "./privacy";

const fixture = JSON.parse(readFileSync(new URL("./fixtures/privacy.json", import.meta.url), "utf8")) as {
  scrub: [string, string][];
};
const sample = readFileSync(new URL("../../../data/sample/test_sample.jsonl", import.meta.url), "utf8")
  .trim()
  .split("\n")
  .map((line) => (JSON.parse(line) as { text: string }).text);

describe("scrub", () => {
  it("masks the same text as the Python version", () => {
    expect(fixture.scrub.length).toBeGreaterThan(10);
    for (const [text, expected] of fixture.scrub) expect(scrub(text)).toBe(expected);
  });

  it("leaves the 1,000 already-checked sample complaints unchanged", () => {
    expect(sample).toHaveLength(1000);
    expect(sample.filter((text) => scrub(text) !== text)).toEqual([]);
  });

  it("can be applied twice without changing the result", () => {
    for (const [text] of fixture.scrub) expect(scrub(scrub(text))).toBe(scrub(text));
  });
});
