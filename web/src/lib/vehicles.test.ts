// Vehicle names: the rules for related names, the recall-file index in public/vehicles/, how the
// picker's lists combine NHTSA's vehicle-list API with that index, and the search that sorts out which
// records are the vehicle's own. The cases mirror tests/test_vehicles.py, and fixtures/names.json
// (scripts/build_web_fixtures.py) holds the Python code's answers. Complaint rows are made up; the
// names are NHTSA's.
import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";
import { API, LIMITS, type Vehicle } from "./nhtsa";
import {
  closestRecallNames,
  identify,
  related,
  relatedNames,
  sameName,
  search,
  shorterNames,
  vehicleMakes,
  vehicleModels,
  within,
  words,
} from "./vehicles";

const publicDir = new URL("../../public/", import.meta.url);
const indexFile = (name: string) => JSON.parse(readFileSync(new URL(`vehicles/${name}`, publicDir), "utf8"));
const fixture = JSON.parse(readFileSync(new URL("./fixtures/names.json", import.meta.url), "utf8")) as {
  words: [string, string[]][];
  pairs: [string, string, boolean, boolean, boolean][];
  closest: [string, string[], string[]][];
  identify: [string, (string | null)[], string[]][];
  shorter: [string, string[]][];
};

describe("related", () => {
  it("links a name with the same name plus more words", () => {
    expect(related("AIR", "AIR BEV")).toBe(true);
    expect(related("F-150 SUPERCREW", "F-150")).toBe(true);
    expect(related("GRAND CHEROKEE", "GRAND CHEROKEE L")).toBe(true);
    expect(related("CR-V", "CR-V")).toBe(true);
    expect(related("MUSTANG MACH-E", "MUSTANG MACH E")).toBe(true); // spelled the same apart from punctuation
    expect(related("F-150 LIGHTNING BEV", "F-150 (SUPER CREW) LIGHTNING BEV")).toBe(true); // more words in between
  });

  it("keeps different models apart", () => {
    expect(related("MODEL 3", "MODEL Y")).toBe(false);
    expect(related("GRAND CHEROKEE", "GRAND WAGONEER")).toBe(false);
    expect(related("AIR", "AIRSTREAM")).toBe(false);
    expect(related("F-150 HYBRID", "F-150 (SUPER CREW) HEV")).toBe(false);
  });

  it("puts the chosen name first", () => {
    expect(relatedNames("AIR BEV", ["AIR", "AIR BEV", "GRAVITY", "GRAVITY BEV"])).toEqual(["AIR BEV", "AIR"]);
    expect(relatedNames("MODEL 3", ["MODEL 3", "MODEL S", "MODEL X", "MODEL Y"])).toEqual(["MODEL 3"]);
  });
});

