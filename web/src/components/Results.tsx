import { useState } from "react";
import { formatDate } from "../lib/dates";
import { displayName } from "../lib/labels";
import type { ComplaintMatches, ShownRecall } from "../lib/match";
import type { Complaint, Vehicle } from "../lib/nhtsa";

export interface Analysis {
  description: string;
  top: [string, number][]; // the 3 most likely components, with the model's confidence
  labels: string[]; // the components the model picks
}

interface Props {
  vehicle: Vehicle;
  names: string[]; // every model name that was searched, the chosen one first
  recalls: ShownRecall[]; // already in display order
  complaintCount: number;
  analysis: Analysis | null;
  matches: ComplaintMatches | null;
}

const number = new Intl.NumberFormat("en-US");
const plural = (n: number, one: string, many: string) => `${number.format(n)} ${n === 1 ? one : many}`;

export function Results({ vehicle, names, recalls: shown, complaintCount, analysis, matches }: Props) {
  const name = `${vehicle.year} ${vehicle.make} ${vehicle.model}`;

  return (
    <>
      <p className="summary">
        NHTSA has {plural(shown.length, "recall", "recalls")} and {plural(complaintCount, "owner complaint", "owner complaints")} on
        file for the {name}.
      </p>
      {names.length > 1 && (
        <p className="note">
          NHTSA files this vehicle under more than one model name, so all of them were searched: {names.join(", ")}.
        </p>
      )}

      {analysis && <Guesses analysis={analysis} />}

      <section aria-labelledby="recalls-heading">
        <h2 id="recalls-heading">Recalls for this vehicle</h2>
        {shown.length ? (
          <>
            <p className="note">
              Every recall is listed, because NHTSA's API names one component per recall, though a recall can cover several
              parts. Recalls with a Do Not Drive or Park Outside warning come first
              {analysis ? ", then those for the components above" : ""}. A recall for this model and year may not cover every
              car, so <a href="https://www.nhtsa.gov/recalls">check your VIN on NHTSA's site</a>.
            </p>
            <ol className="cards">
              {shown.map((recall) => (
                <RecallCard key={recall.campaign} recall={recall} chosen={vehicle.model} />
              ))}
            </ol>
          </>
        ) : (
          <p className="note">
            No recalls were found for the {name}. NHTSA sometimes files a vehicle under a different model name, so{" "}
            <a href="https://www.nhtsa.gov/recalls">check your VIN on NHTSA's site</a> to be sure.
          </p>
        )}
      </section>

      <section aria-labelledby="complaints-heading">
        <h2 id="complaints-heading">Owner complaints like yours</h2>
        {!matches || !analysis ? (
          <p className="note">Describe the problem above to see complaints about the same part.</p>
        ) : matches.shown.length ? (
          <>
            <p className="note">
              {plural(matches.filedUnder, "complaint", "complaints")} about the {name} {matches.filedUnder === 1 ? "was" : "were"} filed
              under {analysis.labels.length === 1 ? "this component" : "these components"}. Here are the{" "}
              {matches.shown.length === 1 ? "one" : number.format(matches.shown.length)} with the wording closest to yours. Complaints
              are reports from owners; NHTSA hasn't verified them.
            </p>
            <ol className="cards">
              {matches.shown.map(({ complaint }) => (
                <ComplaintCard key={complaint.odiNumber} complaint={complaint} chosen={vehicle.model} />
              ))}
            </ol>
          </>
        ) : complaintCount === 0 ? (
          <p className="note">NHTSA has no owner complaints on file for the {name}.</p>
        ) : (
          <p className="note">No complaints about the {name} were filed under these components.</p>
        )}
      </section>
    </>
  );
}

