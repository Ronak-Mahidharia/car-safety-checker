// What the page shows once it knows the vehicle and the likely components.
import type { Complaint, Recall } from "./nhtsa";

export interface ShownRecall extends Recall {
  advisory: boolean; // "Do Not Drive" or "Park Outside"
  matches: boolean; // its component is one of the likely ones
}

// Dates are "YYYY-MM-DD" strings, so comparing them as text compares them as dates. Unknown dates go last.
const newestFirst = (a: string | null, b: string | null) => {
  const [x, y] = [a ?? "", b ?? ""];
  return x === y ? 0 : x < y ? 1 : -1;
};

/**
 * Every recall for the vehicle, never just the matching ones: NHTSA's API lists one component per
 * recall, so a recall that also covers the problem could look unrelated. Order: recalls with a
 * "Do Not Drive" or "Park Outside" advisory first, then those matching the likely components,
 * then the rest; newest first within each group.
 */
export function orderRecalls(recalls: readonly Recall[], labels: readonly string[]): ShownRecall[] {
  const likely = new Set(labels);
  return recalls
    .map((r) => ({ ...r, advisory: r.doNotDrive || r.parkOutside, matches: r.label !== null && likely.has(r.label) }))
    .sort((a, b) => Number(b.advisory) - Number(a.advisory) || Number(b.matches) - Number(a.matches) || newestFirst(a.received, b.received));
}

export type Vector = Map<number, number>;

/** Cosine similarity of two vectors that already have length 1. */
export function similarity(a: Vector, b: Vector): number {
  const [small, large] = a.size <= b.size ? [a, b] : [b, a];
  let total = 0;
  for (const [i, value] of small) total += value * (large.get(i) ?? 0);
  return total;
}

export interface ComplaintMatches {
  filedUnder: number; // complaints NHTSA filed under at least one likely component
  shown: { complaint: Complaint; similarity: number }[];
}

/**
 * Complaints filed under at least one of the likely components, the most similar wording first
 * (ties: newest first). `vectorize` turns text into the keyword model's tf-idf vector.
 */
export function matchComplaints(
  complaints: readonly Complaint[],
  labels: readonly string[],
  description: string,
  vectorize: (text: string) => Vector,
  limit = 10,
): ComplaintMatches {
  const likely = new Set(labels);
  const query = vectorize(description);
  const candidates = complaints.filter((c) => c.labels.some((label) => likely.has(label)));
  const scored = candidates.map((complaint) => ({ complaint, similarity: similarity(query, vectorize(complaint.summary)) }));
  scored.sort((a, b) => b.similarity - a.similarity || newestFirst(a.complaint.filed, b.complaint.filed));
  return { filedUnder: candidates.length, shown: scored.slice(0, limit) };
}
