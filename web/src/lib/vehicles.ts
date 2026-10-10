// Vehicle names, and which of NHTSA's records belong to the vehicle someone picks. NHTSA's API names
// the same vehicle in more than one way (checked Oct 3, 2026):
//   - Its complaint search takes the names in its vehicle list ("AIR BEV", "MUSTANG MACH-E",
//     "F-150 (SUPER CREW) LIGHTNING BEV"), but each complaint record names the model the way recalls
//     are filed ("AIR", "MUSTANG MACH E", "F-150 LIGHTNING BEV").
//   - Its recall search takes only those recall names, and the vehicle list leaves some out (it offers
//     only "AIR BEV" for the 2026 Lucid Air), so the picker also offers every name in NHTSA's recall
//     file (public/vehicles/, built by scripts/build_vehicle_index.py).
//   - A complaint search can return another model's records too: the 2023 "F-150 (SUPER CREW)
//     LIGHTNING BEV" search returns 94 complaints whose records name the F-150 HYBRID.
// So a search covers related names (spelled the same apart from punctuation, or with more words), and
// the models named on the complaint records decide which recalls and complaints are the vehicle's own.
// Recalls under related names that the records don't tie to the vehicle are kept apart, never dropped:
// "MUSTANG" is related to "MUSTANG MACH-E" but is a different car. src/carsafety/vehicles.py does the
// same in Python. NHTSA's searches ignore capitals, so every name is kept in capitals.
import {
  complaints as complaintsFor,
  makes as listedMakes,
  modelYears as listedYears,
  models as listedModels,
  recalls as recallsFor,
  type Complaint,
  type Recall,
  type Vehicle,
} from "./nhtsa";

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

/**
 * Names from both sources, in capitals and without repeats. Either source is enough if the other fails;
 * `complete` says whether both answered.
 */
async function combine(sources: Promise<string[]>[]): Promise<{ names: string[]; complete: boolean }> {
  const settled = await Promise.allSettled(sources);
  const found = settled.flatMap((s) => (s.status === "fulfilled" ? [s.value] : []));
  if (!found.length) throw (settled[0] as PromiseRejectedResult).reason;
  const names = [...new Set(found.flat().map((name) => name.trim().toUpperCase()).filter(Boolean))];
  return { names, complete: found.length === settled.length };
}

export async function vehicleYears(signal?: AbortSignal): Promise<string[]> {
  const { names } = await combine([listedYears(signal), recallYears()]);
  return names.sort((a, b) => Number(b) - Number(a));
}

export async function vehicleMakes(year: string, signal?: AbortSignal): Promise<string[]> {
  return (await combine([listedMakes(year, signal), recallNames(year).then(Object.keys)])).names.sort();
}

const modelLists = new Map<string, string[]>();

export async function vehicleModels(year: string, make: string, signal?: AbortSignal): Promise<string[]> {
  const key = `${year}|${make}`;
  const known = modelLists.get(key);
  if (known) return known;
  const { names, complete } = await combine([listedModels(year, make, signal), recallNames(year).then((file) => file[make] ?? [])]);
  const models = names.sort();
  // A list made while NHTSA's list failed or was cancelled lacks the names only NHTSA has (AIR BEV, MUSTANG
  // MACH-E), and complaints are found only under those, so it isn't kept: the next look asks again.
  if (complete) modelLists.set(key, models);
  return models;
}

/** A name's words in capitals, without punctuation: "F-150 (SUPER CREW)" -> ["F150", "SUPER", "CREW"]. */
export function words(name: string): string[] {
  return name
    .toUpperCase()
    .split(/\s+/)
    .map((part) => part.replace(/[^A-Z0-9]/g, ""))
    .filter(Boolean);
}

/** Spelled the same apart from spaces and punctuation: "MUSTANG MACH-E" and "MUSTANG MACH E". */
export function sameName(a: string, b: string): boolean {
  const key = words(a).join("");
  return key !== "" && key === words(b).join("");
}

/**
 * True if `whole` is `part` with more words, in order and starting with the same word. "AIR" is within
 * "AIR BEV", and "F-150 LIGHTNING BEV" is within "F-150 (SUPER CREW) LIGHTNING BEV".
 */
export function within(part: string, whole: string): boolean {
  const p = words(part);
  const w = words(whole);
  if (!p.length || p.length >= w.length || p[0] !== w[0]) return false;
  let next = 0; // each word found after the one before
  for (const word of w) if (next < p.length && word === p[next]) next++;
  return next === p.length;
}

