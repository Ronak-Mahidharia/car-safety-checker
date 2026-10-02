// The keyword model, running in the browser. It follows the same steps as
// src/carsafety/browser_model.py (which matches scikit-learn), so it gives the same answers:
//   1. lowercase, then remove accents
//   2. words of 2 or more letters or digits, plus every pair of neighboring words
//   3. for each known term: (1 + log(count)) * idf, then scale the vector to length 1
//   4. for each label: probability = sigmoid(weights . vector + bias)
//   5. labels at or above the threshold, or else the single most likely one

export interface ModelFiles {
  labels: string[];
  vocabulary: string[];
  idf: number[];
  bias: number[];
  scale: number[];
  threshold: number;
}

const ASCII_ONLY = /^[\x00-\x7F]*$/;
const COMBINING_MARK = /\p{Mn}/gu;
const TOKEN = /[\p{L}\p{N}_]{2,}/gu;

export function preprocess(text: string): string {
  const lower = text.toLowerCase();
  return ASCII_ONLY.test(lower) ? lower : lower.normalize("NFKD").replace(COMBINING_MARK, "");
}

export function terms(text: string): string[] {
  const tokens = preprocess(text).match(TOKEN) ?? [];
  const pairs = tokens.slice(1).map((token, i) => `${tokens[i]} ${token}`);
  return [...tokens, ...pairs];
}

export class KeywordModel {
  readonly labels: string[];
  readonly threshold: number;
  private readonly index: Map<string, number>;
  private readonly idf: Float64Array;
  private readonly bias: Float64Array;
  private readonly scale: Float64Array;
  private readonly weights: Int8Array;
  private readonly size: number;

  constructor(files: ModelFiles, weights: Int8Array) {
    if (weights.length !== files.labels.length * files.vocabulary.length) {
      throw new Error("weights.bin doesn't match model.json");
    }
    this.labels = files.labels;
    this.threshold = files.threshold;
    this.index = new Map(files.vocabulary.map((term, i) => [term, i]));
    this.idf = Float64Array.from(files.idf);
    this.bias = Float64Array.from(files.bias);
    this.scale = Float64Array.from(files.scale);
    this.weights = weights;
    this.size = files.vocabulary.length;
  }

  static async load(base = "/model/"): Promise<KeywordModel> {
    const get = async (name: string) => {
      const response = await fetch(`${base}${name}`);
      if (!response.ok) throw new Error(`Couldn't load ${name} (${response.status})`);
      return response;
    };
    const [files, buffer] = await Promise.all([
      get("model.json").then((r) => r.json() as Promise<ModelFiles>),
      get("weights.bin").then((r) => r.arrayBuffer()),
    ]);
    return new KeywordModel(files, new Int8Array(buffer));
  }

  /** Steps 1 to 3: the text's tf-idf vector, scaled to length 1, as column -> value. Empty if no term is known. */
  vector(text: string): Map<number, number> {
    const counts = new Map<number, number>();
    for (const term of terms(text)) {
      const i = this.index.get(term);
      if (i !== undefined) counts.set(i, (counts.get(i) ?? 0) + 1);
    }
    const values = [...counts].map(([i, n]) => [i, (1 + Math.log(n)) * this.idf[i]] as const);
    const length = Math.sqrt(values.reduce((sum, [, v]) => sum + v * v, 0));
    return new Map(values.map(([i, v]) => [i, v / length]));
  }

  probabilities(text: string): Float64Array {
    const vector = this.vector(text);
    const probs = new Float64Array(this.labels.length);
    for (let label = 0; label < this.labels.length; label++) {
      let z = this.bias[label];
      for (const [column, value] of vector) {
        z += this.weights[label * this.size + column] * this.scale[label] * value;
      }
      probs[label] = 1 / (1 + Math.exp(-z));
    }
    return probs;
  }

  /** The predicted labels, sorted. Always at least one. */
  predict(text: string): string[] {
    const probs = this.probabilities(text);
    let best = 0;
    const chosen: string[] = [];
    probs.forEach((p, i) => {
      if (p >= this.threshold) chosen.push(this.labels[i]);
      if (p > probs[best]) best = i;
    });
    return (chosen.length ? chosen : [this.labels[best]]).sort();
  }

  /** The n most likely labels with their probabilities, most likely first. */
  top(text: string, n = 3): [string, number][] {
    const probs = this.probabilities(text);
    return [...probs.keys()]
      .sort((a, b) => probs[b] - probs[a])
      .slice(0, n)
      .map((i) => [this.labels[i], probs[i]]);
  }
}
