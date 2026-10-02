// NHTSA's public API, called straight from the browser. What it does, checked on Oct 2, 2026:
//   - Plain GET requests work from any site (it echoes the site's origin in Access-Control-Allow-Origin).
//     Its pre-check for other requests (OPTIONS) answers 501, so these calls send no custom headers.
//   - A vehicle with no records comes back as HTTP 400 with an empty "results" list.
//   - Each complaint record includes a partial VIN. It's dropped here and never kept or shown.
//   - A recall lists one component, even when NHTSA's recall file lists several for the campaign.
import { parseDayFirst, parseMonthFirst } from "./dates";
import { normalize, normalizeAll, splitComponents } from "./labels";
import { scrub } from "./privacy";

export const API = "https://api.nhtsa.gov";

export interface Vehicle {
  year: string;
  make: string;
  model: string;
}

export interface Recall {
  campaign: string;
  received: string | null; // YYYY-MM-DD
  component: string; // as NHTSA lists it, e.g. "FUEL SYSTEM, GASOLINE:DELIVERY:FUEL PUMP"
  label: string | null;
  summary: string;
  consequence: string;
  remedy: string;
  doNotDrive: boolean;
  parkOutside: boolean;
  overTheAir: boolean;
  source: string;
  listedAs: string; // the model name it was found under
}

export interface Complaint {
  odiNumber: string;
  filed: string | null; // YYYY-MM-DD
  components: string[]; // as NHTSA lists them
  labels: string[];
  summary: string; // with emails, phone numbers, and full VINs masked
  crash: boolean;
  fire: boolean;
  injuries: number;
  deaths: number;
  source: string;
  listedAs: string; // the model name it was found under
}

export class NhtsaError extends Error {}

type Fetcher = (url: string, init?: { signal?: AbortSignal }) => Promise<Response>;
type Row = Record<string, unknown>;

const text = (value: unknown) => (typeof value === "string" ? value.trim() : value == null ? "" : String(value));
const count = (value: unknown) => (Number.isFinite(Number(value)) ? Number(value) : 0);
const query = (params: Record<string, string>) =>
  Object.entries(params)
    .map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
    .join("&");

async function results(path: string, signal?: AbortSignal, fetcher: Fetcher = fetch): Promise<Row[]> {
  let response: Response;
  try {
    response = await fetcher(`${API}${path}`, { signal }); // a plain GET: no headers, no body
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new NhtsaError("Couldn't reach NHTSA. Check your connection and try again.");
  }
  if (!response.ok && response.status !== 400) throw new NhtsaError(`NHTSA's server answered ${response.status}.`);
  let body: unknown;
  try {
    body = await response.json();
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new NhtsaError("NHTSA sent a reply this page couldn't read.");
  }
  const rows = (body as { results?: unknown; Results?: unknown } | null)?.results ?? (body as { Results?: unknown })?.Results;
  if (!Array.isArray(rows)) throw new NhtsaError("NHTSA sent a reply this page couldn't read.");
  if (!response.ok && rows.length) throw new NhtsaError(`NHTSA's server answered ${response.status}.`);
  return rows.filter((row): row is Row => typeof row === "object" && row !== null);
}

/** Values from both NHTSA lists (vehicles with complaints, and with recalls), without repeats. */
async function both(path: (issueType: string) => string, key: string, signal?: AbortSignal, fetcher?: Fetcher) {
  const lists = await Promise.all(["c", "r"].map((issueType) => results(path(issueType), signal, fetcher)));
  return [...new Set(lists.flat().map((row) => text(row[key])).filter(Boolean))];
}

/** Model years, newest first. NHTSA's placeholder year 9999 is left out. */
export async function modelYears(signal?: AbortSignal, fetcher?: Fetcher): Promise<string[]> {
  const years = await both((t) => `/products/vehicle/modelYears?issueType=${t}`, "modelYear", signal, fetcher);
  return years.filter((y) => /^\d{4}$/.test(y) && y !== "9999").sort((a, b) => Number(b) - Number(a));
}