/** Names that may be the same vehicle: spelled the same, or one is the other with more words. */
export function related(a: string, b: string): boolean {
  return sameName(a, b) || within(a, b) || within(b, a);
}

/** The chosen name first, then every related name from the list. */
export function relatedNames(name: string, names: readonly string[]): string[] {
  return [name, ...names.filter((other) => other !== name && related(name, other))];
}

/**
 * The recall-file names that are this name's, judged by the name alone. The first of these that finds any:
 *   1. names spelled the same ("MUSTANG MACH E" for "MUSTANG MACH-E")
 *   2. the one name that is this name with more words ("F-150 LIGHTNING BEV" for "F-150 LIGHTNING"). If
 *      several are, none: the name can't tell them apart.
 *   3. the most specific names within it: "F-150 LIGHTNING BEV", not "F-150", for
 *      "F-150 (SUPER CREW) LIGHTNING BEV". Only with shorter = true: for a name nobody lists and no record
 *      names, a shorter name is a guess ("MUSTANG MAH-E", a typo, isn't the gasoline "MUSTANG").
 */
export function closestRecallNames(name: string, recallFileNames: readonly string[], shorter = true): string[] {
  const same = recallFileNames.filter((r) => sameName(r, name));
  if (same.length) return same;
  const longer = recallFileNames.filter((r) => within(name, r));
  if (longer.length) return longer.length === 1 ? longer : [];
  if (!shorter) return [];
  const fitting = recallFileNames.filter((r) => within(r, name));
  return fitting.filter((r) => !fitting.some((other) => within(r, other)));
}

/** The name without its last words, keeping at least two: "F-150 LIGHTNING BEV" -> ["F-150 LIGHTNING"]. */
export function shorterNames(name: string): string[] {
  const parts = name.split(/\s+/).filter(Boolean);
  const out: string[] = [];
  for (let k = parts.length - 1; k >= 2; k--) out.push(parts.slice(0, k).join(" "));
  return out;
}

/**
 * Which model the chosen vehicle is, from the models its complaint records name. A search can return
 * another model's records too, so the first of these that finds any is kept:
 *   1. models spelled like the chosen name or within it ("AIR" for "AIR BEV")
 *   2. models the chosen name is within
 *   3. every model named: the 2023 "F-150 (SUPER CREW) HEV" records name the F-150 HYBRID
 * With no records, it's the chosen name.
 */
export function identify(chosen: string, recordModels: readonly (string | null)[]): string[] {
  const named: string[] = [];
  for (const m of recordModels) if (m && !named.some((n) => sameName(m, n))) named.push(m); // each model once, spellings aside
  for (const close of [named.filter((m) => sameName(m, chosen) || within(m, chosen)), named.filter((m) => within(chosen, m))]) {
    if (close.length) return close;
  }
  return named.length ? named : [chosen];
}

/** What a search found, split by whether NHTSA's records tie it to the chosen vehicle. */
export interface Found {
  names: string[]; // every name searched, the chosen one first
  models: string[]; // the models the vehicle's complaint records name (or the chosen name)
  ownNames: string[]; // the names whose recalls are the vehicle's own
  recalls: Recall[]; // the vehicle's own
  relatedRecalls: Recall[]; // filed under related names that may be a different vehicle
  complaints: Complaint[]; // the vehicle's own
  leftOut: Record<string, number>; // complaints the chosen name's search returned whose records name another model
}

type ApiFetcher = Parameters<typeof recallsFor>[2];

/**
 * Recalls and complaints for a vehicle, under its name and every related name in `listed`. The
 * complaints found under the chosen name (or one spelled the same) say which model it is. Recalls are
 * its own when filed under the chosen name, a name spelled the same, those models, or their closest
 * recall-file names; recalls under other related names, and under shorter versions of the vehicle's recall
 * names, are kept apart. Complaints are its
 * own when their record names one of those models. Complaints the chosen name's own search returns also
 * count when their record names a version of one with more words (the 2015 "FUSION HEV" search returns
 * FUSION HYBRID complaints) or no model at all; the rest are left out. A record found twice is kept once.
 */