describe("the name rules, the same as src/carsafety/vehicles.py", () => {
  it("treat names spelled the same apart from spaces and punctuation as one", () => {
    expect(words("F-150 (SUPER CREW) GAS")).toEqual(["F150", "SUPER", "CREW", "GAS"]);
    expect([sameName("MUSTANG MACH-E", "MUSTANG MACH E"), sameName("CR-V", "crv"), sameName("ID.4", "ID 4")]).toEqual([true, true, true]);
    expect([sameName("MODEL 3", "MODEL Y"), sameName("", ""), sameName("-", "")]).toEqual([false, false, false]);
  });

  it("need more words, in order, starting with the same word", () => {
    expect([within("AIR", "AIR BEV"), within("F-150 LIGHTNING BEV", "F-150 (SUPER CREW) LIGHTNING BEV")]).toEqual([true, true]);
    expect([within("AIR BEV", "AIR"), within("AIR", "AIR")]).toEqual([false, false]); // not more words
    expect(within("LIGHTNING BEV", "F-150 LIGHTNING BEV")).toBe(false); // another first word
    expect(within("F-150 BEV LIGHTNING", "F-150 LIGHTNING BEV")).toBe(false); // another order
  });

  it("pick the most specific recall names, and the model the complaint records name", () => {
    const names = ["F-150", "F-150 LIGHTNING BEV", "MUSTANG", "MUSTANG MACH E"];
    expect(closestRecallNames("F-150 (SUPER CREW) LIGHTNING BEV", names)).toEqual(["F-150 LIGHTNING BEV"]);
    expect(closestRecallNames("F-150 (SUPER CREW) HEV", names)).toEqual(["F-150"]);
    expect(closestRecallNames("MUSTANG MACH-E", names)).toEqual(["MUSTANG MACH E"]);
    // A name in no list: the one recall-file name that is it with more words beats a shorter one.
    expect(closestRecallNames("F-150 LIGHTNING", names)).toEqual(["F-150 LIGHTNING BEV"]);
    expect(closestRecallNames("GRAND CHEROKEE", ["GRAND CHEROKEE L", "GRAND CHEROKEE 4XE"])).toEqual([]); // two: no guess
    expect(shorterNames("F-150 LIGHTNING BEV")).toEqual(["F-150 LIGHTNING"]);
    expect(shorterNames("SONATA PLUG-IN HYBRID TOURING")).toEqual(["SONATA PLUG-IN HYBRID", "SONATA PLUG-IN"]);
    expect([shorterNames("AIR BEV"), shorterNames("CR-V")]).toEqual([[], []]);
    expect(identify("F-150 (SUPER CREW) LIGHTNING BEV", ["F-150 LIGHTNING BEV", "F-150 HYBRID"])).toEqual(["F-150 LIGHTNING BEV"]);
    expect(identify("F-150 (SUPER CREW) HEV", ["F-150 HYBRID"])).toEqual(["F-150 HYBRID"]); // no name fits, so the records are trusted
    expect(identify("AIR", [])).toEqual(["AIR"]);
  });

  it("give the Python code's answers for every case in fixtures/names.json", () => {
    for (const [name, expected] of fixture.words) expect(words(name), name).toEqual(expected);
    for (const [a, b, ...expected] of fixture.pairs) expect([sameName(a, b), within(a, b), related(a, b)], `${a} | ${b}`).toEqual(expected);
    for (const [name, names, expected] of fixture.closest) expect(closestRecallNames(name, names), name).toEqual(expected);
    for (const [chosen, models, expected] of fixture.identify) expect(identify(chosen, models), chosen).toEqual(expected);
    for (const [name, expected] of fixture.shorter) expect(shorterNames(name), name).toEqual(expected);
  });
});

describe("the recall-file index", () => {
  it("has the names NHTSA's vehicle-list API misses", () => {
    expect(indexFile("years.json")).toEqual(expect.arrayContaining(["2026", "2025", "2019"]));
    expect(indexFile("2026.json").LUCID).toEqual(expect.arrayContaining(["AIR", "GRAVITY"]));
    expect(indexFile("2025.json").ISUZU).toEqual(expect.arrayContaining(["NPR HD", "FTR"]));
    expect(indexFile("2019.json").HONDA).toContain("CR-V");
  });
});

