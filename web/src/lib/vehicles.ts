// Vehicle names for the picker. NHTSA's recall and complaint records often name the same vehicle
// differently (checked Oct 2, 2026): the 2026 Lucid Air's recalls are filed under "AIR" and its
// complaints under "AIR BEV", and NHTSA's vehicle-list API offers only "AIR BEV". A recall is found
// only by the exact model name it's filed under, so:
//   1. the picker also offers every name in NHTSA's recall file (public/vehicles/, built by
//      scripts/build_vehicle_index.py), and
//   2. a search covers related names: one name is the other plus more words ("AIR" and "AIR BEV").
// NHTSA's searches ignore capitals, so every name is kept in capitals.
import { makes as listedMakes, modelYears as listedYears, models as listedModels } from "./nhtsa";

type Fetcher = (url: string) => Promise<Response>;
type YearFile = Record<string, string[]>; // make -> model names

const BASE = `${import.meta.env.BASE_URL}vehicles/`;

async function readJson<T>(name: string, fetcher: Fetcher): Promise<T> {
  const response = await fetcher(`${BASE}${name}`);
  if (!response.ok) throw new Error(`Couldn't load ${name} (${response.status})`);
  return (await response.json()) as T;
}

let recallYearsFile: Promise<string[]> | null = null;
const recallYearFiles = new Map<string, Promise<YearFile>>();

/** Model years in NHTSA's recall file. */
export function recallYears(fetcher: Fetcher = fetch): Promise<string[]> {
  recallYearsFile ??= readJson<string[]>("years.json", fetcher).catch((error: unknown) => {
    recallYearsFile = null; // try again next time
    throw error;
  });
  return recallYearsFile;
}

/** The recall file's makes and models for one model year ({} for a year it doesn't have). */
export function recallNames(year: string, fetcher: Fetcher = fetch): Promise<YearFile> {
  let file = recallYearFiles.get(year);
  if (!file) {
    file = recallYears(fetcher)
      .then((years) => (years.includes(year) ? readJson<YearFile>(`${year}.json`, fetcher) : {}))
      .catch((error: unknown) => {
        recallYearFiles.delete(year);
        throw error;
      });
    recallYearFiles.set(year, file);
  }
  return file;
}

/** Names from both sources, in capitals and without repeats. Either source is enough if the other fails. */
async function combine(sources: Promise<string[]>[]): Promise<string[]> {
  const settled = await Promise.allSettled(sources);
  const found = settled.flatMap((s) => (s.status === "fulfilled" ? [s.value] : []));
  if (!found.length) throw (settled[0] as PromiseRejectedResult).reason;
  return [...new Set(found.flat().map((name) => name.trim().toUpperCase()).filter(Boolean))];
}

export async function vehicleYears(signal?: AbortSignal): Promise<string[]> {
  const years = await combine([listedYears(signal), recallYears()]);
  return years.sort((a, b) => Number(b) - Number(a));
}

export async function vehicleMakes(year: string, signal?: AbortSignal): Promise<string[]> {
  return (await combine([listedMakes(year, signal), recallNames(year).then(Object.keys)])).sort();
}

const modelLists = new Map<string, string[]>();

export async function vehicleModels(year: string, make: string, signal?: AbortSignal): Promise<string[]> {
  const key = `${year}|${make}`;
  const known = modelLists.get(key);
  if (known) return known;
  const models = (await combine([listedModels(year, make, signal), recallNames(year).then((file) => file[make] ?? [])])).sort();
  modelLists.set(key, models);
  return models;
}

/** True if the names are equal or one is the other plus more words ("AIR" and "AIR BEV"). */
export function related(a: string, b: string): boolean {
  return a === b || a.startsWith(`${b} `) || b.startsWith(`${a} `);
}

/** The chosen name first, then every related name from the list. */
export function relatedNames(name: string, names: readonly string[]): string[] {
  return [name, ...names.filter((other) => other !== name && related(name, other))];
}
