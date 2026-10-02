// The browser model must give the same answers as the Python version
// (src/carsafety/browser_model.py) on all 1,000 complaints in the fixed test sample.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { KeywordModel, terms, type ModelFiles } from "./keywordModel";

const web = new URL("../../", import.meta.url);
const read = (path: string) => readFileSync(new URL(path, web));

const files = JSON.parse(read("public/model/model.json").toString("utf8")) as ModelFiles;
const buffer = read("public/model/weights.bin");
const model = new KeywordModel(files, new Int8Array(buffer.buffer, buffer.byteOffset, buffer.byteLength));

type Expected = { id: string; labels: string[]; top: [string, number][] };
const expected = JSON.parse(read("src/model/expected.json").toString("utf8")) as Expected[];
const sample = read("../data/sample/test_sample.jsonl")
  .toString("utf8")
  .trim()
  .split("\n")
  .map((line) => JSON.parse(line) as { id: string; text: string });

describe("terms", () => {
  it("splits text the same way as scikit-learn", () => {
    expect(terms("It's the 2019's model, ok?")).toEqual([
      "it", "the", "2019", "model", "ok", "it the", "the 2019", "2019 model", "model ok",
    ]);
    expect(terms("café naïve BRAKÉS")).toEqual(["cafe", "naive", "brakes", "cafe naive", "naive brakes"]);
    expect(terms("a b c")).toEqual([]);
  });
});

describe("KeywordModel", () => {
  it("covers the same 1,000 complaints as the Python answers", () => {
    expect(sample.map((r) => r.id)).toEqual(expected.map((e) => e.id));
  });

  it("gives the same labels as the Python version on all 1,000 test complaints", () => {
    const mismatches = sample.filter((r, i) => model.predict(r.text).join("|") !== expected[i].labels.join("|"));
    expect(mismatches.map((r) => r.id)).toEqual([]);
  });

  it("gives the same top 3 probabilities as the Python version", () => {
    sample.forEach((r, i) => {
      const ours = model.top(r.text, 3);
      expected[i].top.forEach(([label, probability], k) => {
        expect(ours[k][0]).toBe(label);
        expect(Math.abs(ours[k][1] - probability)).toBeLessThan(1e-6);
      });
    });
  });
});
