// The page, rendered to HTML without a browser.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { App } from "./App";
import { Results } from "./components/Results";
import { VehiclePicker } from "./components/VehiclePicker";
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
  recordModel: "CR-V",
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
      models={["CR-V"]}
      recalls={recalls}
      relatedRecalls={[]}
      complaintCount={1101}
      leftOut={{}}
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

  it("shows the vehicle, its counts, and a warning tile for the Do Not Drive recall", () => {
    expect(html).toContain(">2019 HONDA CR-V</h2>");
    expect(html).toMatch(/Recalls<\/dt><dd class="stat-value">3</);
    expect(html).toMatch(/Owner complaints<\/dt><dd class="stat-value">1,101</);
    expect(html).toContain("Safety warnings");
    expect(html).toContain('<dd class="stat-detail">Do Not Drive</dd>');
    expect(html.indexOf("Safety warnings")).toBeLessThan(html.indexOf("Recalls</dt>"));
  });

  it("opens NHTSA's records in a new tab without sharing the page", () => {
    expect(html).toContain('target="_blank" rel="noopener noreferrer"');
  });

  it("shows guesses, complaints, and links to NHTSA's records", () => {
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
      models={["AIR"]}
      recalls={orderRecalls([recall("26V540000", "2026-08-20", "ELECTRICAL SYSTEM", { parkOutside: true, listedAs: "AIR" })], [])}
      relatedRecalls={[]}
      complaintCount={6}
      leftOut={{}}
      analysis={null}
      matches={null}
    />,
  );

  it("says which names were searched and which one each recall was filed under", () => {
    expect(html).toContain("NHTSA&#x27;s complaint records name this vehicle AIR. NHTSA uses more than one name");
    expect(html).toContain("these were searched: AIR BEV, AIR.");
    expect(html).toContain("Filed under AIR");
    expect(html).toContain("Park Outside");
  });
});

describe("Results without any safety warning", () => {
  const html = renderToStaticMarkup(
    <Results
      vehicle={{ year: "2019", make: "HONDA", model: "CR-V" }}
      names={["CR-V"]}
      models={["CR-V"]}
      recalls={orderRecalls([recall("21V000001", "2021-03-25", "TIRES")], [])}
      relatedRecalls={[]}
      complaintCount={0}
      leftOut={{}}
      analysis={null}
      matches={null}
    />,
  );

  it("has no warnings tile, because a zero there could be read as 'safe'", () => {
    expect(html).not.toContain("Safety warnings");
    expect(html).not.toContain('class="warning-banner"');
  });

  it("doesn't mention other names when only the chosen one was searched", () => {
    expect(html).not.toContain("these were searched");
    expect(html).not.toContain("similar name");
    expect(html).not.toContain("left out");
  });
});

describe("Results with recalls under a similar name that may be another vehicle", () => {
  // The 2022 Mustang Mach-E's records name MUSTANG MACH E; MUSTANG is the gasoline car (checked Oct 3, 2026).
  // The Do Not Drive flag on the MUSTANG recall is made up, to show how a warning there is handled.
  const html = renderToStaticMarkup(
    <Results
      vehicle={{ year: "2022", make: "FORD", model: "MUSTANG MACH-E" }}
      names={["MUSTANG MACH-E", "MUSTANG", "MUSTANG MACH E"]}
      models={["MUSTANG MACH E"]}
      recalls={orderRecalls([recall("22V900001", "2022-06-10", "ELECTRICAL SYSTEM", { listedAs: "MUSTANG MACH E" })], [])}
      relatedRecalls={orderRecalls([recall("22V900002", "2022-02-16", "AIR BAGS", { listedAs: "MUSTANG", doNotDrive: true })], [])}
      complaintCount={138}
      leftOut={{}}
      analysis={null}
      matches={null}
    />,
  );

  it("counts only the vehicle's own recalls and warnings", () => {
    expect(html).toMatch(/Recalls<\/dt><dd class="stat-value">1</);
    expect(html).not.toContain("Safety warnings");
  });

  it("lists the similar name's recalls apart, after the vehicle's own, and says why", () => {
    const own = html.indexOf("Recall 22V900001");
    const heading = html.indexOf("Recalls under similar names");
    expect(own).toBeGreaterThan(0);
    expect(heading).toBeGreaterThan(own);
    expect(html.indexOf("Recall 22V900002")).toBeGreaterThan(heading);
    expect(html).toContain("This recall is filed under MUSTANG, a similar name that may be a different vehicle, so it isn&#x27;t counted above.");
    expect(html).toContain("Filed under MUSTANG");
  });

  it("points out a safety warning filed under the similar name", () => {
    expect(html).toContain('class="callout danger"');
    expect(html).toContain("A safety warning is filed under a similar name (MUSTANG). Check whether it applies to your vehicle");
  });
});

describe("Results when a search returned another model's complaints", () => {
  const html = renderToStaticMarkup(
    <Results
      vehicle={{ year: "2023", make: "FORD", model: "F-150 (SUPER CREW) LIGHTNING BEV" }}
      names={["F-150 (SUPER CREW) LIGHTNING BEV", "F-150", "F-150 LIGHTNING BEV"]}
      models={["F-150 LIGHTNING BEV"]}
      recalls={[]}
      relatedRecalls={orderRecalls([recall("23V900002", "2023-02-10", "POWER TRAIN", { listedAs: "F-150" })], [])}
      complaintCount={109}
      leftOut={{ "F-150 HYBRID": 94 }}
      analysis={null}
      matches={null}
    />,
  );

  it("says how many were left out and which model they name", () => {
    expect(html).toContain(
      "NHTSA&#x27;s search for this vehicle also returned 94 complaints whose records name another model (F-150 HYBRID), so they&#x27;re left out.",
    );
  });

  it("says the vehicle's own names have no recalls, and points to the ones under similar names", () => {
    expect(html).toContain("No recalls are filed under this vehicle&#x27;s names. Recalls under similar names are listed below and may apply");
  });
});

describe("The page before a vehicle is chosen", () => {
  const html = renderToStaticMarkup(<App />);

  it("explains what to do, and offers example descriptions that don't name a vehicle", () => {
    expect(html).toContain("Choose a vehicle to begin");
    expect(html).toContain("Engine hesitates");
    expect(html).toContain("Skip to results");
  });
});

describe("VehiclePicker", () => {
  it("shows a vehicle from a link while NHTSA's lists are still loading", () => {
    const html = renderToStaticMarkup(<VehiclePicker value={{ year: "2019", make: "HONDA", model: "CR-V" }} onChange={() => {}} />);
    for (const value of ["2019", "HONDA", "CR-V"]) expect(html).toContain(`<option value="${value}" selected="">${value}</option>`);
  });
});
