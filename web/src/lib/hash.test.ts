import { describe, expect, it } from "vitest";
import { cleanAddress, readHash, vehicleHash } from "./hash";

describe("readHash", () => {
  it("reads the vehicle and description from a link", () => {
    expect(readHash("#year=2019&make=honda&model=cr-v&q=engine%20hesitates")).toEqual({
      year: "2019",
      make: "HONDA",
      model: "CR-V",
      description: "engine hesitates",
    });
    expect(readHash("")).toEqual({ year: undefined, make: undefined, model: undefined, description: undefined });
  });
});

describe("vehicleHash", () => {
  it("holds the vehicle only, never a description", () => {
    const hash = vehicleHash({ year: "2014", make: "JEEP", model: "GRAND CHEROKEE" });
    expect(hash).toBe("#year=2014&make=JEEP&model=GRAND+CHEROKEE");
    expect(readHash(hash)).toEqual({ year: "2014", make: "JEEP", model: "GRAND CHEROKEE", description: undefined });
  });
});

describe("cleanAddress", () => {
  const crv = { year: "2019", make: "HONDA", model: "CR-V" };
  const at = (hash: string) => ({ pathname: "/", search: "", hash });

  it("removes the description from a link once the page has read it", () => {
    expect(cleanAddress(crv, at("#year=2019&make=HONDA&model=CR-V&q=engine%20stalls"))).toBe("#year=2019&make=HONDA&model=CR-V");
  });

  it("changes nothing when the address already shows the vehicle", () => {
    expect(cleanAddress(crv, at("#year=2019&make=HONDA&model=CR-V"))).toBeNull();
  });

  it("clears the part after # while no full vehicle is chosen, even a description on its own", () => {
    expect(cleanAddress({ year: "2019" }, at("#q=engine%20stalls"))).toBe("/");
    expect(cleanAddress({}, at(""))).toBeNull();
  });
});
