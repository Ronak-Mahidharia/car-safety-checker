import { describe, expect, it } from "vitest";
import { matchComplaints, orderRecalls, similarity, type Vector } from "./match";
import type { Complaint, Recall } from "./nhtsa";

const recall = (campaign: string, received: string | null, label: string | null, flags: Partial<Recall> = {}): Recall => ({
  campaign,
  received,
  component: label ?? "UNKNOWN OR OTHER",
  label,
  summary: "",
  consequence: "",
  remedy: "",
  doNotDrive: false,
  parkOutside: false,
  overTheAir: false,
  source: "",
  listedAs: "TEST",
  ...flags,
});

describe("orderRecalls", () => {
  const list = [
    recall("A-old-engine", "2019-05-21", "ENGINE"),
    recall("B-new-tires", "2024-01-10", "TIRES"),
    recall("C-park-outside", "2018-02-01", "ELECTRICAL SYSTEM", { parkOutside: true }),
    recall("D-new-engine", "2023-03-09", "ENGINE"),
    recall("E-no-date", null, "TIRES"),
    recall("F-do-not-drive", "2017-07-07", "AIR BAGS", { doNotDrive: true }),
  ];

  it("lists every recall: advisories first, then matches, then the rest, newest first in each group", () => {
    const order = orderRecalls(list, ["ENGINE"]).map((r) => r.campaign);
    expect(order).toEqual(["C-park-outside", "F-do-not-drive", "D-new-engine", "A-old-engine", "B-new-tires", "E-no-date"]);
  });

  it("marks matches and advisories", () => {
    const shown = orderRecalls(list, ["ENGINE"]);
    expect(shown.filter((r) => r.matches).map((r) => r.campaign)).toEqual(["D-new-engine", "A-old-engine"]);
    expect(shown.filter((r) => r.advisory).map((r) => r.campaign)).toEqual(["C-park-outside", "F-do-not-drive"]);
  });

  it("without a description, keeps advisories first and the rest newest first", () => {
    const order = orderRecalls(list, []).map((r) => r.campaign);
    expect(order).toEqual(["C-park-outside", "F-do-not-drive", "B-new-tires", "D-new-engine", "A-old-engine", "E-no-date"]);
  });
});

describe("similarity", () => {
  it("is the dot product of two unit vectors", () => {
    const a: Vector = new Map([[1, 0.6], [2, 0.8]]);
    const b: Vector = new Map([[2, 1]]);
    expect(similarity(a, b)).toBeCloseTo(0.8);
    expect(similarity(a, a)).toBeCloseTo(1);
    expect(similarity(a, new Map())).toBe(0);
  });
});

describe("matchComplaints", () => {
  // A stand-in for the model's tf-idf vectors: one column per word, scaled to length 1.
  const words = new Map<string, number>();
  const vectorize = (text: string): Vector => {
    const counts = new Map<number, number>();
    for (const word of text.toLowerCase().match(/[a-z]+/g) ?? []) {
      if (!words.has(word)) words.set(word, words.size);
      const i = words.get(word)!;
      counts.set(i, (counts.get(i) ?? 0) + 1);
    }
    const length = Math.sqrt([...counts.values()].reduce((sum, n) => sum + n * n, 0));
    return new Map([...counts].map(([i, n]) => [i, n / length]));
  };
  const complaint = (odiNumber: string, labels: string[], summary: string, filed: string): Complaint => ({
    odiNumber, filed, components: labels, labels, summary, crash: false, fire: false, injuries: 0, deaths: 0, source: "", listedAs: "TEST",
  });
  const list = [
    complaint("1", ["ENGINE"], "engine hesitates and stalls", "2025-01-01"),
    complaint("2", ["TIRES"], "engine hesitates and stalls", "2025-01-02"),
    complaint("3", ["ENGINE", "ELECTRICAL SYSTEM"], "check engine light", "2025-01-03"),
    complaint("4", ["ENGINE"], "engine hesitates", "2025-01-04"),
    complaint("5", ["ENGINE"], "radio stopped working", "2026-01-01"),
  ];

  it("keeps complaints filed under a likely component, the closest wording first", () => {
    const result = matchComplaints(list, ["ENGINE"], "the engine hesitates", vectorize);
    expect(result.filedUnder).toBe(4);
    expect(result.shown.map((m) => m.complaint.odiNumber)).toEqual(["4", "1", "3", "5"]);
  });

  it("breaks ties by date, newest first, and respects the limit", () => {
    const result = matchComplaints(list, ["ENGINE"], "nothing in common", vectorize, 2);
    expect(result.shown.map((m) => m.complaint.odiNumber)).toEqual(["5", "4"]);
  });

  it("finds nothing when no complaint is filed under the likely components", () => {
    expect(matchComplaints(list, ["SEATS"], "seat broke", vectorize)).toEqual({ filedUnder: 0, shown: [] });
  });
});
