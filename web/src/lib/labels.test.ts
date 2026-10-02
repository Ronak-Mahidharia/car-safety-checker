// The labels must match src/carsafety/labels.py: the fixture holds the Python answers
// (scripts/build_web_fixtures.py) for every component name in NHTSA's complaint and recall files.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { displayName, normalize, normalizeAll, splitComponents } from "./labels";

const fixture = JSON.parse(readFileSync(new URL("./fixtures/labels.json", import.meta.url), "utf8")) as {
  normalize: [string, string | null][];
  split: [string, string[]][];
};

describe("normalize", () => {
  it("gives the same label as the Python version for every NHTSA component name", () => {
    expect(fixture.normalize.length).toBeGreaterThanOrEqual(800);
    expect(fixture.normalize.filter(([name, label]) => normalize(name) !== label)).toEqual([]);
  });

  it("merges old names and drops unknowns", () => {
    expect(normalize("ENGINE AND ENGINE COOLING:COOLING SYSTEM")).toBe("ENGINE");
    expect(normalize("FUEL SYSTEM, GASOLINE:DELIVERY:FUEL PUMP")).toBe("FUEL/PROPULSION SYSTEM");
    expect(normalize("UNKNOWN OR OTHER")).toBeNull();
  });
});

describe("splitComponents", () => {
  it("splits the complaints API's lists the same way as the Python rule", () => {
    expect(fixture.split.length).toBeGreaterThan(100);
    expect(fixture.split.filter(([value, parts]) => splitComponents(value).join("|") !== parts.join("|"))).toEqual([]);
  });

  it("keeps names that contain a comma in one piece", () => {
    expect(splitComponents("SERVICE BRAKES,FORWARD COLLISION AVOIDANCE")).toEqual(["SERVICE BRAKES", "FORWARD COLLISION AVOIDANCE"]);
    expect(splitComponents("ENGINE,FUEL SYSTEM, GASOLINE")).toEqual(["ENGINE", "FUEL SYSTEM, GASOLINE"]);
    expect(splitComponents("")).toEqual([]);
  });
});

describe("normalizeAll", () => {
  it("returns sorted, unique labels without unknowns", () => {
    expect(normalizeAll(["VISIBILITY", "UNKNOWN OR OTHER", "ENGINE AND ENGINE COOLING", "ENGINE"])).toEqual(["ENGINE", "VISIBILITY/WIPER"]);
  });
});

describe("displayName", () => {
  it("makes NHTSA's capitalized names easier to read", () => {
    expect(displayName("SERVICE BRAKES")).toBe("Service brakes");
    expect(displayName("ELECTRONIC STABILITY CONTROL (ESC)")).toBe("Electronic stability control (ESC)");
    expect(displayName("FUEL/PROPULSION SYSTEM")).toBe("Fuel/propulsion system");
    expect(displayName("FIRERELATED")).toBe("Fire-related");
  });
});
