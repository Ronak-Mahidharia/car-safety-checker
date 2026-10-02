// Vehicle names: the related-name rule, the recall-file index in public/vehicles/, and how the
// picker's lists combine NHTSA's vehicle-list API with that index.
import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";
import { related, relatedNames, vehicleMakes, vehicleModels } from "./vehicles";

const publicDir = new URL("../../public/", import.meta.url);
const indexFile = (name: string) => JSON.parse(readFileSync(new URL(`vehicles/${name}`, publicDir), "utf8"));

describe("related", () => {
  it("links a name with the same name plus more words", () => {
    expect(related("AIR", "AIR BEV")).toBe(true);
    expect(related("F-150 SUPERCREW", "F-150")).toBe(true);
    expect(related("GRAND CHEROKEE", "GRAND CHEROKEE L")).toBe(true);
    expect(related("CR-V", "CR-V")).toBe(true);
  });

  it("keeps different models apart", () => {
    expect(related("MODEL 3", "MODEL Y")).toBe(false);
    expect(related("GRAND CHEROKEE", "GRAND WAGONEER")).toBe(false);
    expect(related("AIR", "AIRSTREAM")).toBe(false);
  });

  it("puts the chosen name first", () => {
    expect(relatedNames("AIR BEV", ["AIR", "AIR BEV", "GRAVITY", "GRAVITY BEV"])).toEqual(["AIR BEV", "AIR"]);
    expect(relatedNames("MODEL 3", ["MODEL 3", "MODEL S", "MODEL X", "MODEL Y"])).toEqual(["MODEL 3"]);
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

  it("still work from the index when NHTSA's list can't be reached", async () => {
    stubFetch(() => {
      throw new TypeError("Failed to fetch");
    });
    expect(await vehicleModels("2025", "ISUZU")).toEqual(expect.arrayContaining(["NPR HD", "FTR"]));
    expect(await vehicleMakes("2025")).toContain("ISUZU");
  });
});