export async function makes(year: string, signal?: AbortSignal, fetcher?: Fetcher): Promise<string[]> {
  const list = await both((t) => `/products/vehicle/makes?${query({ modelYear: year, issueType: t })}`, "make", signal, fetcher);
  return list.sort();
}

export async function models(year: string, make: string, signal?: AbortSignal, fetcher?: Fetcher): Promise<string[]> {
  const path = (t: string) => `/products/vehicle/models?${query({ modelYear: year, make, issueType: t })}`;
  return (await both(path, "model", signal, fetcher)).sort();
}

const vehicleQuery = (v: Vehicle) => query({ make: v.make, model: v.model, modelYear: v.year });

export function toRecall(row: Row, listedAs: string): Recall {
  const campaign = text(row.NHTSACampaignNumber);
  const component = text(row.Component);
  return {
    campaign,
    received: parseDayFirst(text(row.ReportReceivedDate)),
    component,
    label: normalize(component),
    summary: text(row.Summary),
    consequence: text(row.Consequence),
    remedy: text(row.Remedy),
    doNotDrive: row.parkIt === true,
    parkOutside: row.parkOutSide === true,
    overTheAir: row.overTheAirUpdate === true,
    source: `${API}/recalls/campaignNumber?${query({ campaignNumber: campaign })}`,
    listedAs,
  };
}

/** Only these fields are kept. The partial VIN and everything else in the record are dropped. */
export function toComplaint(row: Row, listedAs: string): Complaint {
  const odiNumber = text(row.odiNumber);
  const components = splitComponents(text(row.components));
  return {
    odiNumber,
    filed: parseMonthFirst(text(row.dateComplaintFiled)),
    components,
    labels: normalizeAll(components),
    summary: scrub(text(row.summary)),
    crash: row.crash === true,
    fire: row.fire === true,
    injuries: count(row.numberOfInjuries),
    deaths: count(row.numberOfDeaths),
    source: `${API}/complaints/odinumber?${query({ odinumber: odiNumber })}`,
    listedAs,
  };
}

/** The vehicle's recall campaigns (one entry per campaign). */
export async function recalls(vehicle: Vehicle, signal?: AbortSignal, fetcher?: Fetcher): Promise<Recall[]> {
  const rows = await results(`/recalls/recallsByVehicle?${vehicleQuery(vehicle)}`, signal, fetcher);
  const byCampaign = new Map<string, Recall>();
  for (const recall of rows.map((row) => toRecall(row, vehicle.model))) {
    if (recall.campaign && !byCampaign.has(recall.campaign)) byCampaign.set(recall.campaign, recall);
  }
  return [...byCampaign.values()];
}

export async function complaints(vehicle: Vehicle, signal?: AbortSignal, fetcher?: Fetcher): Promise<Complaint[]> {
  const rows = await results(`/complaints/complaintsByVehicle?${vehicleQuery(vehicle)}`, signal, fetcher);
  return rows.map((row) => toComplaint(row, vehicle.model)).filter((c) => c.odiNumber);
}

/**
 * Recalls and complaints for a vehicle under each of its model names (see vehicles.ts), in one list
 * each. A record found under several names is kept once, under the first name in the list.
 */
export async function records(vehicle: Vehicle, names: readonly string[], signal?: AbortSignal, fetcher?: Fetcher) {
  const found = await Promise.all(
    names.map((model) =>
      Promise.all([recalls({ ...vehicle, model }, signal, fetcher), complaints({ ...vehicle, model }, signal, fetcher)]),
    ),
  );
  return {
    recalls: firstOf(found.flatMap(([r]) => r), (r) => r.campaign),
    complaints: firstOf(found.flatMap(([, c]) => c), (c) => c.odiNumber),
  };
}

/** Each item once, keeping the first of any repeats and the original order. */
function firstOf<T>(items: T[], key: (item: T) => string): T[] {
  const kept = new Map<string, T>();
  for (const item of items) if (!kept.has(key(item))) kept.set(key(item), item);
  return [...kept.values()];
}