describe("picker lists", () => {
  afterEach(() => vi.unstubAllGlobals());

  // NHTSA's API for vehicle lists is replaced; the index files are read from public/.
  function stubFetch(api: (url: string) => Response) {
    vi.stubGlobal("fetch", async (url: string) => {
      if (url.startsWith("https://api.nhtsa.gov")) return api(url);
      const file = new URL(url.replace(/^\//, ""), publicDir);
      return new Response(readFileSync(file));
    });
  }

  it("combine both sources in capitals without repeats", async () => {
    stubFetch((url) =>
      url.includes("make=LUCID")
        ? new Response(JSON.stringify({ results: [{ model: "AIR BEV" }, { model: "Air Bev" }, { model: "GRAVITY BEV" }] }))
        : new Response(JSON.stringify({ results: [] }), { status: 400 }),
    );
    expect(await vehicleModels("2026", "LUCID")).toEqual(["AIR", "AIR BEV", "GRAVITY", "GRAVITY BEV"]);
  });

  it("don't keep a model list made while NHTSA's list failed, so a second look gets NHTSA's names", async () => {
    // Before Oct 9, 2026, the partial list was kept for the visit, so names only NHTSA has (AIR BEV) disappeared.
    const saved = LIMITS.retryMs;
    LIMITS.retryMs = 0;
    let nhtsaUp = false;
    stubFetch((url) => {
      if (!nhtsaUp) throw new TypeError("Failed to fetch");
      return new Response(JSON.stringify({ results: url.includes("make=RIVIAN") ? [{ model: "ONLY IN NHTSA'S LIST" }] : [] }));
    });
    try {
      expect(await vehicleModels("2024", "RIVIAN")).toEqual(["EDV", "R1S", "R1T"]); // the index alone
      nhtsaUp = true;
      expect(await vehicleModels("2024", "RIVIAN")).toEqual(["EDV", "ONLY IN NHTSA'S LIST", "R1S", "R1T"]);
    } finally {
      LIMITS.retryMs = saved;
    }
  });

  it("still work from the index when NHTSA's list can't be reached", async () => {
    stubFetch(() => {
      throw new TypeError("Failed to fetch");
    });
    expect(await vehicleModels("2025", "ISUZU")).toEqual(expect.arrayContaining(["NPR HD", "FTR"]));
    expect(await vehicleMakes("2025")).toContain("ISUZU");
  });
});

describe("search", () => {
  // A stand-in for NHTSA's server: path -> rows. Anything else gets NHTSA's answer for no records.
  function server(routes: Record<string, unknown[]>) {
    const calls: string[] = [];
    const fetcher = async (url: string) => {
      const path = url.replace(API, "");
      calls.push(path);
      const rows = routes[path];
      return rows ? new Response(JSON.stringify({ results: rows })) : new Response(JSON.stringify({ results: [] }), { status: 400 });
    };
    return { fetcher, calls };
  }
  const at = (year: string, make: string, model: string): Vehicle => ({ year, make, model });
  const path = (kind: "recalls" | "complaints", v: Vehicle) =>
    `/${kind}/${kind}ByVehicle?make=${encodeURIComponent(v.make)}&model=${encodeURIComponent(v.model)}&modelYear=${v.year}`;
  const recall = (campaign: string, flags: Record<string, unknown> = {}) => ({
    NHTSACampaignNumber: campaign,
    ReportReceivedDate: "06/01/2025",
    Component: "ELECTRICAL SYSTEM",
    Summary: "Summary.",
    Consequence: "Risk.",
    Remedy: "Fix.",
    parkIt: false,
    parkOutSide: false,
    overTheAirUpdate: false,
    ...flags,
  });
  // A made-up complaint whose record names `model`.
  const complaint = (odiNumber: number, v: Vehicle) => ({
    odiNumber,
    dateComplaintFiled: "09/01/2025",
    components: "ELECTRICAL SYSTEM",
    summary: "It stopped.",
    products: [{ type: "Vehicle", productYear: v.year, productMake: v.make, productModel: v.model }],
  });
  const mustangs = ["MUSTANG", "MUSTANG GT 500", "MUSTANG MACH E", "MUSTANG MACH-E"];
  const f150s = [
    "F-150",
    "F-150 (REGULAR CAB) GAS",
    "F-150 (SUPER CAB) GAS",
    "F-150 (SUPER CREW) GAS",
    "F-150 (SUPER CREW) HEV",
    "F-150 (SUPER CREW) LIGHTNING BEV",
    "F-150 LIGHTNING BEV",
  ];

  it("gives the Mach-E its own recalls, not the gasoline Mustang's, and the other way round", async () => {
    // 2022 Ford (checked Oct 3, 2026): Mach-E complaints are found under MUSTANG MACH-E and name MUSTANG MACH E,
    // the name its recalls are filed under. MUSTANG is the gasoline car.
    const ford = (model: string) => at("2022", "FORD", model);
    const { fetcher } = server({
      [path("complaints", ford("MUSTANG MACH-E"))]: [complaint(1, ford("MUSTANG MACH E")), complaint(2, ford("MUSTANG MACH E"))],
      [path("recalls", ford("MUSTANG MACH E"))]: [recall("22V412000")],
      [path("complaints", ford("MUSTANG"))]: [complaint(3, ford("MUSTANG"))],
      [path("recalls", ford("MUSTANG"))]: [recall("22V083000")],
    });
    const machE = await search(ford("MUSTANG MACH-E"), mustangs, ["MUSTANG", "MUSTANG MACH E"], undefined, fetcher);
    expect(machE.models).toEqual(["MUSTANG MACH E"]);
    expect(machE.recalls.map((r) => [r.campaign, r.listedAs])).toEqual([["22V412000", "MUSTANG MACH E"]]);
    expect(machE.relatedRecalls.map((r) => [r.campaign, r.listedAs])).toEqual([["22V083000", "MUSTANG"]]);
    expect(machE.complaints.map((c) => c.odiNumber)).toEqual(["1", "2"]);
    expect(machE.leftOut).toEqual({});
    const mustang = await search(ford("MUSTANG"), mustangs, ["MUSTANG", "MUSTANG MACH E"], undefined, fetcher);
    expect(mustang.recalls.map((r) => r.campaign)).toEqual(["22V083000"]);
    expect(mustang.relatedRecalls.map((r) => r.campaign)).toEqual(["22V412000"]);
    expect(mustang.complaints.map((c) => c.odiNumber)).toEqual(["3"]);
  });

  it("leaves out another model's complaints that a search returns", async () => {
    // 2023 Ford (checked Oct 3, 2026): the "F-150 (SUPER CREW) LIGHTNING BEV" search returns Lightning complaints and
    // F-150 HYBRID complaints. Lightning recalls are filed under F-150 LIGHTNING BEV; F-150 is the gasoline truck.
    const ford = (model: string) => at("2023", "FORD", model);
    const lightning = "F-150 (SUPER CREW) LIGHTNING BEV";
    const { fetcher } = server({
      [path("complaints", ford(lightning))]: [
        complaint(1, ford("F-150 LIGHTNING BEV")),
        complaint(2, ford("F-150 HYBRID")),
        complaint(3, ford("F-150 LIGHTNING BEV")),
      ],
      [path("recalls", ford("F-150 LIGHTNING BEV"))]: [recall("23V900001")],
      [path("recalls", ford("F-150"))]: [recall("23V900002")],
    });
    const found = await search(ford(lightning), f150s, ["F-150", "F-150 LIGHTNING BEV"], undefined, fetcher);
    expect(found.names).toEqual([lightning, "F-150", "F-150 LIGHTNING BEV", "F-150 LIGHTNING"]); // the last, a shorter version
    expect(found.models).toEqual(["F-150 LIGHTNING BEV"]);
    expect(found.recalls.map((r) => r.campaign)).toEqual(["23V900001"]);
    expect(found.relatedRecalls.map((r) => r.campaign)).toEqual(["23V900002"]);
    expect(found.complaints.map((c) => c.odiNumber)).toEqual(["1", "3"]);
    expect(found.leftOut).toEqual({ "F-150 HYBRID": 1 });
  });

  it("keeps versions of the model that its own search returns", async () => {
    // The 2015 "FUSION HEV" search returns FUSION, FUSION HYBRID, and FUSION ENERGI complaints (checked Oct 3, 2026).
    const ford = (model: string) => at("2015", "FORD", model);
    const { fetcher } = server({
      [path("complaints", ford("FUSION HEV"))]: [
        complaint(1, ford("FUSION")),
        complaint(2, ford("FUSION HYBRID")),
        complaint(3, ford("FUSION ENERGI")),
        complaint(4, ford("ESCAPE")),
      ],
      [path("complaints", ford("FUSION"))]: [complaint(5, ford("FUSION HYBRID"))],
    });
    const found = await search(ford("FUSION HEV"), ["FUSION", "FUSION HEV"], ["FUSION", "FUSION ENERGI", "FUSION HYBRID"], undefined, fetcher);
    expect(found.models).toEqual(["FUSION"]);
    expect(found.complaints.map((c) => c.odiNumber)).toEqual(["1", "2", "3"]);
    expect(found.leftOut).toEqual({ ESCAPE: 1 });
  });

  it("searches a name the records point to, even when no list relates it", async () => {
    // The 2023 "F-150 (SUPER CREW) HEV" complaints name the F-150 HYBRID, which has no recalls of its own; its
    // recalls are filed under F-150, the closest recall-file name (checked Oct 3, 2026).
    const ford = (model: string) => at("2023", "FORD", model);
    const hev = "F-150 (SUPER CREW) HEV";
    const { fetcher, calls } = server({
      [path("complaints", ford(hev))]: [complaint(1, ford("F-150 HYBRID"))],
      [path("recalls", ford("F-150"))]: [recall("23V900002")],
    });
    const found = await search(ford(hev), f150s, ["F-150", "F-150 LIGHTNING BEV"], undefined, fetcher);
    expect(found.models).toEqual(["F-150 HYBRID"]);
    expect(calls).toContain(path("recalls", ford("F-150 HYBRID")));
    expect(found.recalls.map((r) => [r.campaign, r.listedAs])).toEqual([["23V900002", "F-150"]]);
    expect(found.relatedRecalls).toEqual([]);
    expect(found.complaints.map((c) => c.odiNumber)).toEqual(["1"]);
  });

  it("searches every spelling the complaint records use", async () => {
    // 2020 Mercedes-Benz (checked Oct 3, 2026): E-CLASS complaint records name both "E 450" and "E450", and NHTSA's API
    // files recall 20V228000 under "E450" only. The made-up campaign stands in for it.
    const benz = (model: string) => at("2020", "MERCEDES-BENZ", model);
    const { fetcher, calls } = server({
      [path("complaints", benz("E-CLASS"))]: [complaint(1, benz("E 450")), complaint(2, benz("E450"))],
      [path("recalls", benz("E450"))]: [recall("20V900001")],
    });
    const found = await search(benz("E-CLASS"), ["E-CLASS"], ["E 450"], undefined, fetcher);
    expect(found.models).toEqual(["E 450"]); // shown once
    expect(calls).toContain(path("recalls", benz("E450")));
    expect(found.recalls.map((r) => [r.campaign, r.listedAs])).toEqual([["20V900001", "E450"]]);
    expect(found.complaints.map((c) => c.odiNumber)).toEqual(["1", "2"]);
  });

  it("gives a name in no list the recall name it shortens, not a shorter one", async () => {
    // "F-150 LIGHTNING" is in neither NHTSA's vehicle list nor its recall file, and has no complaints. NHTSA's API
    // files two Lightning recalls under it, and the rest under F-150 LIGHTNING BEV (checked Oct 3, 2026). F-150 is
    // the gasoline truck. The campaigns here are made up.
    const ford = (model: string) => at("2023", "FORD", model);
    const { fetcher } = server({
      [path("recalls", ford("F-150 LIGHTNING"))]: [recall("23V900003")],
      [path("recalls", ford("F-150 LIGHTNING BEV"))]: [recall("23V900001")],
      [path("recalls", ford("F-150"))]: [recall("23V900002")],
    });
    const found = await search(ford("F-150 LIGHTNING"), f150s, ["F-150", "F-150 LIGHTNING BEV"], undefined, fetcher);
    expect(found.recalls.map((r) => [r.campaign, r.listedAs])).toEqual([
      ["23V900003", "F-150 LIGHTNING"],
      ["23V900001", "F-150 LIGHTNING BEV"],
    ]);
    expect(found.relatedRecalls.map((r) => [r.campaign, r.listedAs])).toEqual([["23V900002", "F-150"]]);
  });

  it("lists recalls under a shorter version of the name apart", async () => {
    // Picking the trim, the two recalls under "F-150 LIGHTNING" are found through the shorter name and kept apart.
    const ford = (model: string) => at("2023", "FORD", model);
    const lightning = "F-150 (SUPER CREW) LIGHTNING BEV";
    const { fetcher, calls } = server({
      [path("complaints", ford(lightning))]: [complaint(1, ford("F-150 LIGHTNING BEV"))],
      [path("recalls", ford("F-150 LIGHTNING BEV"))]: [recall("23V900001")],
      [path("recalls", ford("F-150 LIGHTNING"))]: [recall("23V900003")],
    });
    const found = await search(ford(lightning), f150s, ["F-150", "F-150 LIGHTNING BEV"], undefined, fetcher);
    expect(calls).toContain(path("recalls", ford("F-150 LIGHTNING")));
    expect(found.recalls.map((r) => r.campaign)).toEqual(["23V900001"]);
    expect(found.relatedRecalls.map((r) => [r.campaign, r.listedAs])).toEqual([["23V900003", "F-150 LIGHTNING"]]);
  });

  it("doesn't give a typo no list has a shorter name's recalls", async () => {
    // qwen3 typed "MUSTANG MAH-E" in the tool-use evaluation (Oct 3, 2026). It's in no list and has no records,
    // so "MUSTANG", the gasoline car, would be a guess: its recalls stay apart, and none is the vehicle's own.
    const ford = (model: string) => at("2022", "FORD", model);
    let { fetcher } = server({ [path("recalls", ford("MUSTANG"))]: [recall("22V900002")] });
    const typo = await search(ford("MUSTANG MAH-E"), mustangs, ["MUSTANG", "MUSTANG MACH E"], undefined, fetcher);
    expect(typo.recalls).toEqual([]);
    expect(typo.relatedRecalls.map((r) => r.campaign)).toEqual(["22V900002"]);
    // A name NHTSA lists keeps the shorter name: the Lucid's AIR BEV, with no complaints, still gets AIR's recalls.
    const lucid = (model: string) => at("2026", "LUCID", model);
    ({ fetcher } = server({ [path("recalls", lucid("AIR"))]: [recall("26V540000")] }));
    const air = await search(lucid("AIR BEV"), ["AIR", "AIR BEV"], ["AIR"], undefined, fetcher);
    expect(air.recalls.map((r) => r.campaign)).toEqual(["26V540000"]);
  });

  it("finds the complaints filed under the list's name for a recall-file name", async () => {
    // For the 2026 Lucid AIR, complaints are found under the vehicle list's AIR BEV and name AIR (checked Oct 3, 2026).
    const lucid = (model: string) => at("2026", "LUCID", model);
    const { fetcher } = server({
      [path("complaints", lucid("AIR BEV"))]: [complaint(1, lucid("AIR"))],
      [path("recalls", lucid("AIR"))]: [recall("26V540000", { parkOutSide: true })],
    });
    const found = await search(lucid("AIR"), ["AIR", "AIR BEV", "GRAVITY", "GRAVITY BEV"], ["AIR", "GRAVITY"], undefined, fetcher);
    expect(found.models).toEqual(["AIR"]);
    expect(found.recalls.map((r) => [r.campaign, r.parkOutside])).toEqual([["26V540000", true]]);
    expect(found.complaints.map((c) => [c.odiNumber, c.listedAs])).toEqual([["1", "AIR BEV"]]);
  });
});
