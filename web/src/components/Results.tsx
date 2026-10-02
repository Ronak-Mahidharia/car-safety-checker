import { useState, type ReactNode } from "react";
import { formatDate } from "../lib/dates";
import { displayName } from "../lib/labels";
import type { ComplaintMatches, ShownRecall } from "../lib/match";
import type { Complaint, Vehicle } from "../lib/nhtsa";
import { AlertIcon, ChatIcon, ChevronIcon, ExternalIcon, InfoIcon, TargetIcon, WrenchIcon } from "./Icons";

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
export const plural = (n: number, one: string, many: string) => `${number.format(n)} ${n === 1 ? one : many}`;
const VIN_LOOKUP = "https://www.nhtsa.gov/recalls";

export function Results({ vehicle, names, recalls, complaintCount, analysis, matches }: Props) {
  const name = `${vehicle.year} ${vehicle.make} ${vehicle.model}`;
  const doNotDrive = recalls.filter((r) => r.doNotDrive).length;
  const parkOutside = recalls.filter((r) => r.parkOutside).length;
  const warnings = recalls.filter((r) => r.advisory).length;

  return (
    <div className="results">
      <div className="results-head">
        <p className="eyebrow">NHTSA records for</p>
        <h2 className="vehicle-title">{name}</h2>
        <dl className="stats">
          {/* First when there are warnings, and shown only then: a "0" here could be misread as "safe". */}
          {warnings > 0 && (
            <Stat
              label="Safety warnings"
              value={warnings}
              tone="danger"
              detail={
                doNotDrive && parkOutside
                  ? `${number.format(doNotDrive)} Do Not Drive · ${number.format(parkOutside)} Park Outside`
                  : doNotDrive
                    ? "Do Not Drive"
                    : "Park Outside"
              }
            />
          )}
          <Stat label="Recalls" value={recalls.length} />
          <Stat label="Owner complaints" value={complaintCount} />
        </dl>
        {names.length > 1 && (
          <p className="callout">
            <InfoIcon />
            <span>NHTSA files this vehicle under more than one model name, so all of them were searched: {names.join(", ")}.</span>
          </p>
        )}
      </div>

      {analysis && <Guesses analysis={analysis} />}

      <section className="section" aria-labelledby="recalls-heading">
        <div className="section-head">
          <h3 id="recalls-heading">Recalls</h3>
          <span className="count">{number.format(recalls.length)}</span>
        </div>
        {recalls.length ? (
          <>
            <p className="section-note">
              Every recall is listed, because NHTSA's API names one component per recall, though a recall can cover several
              parts. Recalls with a Do Not Drive or Park Outside warning come first
              {analysis ? ", then those for the likely components" : ""}. A recall for this model and year may not cover every
              car, so <ExternalLink href={VIN_LOOKUP}>check your VIN on NHTSA's site</ExternalLink>.
            </p>
            <ol className="cards">
              {recalls.map((recall) => (
                <RecallCard key={recall.campaign} recall={recall} chosen={vehicle.model} />
              ))}
            </ol>
          </>
        ) : (
          <div className="card quiet">
            <p>
              No recalls were found for the {name}. NHTSA sometimes files a vehicle under a different model name, so{" "}
              <ExternalLink href={VIN_LOOKUP}>check your VIN on NHTSA's site</ExternalLink> to be sure.
            </p>
          </div>
        )}
      </section>

      <section className="section" aria-labelledby="complaints-heading">
        <div className="section-head">
          <h3 id="complaints-heading">Owner complaints like yours</h3>
          {matches && analysis && matches.shown.length > 0 && <span className="count">{number.format(matches.shown.length)}</span>}
        </div>
        {!matches || !analysis ? (
          <div className="card quiet with-icon">
            <ChatIcon />
            <p>Describe the problem to see complaints about the same part, with the ones worded most like yours first.</p>
          </div>
        ) : matches.shown.length ? (
          <>
            <p className="section-note">
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
          <div className="card quiet">
            <p>NHTSA has no owner complaints on file for the {name}.</p>
          </div>
        ) : (
          <div className="card quiet">
            <p>No complaints about the {name} were filed under these components.</p>
          </div>
        )}
      </section>
    </div>
  );
}

function Stat({ label, value, detail, tone }: { label: string; value: number; detail?: string; tone?: "danger" }) {
  return (
    <div className={tone ? `stat ${tone}` : "stat"}>
      <dt>
        {tone === "danger" && <AlertIcon width="16" height="16" />}
        {label}
      </dt>
      <dd className="stat-value">{number.format(value)}</dd>
      {detail && <dd className="stat-detail">{detail}</dd>}
    </div>
  );
}

function Guesses({ analysis }: { analysis: Analysis }) {
  return (
    <section className="card guesses-card" aria-labelledby="guesses-heading">
      <div className="section-head">
        <TargetIcon className="section-icon" />
        <h3 id="guesses-heading">Likely components</h3>
      </div>
      <ol className="guesses">
        {analysis.top.map(([label, confidence]) => {
          const picked = analysis.labels.includes(label);
          return (
            <li key={label} className={picked ? "picked" : undefined}>
              <div className="guess-row">
                <span className="guess-name">{displayName(label)}</span>
                {picked && <span className="chip match">Used to match</span>}
                <span className="guess-value">{confidence.toFixed(2)}</span>
              </div>
              <meter min={0} max={1} value={confidence} aria-label={`Confidence for ${displayName(label)}`} />
            </li>
          );
        })}
      </ol>
      <p className="fine-print">
        Confidence from 0 to 1, from a keyword model trained on 200,000 past complaints. On 1,000 complaints received in 2025 and
        2026, its top guess was one of the components NHTSA recorded 83% of the time.
      </p>
    </section>
  );
}

