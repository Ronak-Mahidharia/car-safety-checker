// The page, rendered to HTML without a browser.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { App } from "./App";
import { Results } from "./components/Results";
import { orderRecalls } from "./lib/match";
import type { Complaint, Recall } from "./lib/nhtsa";

const recall = (campaign: string, received: string, label: string, flags: Partial<Recall> = {}): Recall => ({
  campaign,
  received,
  component: `${label}:PART`,
  label,
  summary: `Summary of ${campaign}.`,
  consequence: "Risk.",
  remedy: "Fix.",
  doNotDrive: false,
  parkOutside: false,
  overTheAir: false,
  source: `https://api.nhtsa.gov/recalls/campaignNumber?campaignNumber=${campaign}`,
  listedAs: "CR-V",
  ...flags,
});

const complaint: Complaint = {
  odiNumber: "12345678",
  filed: "2026-09-29",
  components: ["ENGINE"],
  labels: ["ENGINE"],
  summary: "The engine hesitates. Call me at [removed].",
  crash: true,
  fire: false,
  injuries: 1,
  deaths: 0,
  source: "https://api.nhtsa.gov/complaints/odinumber?odinumber=12345678",
  listedAs: "CR-V",
};

describe("App", () => {
  it("shows the safety notice and the privacy promise before anything loads", () => {
    const html = renderToStaticMarkup(<App />);
    expect(html).toContain("isn&#x27;t a safety inspection");
    expect(html).toContain('href="https://www.nhtsa.gov/recalls"');
    expect(html).toContain("Not affiliated with or endorsed by NHTSA");
    expect(html).toContain("It isn&#x27;t sent anywhere.");
  });
});

describe("Results", () => {
  const recalls = orderRecalls(
    [recall("21V000001", "2021-03-25", "TIRES"), recall("19V000002", "2019-12-05", "ENGINE"), recall("17V000003", "2017-07-07", "AIR BAGS", { doNotDrive: true })],
    ["ENGINE"],
  );
  const analysis = { description: "the engine hesitates", top: [["ENGINE", 0.81], ["ELECTRICAL SYSTEM", 0.2], ["POWER TRAIN", 0.1]] as [string, number][], labels: ["ENGINE"] };
  const html = renderToStaticMarkup(
    <Results
      vehicle={{ year: "2019", make: "HONDA", model: "CR-V" }}
      names={["CR-V"]}
      recalls={recalls}
      complaintCount={1101}
      analysis={analysis}
      matches={{ filedUnder: 1, shown: [{ complaint, similarity: 0.5 }] }}
    />,
  );

  it("puts the Do Not Drive recall first, then the matching one", () => {
    const order = ["17V000003", "19V000002", "21V000001"].map((campaign) => html.indexOf(`Recall ${campaign}`));
    expect(order.every((position, i) => position > 0 && (i === 0 || position > order[i - 1]))).toBe(true);
    expect(html).toContain("Do Not Drive");
    expect(html).toContain("Matches your description");
  });

  it("shows counts, guesses, complaints, and links to NHTSA's records", () => {
    expect(html).toContain("NHTSA has 3 recalls and 1,101 owner complaints on file for the 2019 HONDA CR-V.");
    expect(html).toContain("Engine");
    expect(html).toContain("0.81");
    expect(html).toContain("Crash");
    expect(html).toContain("1 injury");
    expect(html).toContain('href="https://api.nhtsa.gov/complaints/odinumber?odinumber=12345678"');
    expect(html).toContain('href="https://api.nhtsa.gov/recalls/campaignNumber?campaignNumber=17V000003"');
  });
});

describe("Results for a vehicle filed under more than one name", () => {
  const html = renderToStaticMarkup(
    <Results
      vehicle={{ year: "2026", make: "LUCID", model: "AIR BEV" }}
      names={["AIR BEV", "AIR"]}
      recalls={orderRecalls([recall("26V540000", "2026-08-20", "ELECTRICAL SYSTEM", { parkOutside: true, listedAs: "AIR" })], [])}
      complaintCount={6}
      analysis={null}
      matches={null}
    />,
  );

  it("says which names were searched and which one each recall was filed under", () => {
    expect(html).toContain("all of them were searched: AIR BEV, AIR.");
    expect(html).toContain("Filed under AIR");
    expect(html).toContain("Park Outside");
  });
});
