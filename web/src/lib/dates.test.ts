import { describe, expect, it } from "vitest";
import { formatDate, parseDayFirst, parseMonthFirst } from "./dates";

describe("recall dates (day/month/year)", () => {
  it("matches the dates in NHTSA's recall file", () => {
    // From the API for a 2019 Honda CR-V, next to RCDATE in FLAT_RCL_POST_2010.txt (checked Oct 2, 2026).
    expect(parseDayFirst("05/12/2019")).toBe("2019-12-05"); // 19V865000, RCDATE 20191205
    expect(parseDayFirst("25/03/2021")).toBe("2021-03-25"); // 21V215000, RCDATE 20210325
    expect(parseDayFirst("21/05/2026")).toBe("2026-05-21"); // 26V332000, RCDATE 20260521
  });
});

describe("complaint dates (month/day/year)", () => {
  it("reads month first", () => {
    expect(parseMonthFirst("09/29/2026")).toBe("2026-09-29");
    expect(parseMonthFirst("01/02/2025")).toBe("2025-01-02");
  });
});

describe("bad dates", () => {
  it("are rejected rather than guessed", () => {
    expect(parseDayFirst("31/02/2024")).toBeNull();
    expect(parseMonthFirst("13/01/2024")).toBeNull();
    expect(parseMonthFirst("2024-01-15")).toBeNull();
    expect(parseDayFirst("")).toBeNull();
  });
});

describe("formatDate", () => {
  it("writes dates for people", () => {
    expect(formatDate("2019-12-05")).toBe("Dec 5, 2019");
    expect(formatDate(null)).toBe("Date unknown");
  });
});