function RecallCard({ recall, chosen }: { recall: ShownRecall; chosen: string }) {
  const [open, setOpen] = useState(false);
  const warnings = [recall.doNotDrive && "Do Not Drive", recall.parkOutside && "Park Outside"].filter((w): w is string => Boolean(w));
  const classes = ["card", "recall", recall.advisory && "is-advisory", recall.matches && "is-match"].filter(Boolean).join(" ");
  return (
    <li className={classes}>
      {warnings.length > 0 && (
        <p className="warning-banner">
          <AlertIcon />
          <span>
            <strong>{warnings.join(" · ")}</strong> · NHTSA safety warning
          </span>
        </p>
      )}
      <div className="card-head">
        <h4>{recall.label ? displayName(recall.label) : "Other"}</h4>
        <time dateTime={recall.received ?? undefined}>{recall.received ? `Reported ${formatDate(recall.received)}` : "Date unknown"}</time>
      </div>
      <p className="path">
        {recall.component
          .split(":")
          .map((part) => part.trim())
          .join(" › ")}
      </p>
      <div className="chips">
        <span className="chip mono">Recall {recall.campaign}</span>
        {recall.matches && <span className="chip match">Matches your description</span>}
        {recall.overTheAir && <span className="chip">Over-the-air fix</span>}
        {recall.listedAs !== chosen && <span className="chip">Filed under {recall.listedAs}</span>}
      </div>
      {recall.summary && <Field label="Problem" text={recall.summary} open={open} />}
      {recall.consequence && <Field label="Risk" text={recall.consequence} open={open} tone="risk" icon={<AlertIcon width="16" height="16" />} />}
      {recall.remedy && <Field label="Fix" text={recall.remedy} open={open} icon={<WrenchIcon />} />}
      <CardFoot
        long={[recall.summary, recall.consequence, recall.remedy].some(isLong)}
        open={open}
        onToggle={() => setOpen(!open)}
        source={recall.source}
        record={`recall ${recall.campaign}`}
      />
    </li>
  );
}

function ComplaintCard({ complaint, chosen }: { complaint: Complaint; chosen: string }) {
  const [open, setOpen] = useState(false);
  const flags = [
    complaint.crash && "Crash",
    complaint.fire && "Fire",
    complaint.injuries > 0 && plural(complaint.injuries, "injury", "injuries"),
    complaint.deaths > 0 && plural(complaint.deaths, "death", "deaths"),
  ].filter((flag): flag is string => Boolean(flag));
  return (
    <li className="card complaint">
      <div className="card-head">
        <h4>{complaint.labels.length ? complaint.labels.map(displayName).join(", ") : "Component not given"}</h4>
        <time dateTime={complaint.filed ?? undefined}>{complaint.filed ? `Filed ${formatDate(complaint.filed)}` : "Date unknown"}</time>
      </div>
      <div className="chips">
        <span className="chip mono">Complaint {complaint.odiNumber}</span>
        {flags.map((flag) => (
          <span key={flag} className="chip danger">
            {flag}
          </span>
        ))}
        {complaint.listedAs !== chosen && <span className="chip">Filed under {complaint.listedAs}</span>}
      </div>
      <blockquote className="quote">{open || !isLong(complaint.summary) ? complaint.summary : shorten(complaint.summary)}</blockquote>
      <CardFoot
        long={isLong(complaint.summary)}
        open={open}
        onToggle={() => setOpen(!open)}
        source={complaint.source}
        record={`complaint ${complaint.odiNumber}`}
      />
    </li>
  );
}

const PREVIEW = 360;
const isLong = (text: string) => text.length > PREVIEW + 40;
const shorten = (text: string) => {
  const cut = text.slice(0, PREVIEW);
  return `${cut.slice(0, Math.max(cut.lastIndexOf(" "), PREVIEW / 2))}...`;
};

/** One labeled part of a recall. Long text starts shortened; the card's button shows all of it. */
function Field({ label, text, open, tone, icon }: { label: string; text: string; open: boolean; tone?: "risk"; icon?: ReactNode }) {
  return (
    <div className={tone ? `detail ${tone}` : "detail"}>
      <p className="detail-label">
        {icon}
        {label}
      </p>
      <p className="detail-text">{open || !isLong(text) ? text : shorten(text)}</p>
    </div>
  );
}

function CardFoot({ long, open, onToggle, source, record }: { long: boolean; open: boolean; onToggle: () => void; source: string; record: string }) {
  return (
    <div className="card-foot">
      {long ? (
        <button type="button" className="link-button" aria-expanded={open} onClick={onToggle}>
          {open ? "Show less" : "Show full details"}
          <ChevronIcon className={open ? "flip" : undefined} />
        </button>
      ) : (
        <span />
      )}
      <ExternalLink href={source} className="record-link" label={`NHTSA's record for ${record}`}>
        NHTSA record
      </ExternalLink>
    </div>
  );
}

/** A link to NHTSA's site, opened in a new tab. */
export function ExternalLink({ href, children, className, label }: { href: string; children: ReactNode; className?: string; label?: string }) {
  return (
    <a href={href} className={className} target="_blank" rel="noopener noreferrer" aria-label={label ? `${label} (opens in a new tab)` : undefined}>
      {children}
      <ExternalIcon />
      {!label && <span className="visually-hidden"> (opens in a new tab)</span>}
    </a>
  );
}
