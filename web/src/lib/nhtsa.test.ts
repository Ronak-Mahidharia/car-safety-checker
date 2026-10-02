// The API client, tested against a stand-in for NHTSA's server. The recall rows are shortened copies
// of real public records (checked Oct 2, 2026); the complaint rows are made up.
import { describe, expect, it } from "vitest";
import { API, complaints, makes, modelYears, models, NhtsaError, recalls, records, type Vehicle } from "./nhtsa";

type Route = { status?: number; body: unknown };

function server(routes: Record<string, Route>) {
  const calls: { url: string; init?: Record<string, unknown> }[] = [];
  const fetcher = async (url: string, init?: { signal?: AbortSignal }) => {
    calls.push({ url, init });
    const route = routes[url.replace(API, "")];
    if (!route) return new Response("not found", { status: 404 });
    return new Response(JSON.stringify(route.body), { status: route.status ?? 200 });
  };
  return { fetcher, calls };
}

const crv: Vehicle = { year: "2019", make: "HONDA", model: "CR-V" };
const crvQuery = "make=HONDA&model=CR-V&modelYear=2019";

const recallRow = (fields: Record<string, unknown>) => ({
  Manufacturer: "Example",
  parkIt: false,
  parkOutSide: false,
  overTheAirUpdate: false,
  Summary: "Summary.",
  Consequence: "Consequence.",
  Remedy: "Remedy.",
  Notes: "Notes.",
  ...fields,
});

describe("requests", () => {
  it("are plain GETs with no headers, so the browser needs no pre-check", async () => {
    const { fetcher, calls } = server({
      "/products/vehicle/modelYears?issueType=c": { body: { results: [{ modelYear: "2019" }] } },
      "/products/vehicle/modelYears?issueType=r": { body: { results: [{ modelYear: "2019" }] } },
    });
    await modelYears(undefined, fetcher);
    expect(calls).toHaveLength(2);
    for (const { init } of calls) expect(Object.entries(init ?? {}).filter(([, value]) => value !== undefined)).toEqual([]);
  });

  it("encode spaces and symbols in names", async () => {
    const { fetcher, calls } = server({});
    await expect(recalls({ year: "2014", make: "JEEP", model: "GRAND CHEROKEE" }, undefined, fetcher)).rejects.toThrow();
    expect(calls[0].url).toBe(`${API}/recalls/recallsByVehicle?make=JEEP&model=GRAND%20CHEROKEE&modelYear=2014`);
  });
});

describe("answers", () => {
  it("treat NHTSA's 400 'no records' reply as an empty list", async () => {
    const empty = { status: 400, body: { Count: 0, Message: "Results returned successfully", results: [] } };
    const { fetcher } = server({ [`/recalls/recallsByVehicle?${crvQuery}`]: empty });
    expect(await recalls(crv, undefined, fetcher)).toEqual([]);
  });

  it("report other failures as errors", async () => {
    const { fetcher } = server({ [`/recalls/recallsByVehicle?${crvQuery}`]: { status: 500, body: {} } });
    await expect(recalls(crv, undefined, fetcher)).rejects.toBeInstanceOf(NhtsaError);
    const offline = async () => {
      throw new TypeError("Failed to fetch");
    };
    await expect(recalls(crv, undefined, offline)).rejects.toBeInstanceOf(NhtsaError);
  });
});

describe("vehicle lists", () => {
  it("combine both lists: years newest first without 9999, makes and models without repeats", async () => {
    const { fetcher } = server({
      "/products/vehicle/modelYears?issueType=c": { body: { results: [{ modelYear: "2018" }, { modelYear: "9999" }, { modelYear: "2027" }] } },
      "/products/vehicle/modelYears?issueType=r": { body: { results: [{ modelYear: "2019" }, { modelYear: "2018" }] } },
      "/products/vehicle/makes?modelYear=2015&issueType=c": { body: { results: [{ make: "FORD" }, { make: "ACURA" }] } },
      "/products/vehicle/makes?modelYear=2015&issueType=r": { body: { results: [{ make: "FORD" }, { make: "MERCEDES-BENZ" }] } },
      "/products/vehicle/models?modelYear=2015&make=FORD&issueType=c": { body: { results: [{ model: "FLEX" }, { model: "FLEX" }] } },
      "/products/vehicle/models?modelYear=2015&make=FORD&issueType=r": { status: 400, body: { results: [] } },
    });
    expect(await modelYears(undefined, fetcher)).toEqual(["2027", "2019", "2018"]);
    expect(await makes("2015", undefined, fetcher)).toEqual(["ACURA", "FORD", "MERCEDES-BENZ"]);
    expect(await models("2015", "FORD", undefined, fetcher)).toEqual(["FLEX"]);
  });
});