export async function search(
  vehicle: Vehicle,
  listed: readonly string[],
  recallFileNames: readonly string[],
  signal?: AbortSignal,
  fetcher?: ApiFetcher,
): Promise<Found> {
  const under = (model: string): Vehicle => ({ ...vehicle, model });
  const names = relatedNames(vehicle.model, listed);
  const fetched = await Promise.all(
    names.map((name) => Promise.all([recallsFor(under(name), signal, fetcher), complaintsFor(under(name), signal, fetcher)])),
  );
  const foundRecalls = new Map(names.map((name, i) => [name, fetched[i][0]]));
  const foundComplaints = new Map(names.map((name, i) => [name, fetched[i][1]]));

  const chosen = names.filter((name) => sameName(name, vehicle.model));
  const named = chosen.flatMap((name) => (foundComplaints.get(name) ?? []).flatMap((c) => (c.recordModel ? [c.recordModel] : [])));
  const models = identify(vehicle.model, named);
  // Every spelling the records use is searched: NHTSA files 2020 Mercedes-Benz recall 20V228000 under "E450",
  // while complaint records name both "E450" and "E 450".
  const matching = unique(named).filter((m) => models.some((o) => sameName(m, o)));
  const spellings = matching.length ? matching : models;
  // A shorter recall name counts only for a name NHTSA lists, or one its records name: for a typo no list
  // has ("MUSTANG MAH-E"), "MUSTANG" would be a guess, and the gasoline car's recalls the wrong answer.
  const trusted = named.length > 0 || listed.some((n) => sameName(vehicle.model, n));
  const ownNames = unique([...chosen, ...spellings.flatMap((m) => [m, ...closestRecallNames(m, recallFileNames, trusted)])]);
  const extra = ownNames.filter((name) => !foundRecalls.has(name)); // the records can point to a name not yet searched
  const more = await Promise.all(extra.map((name) => recallsFor(under(name), signal, fetcher)));
  extra.forEach((name, i) => foundRecalls.set(name, more[i]));
  // NHTSA's API files a few recalls under a shorter name that's in none of its lists: two 2023 F-150
  // Lightning recalls are under "F-150 LIGHTNING", not "F-150 LIGHTNING BEV" (checked Oct 3, 2026). So
  // shorter versions of the vehicle's recall names are searched too. Their recalls count as related,
  // because a shorter name can be a different vehicle ("F-150" is the gasoline truck).
  const recallStyle = new Set([...recallFileNames, ...named]);
  const shorter = unique(ownNames.filter((n) => recallStyle.has(n)).flatMap(shorterNames));
  const missing = shorter.filter((name) => !foundRecalls.has(name));
  const fromShorter = await Promise.all(missing.map((name) => recallsFor(under(name), signal, fetcher)));
  missing.forEach((name, i) => foundRecalls.set(name, fromShorter[i]));

  const own = new Map<string, Recall>();
  for (const name of ownNames) for (const r of foundRecalls.get(name) ?? []) if (!own.has(r.campaign)) own.set(r.campaign, r);
  const others = new Map<string, Recall>();
  for (const name of unique([...names, ...shorter])) {
    for (const r of foundRecalls.get(name) ?? []) if (!own.has(r.campaign) && !others.has(r.campaign)) others.set(r.campaign, r);
  }

  const mine = new Map<string, Complaint>();
  const leftOut: Record<string, number> = {};
  const seen = new Set<string>();
  // The chosen name's own search first, so its complaints are judged as such.
  for (const name of [...chosen, ...names.filter((n) => !chosen.includes(n))]) {
    const searchedFor = chosen.includes(name); // NHTSA's own search for the chosen name returned it
    for (const c of foundComplaints.get(name) ?? []) {
      if (seen.has(c.odiNumber)) continue;
      seen.add(c.odiNumber);
      const model = c.recordModel;
      const ownOne =
        model === null
          ? searchedFor
          : models.some((m) => sameName(model, m)) || (searchedFor && models.some((m) => within(m, model)));
      if (ownOne) mine.set(c.odiNumber, c);
      else if (model !== null && searchedFor) leftOut[model] = (leftOut[model] ?? 0) + 1;
    }
  }

  return {
    names: unique([...names, ...ownNames, ...shorter]),
    models,
    ownNames,
    recalls: [...own.values()],
    relatedRecalls: [...others.values()],
    complaints: [...mine.values()],
    leftOut,
  };
}

function unique(items: readonly string[]): string[] {
  return [...new Set(items)];
}
