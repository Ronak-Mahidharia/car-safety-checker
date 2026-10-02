// NHTSA's API writes dates in two different orders (checked Oct 2, 2026):
//   - recalls: day/month/year. "05/12/2019" for recall 19V865000 is Dec 5, 2019, its date in
//     NHTSA's recall file (20191205).
//   - complaints: month/day/year, such as "09/29/2026".
// Dates are turned into "YYYY-MM-DD" strings, which sort in date order.

const PATTERN = /^(\d{2})\/(\d{2})\/(\d{4})$/;

function iso(year: number, month: number, day: number): string | null {
  const date = new Date(Date.UTC(year, month - 1, day));
  const real = date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
  return real ? date.toISOString().slice(0, 10) : null;
}

/** A recall date ("DD/MM/YYYY") as "YYYY-MM-DD", or null if it isn't a real date. */
export function parseDayFirst(value: string): string | null {
  const m = PATTERN.exec(value.trim());
  return m ? iso(Number(m[3]), Number(m[2]), Number(m[1])) : null;
}

/** A complaint date ("MM/DD/YYYY") as "YYYY-MM-DD", or null if it isn't a real date. */
export function parseMonthFirst(value: string): string | null {
  const m = PATTERN.exec(value.trim());
  return m ? iso(Number(m[3]), Number(m[1]), Number(m[2])) : null;
}

const FORMAT = new Intl.DateTimeFormat("en-US", { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" });

/** "2019-12-05" -> "Dec 5, 2019". */
export function formatDate(isoDate: string | null): string {
  return isoDate ? FORMAT.format(new Date(`${isoDate}T00:00:00Z`)) : "Date unknown";
}