describe("recalls", () => {
  it("read day-first dates, advisories, the label, and a link to the record", async () => {
    const { fetcher } = server({
      [`/recalls/recallsByVehicle?${crvQuery}`]: {
        body: {
          Count: 3,
          results: [
            recallRow({ NHTSACampaignNumber: "19V865000", ReportReceivedDate: "05/12/2019", Component: "STRUCTURE:FRAME AND MEMBERS" }),
            recallRow({ NHTSACampaignNumber: "26V517000", ReportReceivedDate: "06/08/2026", Component: "SERVICE BRAKES, HYDRAULIC", parkIt: true }),
            recallRow({ NHTSACampaignNumber: "26V540000", ReportReceivedDate: "20/08/2026", Component: "ELECTRICAL SYSTEM:SOFTWARE", parkOutSide: true }),
            recallRow({ NHTSACampaignNumber: "19V865000", ReportReceivedDate: "05/12/2019", Component: "STRUCTURE" }),
          ],
        },
      },
    });
    const [frame, brakes, software, ...rest] = await recalls(crv, undefined, fetcher);
    expect(rest).toEqual([]); // the repeated campaign is listed once
    expect(frame).toMatchObject({ campaign: "19V865000", received: "2019-12-05", label: "STRUCTURE", doNotDrive: false, parkOutside: false });
    expect(frame.source).toBe(`${API}/recalls/campaignNumber?campaignNumber=19V865000`);
    expect(brakes).toMatchObject({ received: "2026-08-06", label: "SERVICE BRAKES", doNotDrive: true, parkOutside: false });
    expect(software).toMatchObject({ received: "2026-08-20", label: "ELECTRICAL SYSTEM", doNotDrive: false, parkOutside: true });
  });
});

describe("complaints", () => {
  const partialVin = "1ABCD23EFG4";
  const row = {
    odiNumber: 12345678,
    manufacturer: "Example Motors",
    crash: true,
    fire: false,
    numberOfInjuries: 2,
    numberOfDeaths: 0,
    dateOfIncident: "07/17/2026",
    dateComplaintFiled: "09/29/2026",
    vin: partialVin,
    components: "SERVICE BRAKES,FUEL SYSTEM, GASOLINE,UNKNOWN OR OTHER",
    summary: "BRAKES FAILED. CALL ME AT 555-123-4567 OR JOHN@EXAMPLE.COM. VIN 1HGCM82633A004352.",
    products: [{ type: "Vehicle", productYear: "2019", productMake: "HONDA", productModel: "CR-V" }],
  };

  it("keep only what the page shows: no partial VIN, and personal details masked", async () => {
    const { fetcher } = server({ [`/complaints/complaintsByVehicle?${crvQuery}`]: { body: { count: 1, results: [row] } } });
    const [complaint] = await complaints(crv, undefined, fetcher);
    expect(Object.keys(complaint).sort()).toEqual(
      ["components", "crash", "deaths", "filed", "fire", "injuries", "labels", "listedAs", "odiNumber", "source", "summary"].sort(),
    );
    expect(JSON.stringify(complaint)).not.toContain(partialVin);
    // The period after the email is masked with it, exactly as the Python version does.
    expect(complaint.summary).toBe("BRAKES FAILED. CALL ME AT [removed] OR [removed] VIN [removed].");
    expect(complaint).toMatchObject({
      odiNumber: "12345678",
      filed: "2026-09-29",
      components: ["SERVICE BRAKES", "FUEL SYSTEM, GASOLINE", "UNKNOWN OR OTHER"],
      labels: ["FUEL/PROPULSION SYSTEM", "SERVICE BRAKES"],
      crash: true,
      fire: false,
      injuries: 2,
      deaths: 0,
      source: `${API}/complaints/odinumber?odinumber=12345678`,
      listedAs: "CR-V",
    });
  });
});

describe("records under several model names", () => {
  // The 2026 Lucid Air: recalls are filed under "AIR" and complaints under "AIR BEV" (checked Oct 2, 2026).
  const lucid: Vehicle = { year: "2026", make: "LUCID", model: "AIR BEV" };
  const empty = { status: 400, body: { results: [] } };
  const complaintRow = (odiNumber: number) => ({ odiNumber, dateComplaintFiled: "09/01/2026", components: "ELECTRICAL SYSTEM", summary: "Screen went black." });

  it("searches every name, keeps each record once, and notes the name it was filed under", async () => {
    const { fetcher, calls } = server({
      "/recalls/recallsByVehicle?make=LUCID&model=AIR%20BEV&modelYear=2026": empty,
      "/complaints/complaintsByVehicle?make=LUCID&model=AIR%20BEV&modelYear=2026": { body: { results: [complaintRow(111), complaintRow(222)] } },
      "/recalls/recallsByVehicle?make=LUCID&model=AIR&modelYear=2026": {
        body: { results: [recallRow({ NHTSACampaignNumber: "26V540000", ReportReceivedDate: "20/08/2026", Component: "ELECTRICAL SYSTEM:SOFTWARE", parkOutSide: true })] },
      },
      "/complaints/complaintsByVehicle?make=LUCID&model=AIR&modelYear=2026": { body: { results: [complaintRow(222)] } },
    });
    const found = await records(lucid, ["AIR BEV", "AIR"], undefined, fetcher);
    expect(calls).toHaveLength(4);
    expect(found.recalls.map((r) => [r.campaign, r.listedAs, r.parkOutside])).toEqual([["26V540000", "AIR", true]]);
    expect(found.complaints.map((c) => [c.odiNumber, c.listedAs])).toEqual([["111", "AIR BEV"], ["222", "AIR BEV"]]);
  });
});