function Guesses({ analysis }: { analysis: Analysis }) {
  return (
    <section aria-labelledby="guesses-heading">
      <h2 id="guesses-heading">Likely components</h2>
      <ol className="guesses">
        {analysis.top.map(([label, confidence]) => {
          const picked = analysis.labels.includes(label);
          return (
            <li key={label} className={picked ? "picked" : undefined}>
              <span className="guess-name">
                {displayName(label)}
                {picked && <span className="badge match">Used to match</span>}
              </span>
              <meter min={0} max={1} value={confidence} aria-label={`Confidence for ${displayName(label)}`} />
              <span className="guess-value">{confidence.toFixed(2)}</span>
            </li>
          );
        })}
      </ol>
      <p className="note">
        Confidence from 0 to 1, from a keyword model trained on 200,000 past complaints. On 1,000 complaints received in 2025 and
        2026, its top guess was one of the components NHTSA recorded 83% of the time.
      </p>
    </section>
  );
}

const listedAs = (name: string, chosen: string) => (name === chosen ? "" : ` · Filed under ${name}`);

function RecallCard({ recall, chosen }: { recall: ShownRecall; chosen: string }) {
  const classes = ["card", recall.advisory && "advisory", recall.matches && "matching"].filter(Boolean).join(" ");
  return (
    <li className={classes}>
      <div className="badges">
        {recall.doNotDrive && <span className="badge danger">Do Not Drive</span>}
        {recall.parkOutside && <span className="badge danger">Park Outside</span>}
        {recall.matches && <span className="badge match">Matches your description</span>}
        {recall.overTheAir && <span className="badge">Fixed by an over-the-air update</span>}
      </div>
      <h3>{recall.label ? displayName(recall.label) : "Other"}</h3>
      <p className="meta">
        Recall {recall.campaign} · Reported {formatDate(recall.received)} ·{" "}
        {recall.component
          .split(":")
          .map((part) => part.trim())
          .join(" › ")}
        {listedAs(recall.listedAs, chosen)}
      </p>
      {recall.summary && <Text label="Problem" text={recall.summary} />}
      {recall.consequence && <Text label="Risk" text={recall.consequence} />}
      {recall.remedy && <Text label="Fix" text={recall.remedy} />}
      <a className="source" href={recall.source}>
        NHTSA's record for {recall.campaign}
      </a>
    </li>
  );
}

function ComplaintCard({ complaint, chosen }: { complaint: Complaint; chosen: string }) {
  const flags = [
    complaint.crash && "Crash",
    complaint.fire && "Fire",
    complaint.injuries > 0 && plural(complaint.injuries, "injury", "injuries"),
    complaint.deaths > 0 && plural(complaint.deaths, "death", "deaths"),
  ].filter((flag): flag is string => Boolean(flag));
  return (
    <li className="card">
      {flags.length > 0 && (
        <div className="badges">
          {flags.map((flag) => (
            <span key={flag} className="badge danger">
              {flag}
            </span>
          ))}
        </div>
      )}
      <h3>{complaint.labels.length ? complaint.labels.map(displayName).join(", ") : "Component not given"}</h3>
      <p className="meta">
        Complaint {complaint.odiNumber} · Filed {formatDate(complaint.filed)}
        {listedAs(complaint.listedAs, chosen)}
      </p>
      <Text text={complaint.summary} />
      <a className="source" href={complaint.source}>
        NHTSA's record for complaint {complaint.odiNumber}
      </a>
    </li>
  );
}

const PREVIEW = 360;

/** Long text starts shortened, with a button to show all of it. */
function Text({ label, text }: { label?: string; text: string }) {
  const [open, setOpen] = useState(false);
  const long = text.length > PREVIEW + 40;
  const cut = text.slice(0, PREVIEW);
  const shown = !long || open ? text : `${cut.slice(0, Math.max(cut.lastIndexOf(" "), PREVIEW / 2))}...`;
  return (
    <div className="text">
      <p>
        {label && <strong>{label}: </strong>}
        {shown}
      </p>
      {long && (
        <button type="button" className="link-button" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? "Show less" : "Show all"}
        </button>
      )}
    </div>
  );
}
