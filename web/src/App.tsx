import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { AlertIcon, CarIcon, LockIcon, MoonIcon, ResetIcon, SearchIcon } from "./components/Icons";
import { ExternalLink, plural, Results, type Analysis } from "./components/Results";
import { VehiclePicker } from "./components/VehiclePicker";
import { cleanAddress, readHash } from "./lib/hash";
import { matchComplaints, orderRecalls } from "./lib/match";
import { NhtsaError, type Vehicle } from "./lib/nhtsa";
import { chooseTheme, currentTheme, savedTheme, type Theme } from "./lib/theme";
import { recallNames, search, vehicleModels, type Found } from "./lib/vehicles";
import { KeywordModel } from "./model/keywordModel";

// The answer key only scored descriptions of at least 20 characters.
const MIN_LENGTH = 20;
const MAX_LENGTH = 2000;
const VIN_LOOKUP = "https://www.nhtsa.gov/recalls";
const number = new Intl.NumberFormat("en-US");

// Examples fill in the description only, never a vehicle, so they don't suggest that any
// particular car has these problems.
const EXAMPLES = [
  { label: "Engine hesitates", text: "The engine hesitates when I speed up, and the check engine light comes on." },
  { label: "Soft brakes", text: "The brakes feel soft, and the pedal sinks almost to the floor." },
  { label: "Screen goes black", text: "The touchscreen goes black while driving, and the backup camera stops working." },
];

type Records =
  | { status: "idle" }
  | { status: "loading" }
  | ({ status: "ready" } & Found)
  | { status: "error"; message: string };

const isComplete = (v: Partial<Vehicle>): v is Vehicle => Boolean(v.year && v.make && v.model);

// Some browsers throw when a page touches storage that the user has blocked.
function browserStorage(): Storage | undefined {
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
}

const DARK_QUERY = "(prefers-color-scheme: dark)";

export function App() {
  const prefill = useMemo(() => readHash(typeof window === "undefined" ? "" : window.location.hash), []);
  const [vehicle, setVehicle] = useState<Partial<Vehicle>>({ year: prefill.year, make: prefill.make, model: prefill.model });
  const [description, setDescription] = useState(prefill.description ?? "");
  const [submitted, setSubmitted] = useState<string | null>(
    prefill.description && prefill.description.length >= MIN_LENGTH ? prefill.description : null,
  );
  const [problem, setProblem] = useState<string | null>(null);
  const [model, setModel] = useState<KeywordModel | null>(null);
  const [modelFailed, setModelFailed] = useState(false);
  const [records, setRecords] = useState<Records>({ status: "idle" });
  const [attempt, setAttempt] = useState(0);
  const [searches, setSearches] = useState(0);
  const resultsRef = useRef<HTMLElement>(null);
  const [theme, setTheme] = useState<Theme>(() =>
    typeof window === "undefined" ? "light" : currentTheme(savedTheme(browserStorage()), window.matchMedia(DARK_QUERY).matches),
  );

  // Until someone uses the switch, it shows the device's setting, which can change while the page is open.
  useEffect(() => {
    const media = window.matchMedia(DARK_QUERY);
    const follow = () => {
      if (!savedTheme(browserStorage())) setTheme(media.matches ? "dark" : "light");
    };
    media.addEventListener("change", follow);
    return () => media.removeEventListener("change", follow);
  }, []);

  function toggleTheme() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    chooseTheme(next, document.documentElement, document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]'), browserStorage());
    setTheme(next);
  }

  useEffect(() => {
    KeywordModel.load(`${import.meta.env.BASE_URL}model/`)
      .then(setModel)
      .catch(() => setModelFailed(true));
  }, []);

  const { year, make, model: modelName } = vehicle;
  useEffect(() => {
    const chosen = { year, make, model: modelName };
    // Only the vehicle goes in the address, never the description (a link's "q" is removed once read).
    const address = cleanAddress(chosen, window.location);
    if (address !== null) window.history.replaceState(null, "", address);
    if (!isComplete(chosen)) {
      setRecords({ status: "idle" });
      return;
    }
    const controller = new AbortController();
    setRecords({ status: "loading" });
    // NHTSA names the same vehicle in more than one way, so the search covers related names and uses
    // the complaint records to sort out which recalls and complaints are this vehicle's (see vehicles.ts).
    Promise.all([
      vehicleModels(chosen.year, chosen.make, controller.signal).catch(() => [chosen.model]),
      recallNames(chosen.year)
        .then((file) => file[chosen.make] ?? [])
        .catch(() => []),
    ])
      .then(async ([models, fileNames]) => {
        const found = await search(chosen, models, fileNames, controller.signal);
        if (!controller.signal.aborted) setRecords({ status: "ready", ...found });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setRecords({ status: "error", message: error instanceof NhtsaError ? error.message : "Couldn't load NHTSA's records." });
      });
    return () => controller.abort();
  }, [year, make, modelName, attempt]);

  // On narrow screens the results sit below the form, so a search brings them into view.
  useEffect(() => {
    if (!searches || !resultsRef.current || window.matchMedia("(min-width: 1024px)").matches) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    resultsRef.current.scrollIntoView({ behavior: still ? "auto" : "smooth", block: "start" });
  }, [searches]);

  const analysis = useMemo<Analysis | null>(() => {
    if (!model || !submitted || model.vector(submitted).size === 0) return null;
    return { description: submitted, top: model.top(submitted, 3), labels: model.predict(submitted) };
  }, [model, submitted]);
  const unknownWords = Boolean(model && submitted && !analysis);

  // Worked out once per search, not on every keystroke: matching scores every complaint's text.
  const view = useMemo(() => {
    if (records.status !== "ready") return null;
    return {
      recalls: orderRecalls(records.recalls, analysis?.labels ?? []),
      relatedRecalls: orderRecalls(records.relatedRecalls, analysis?.labels ?? []),
      matches:
        analysis && model
          ? matchComplaints(records.complaints, analysis.labels, analysis.description, (text) => model.vector(text))
          : null,
    };
  }, [records, analysis, model]);

  const pickVehicle = useCallback((next: Partial<Vehicle>) => {
    setVehicle(next);
    setProblem(null);
  }, []);

  const hasInput = Boolean(vehicle.year || vehicle.make || vehicle.model || description || submitted);

  // Clears the vehicle, the description, and the results. The address loses the vehicle too.
  function startOver() {
    setVehicle({});
    setDescription("");
    setSubmitted(null);
    setProblem(null);
    document.getElementById("year")?.focus();
  }

  function check(event: FormEvent) {
    event.preventDefault();
    const text = description.trim();
    if (!isComplete(vehicle)) setProblem("Choose the year, make, and model first.");
    else if (text.length < MIN_LENGTH) setProblem(`Please describe the problem in at least ${MIN_LENGTH} characters.`);
    else {
      setProblem(null);
      setSubmitted(text);
      setSearches((n) => n + 1);
    }
  }

  // Read out by screen readers when the results change; the cards themselves aren't announced.
  const status =
    records.status === "loading"
      ? "Loading NHTSA's records."
      : records.status === "error"
        ? records.message
        : records.status === "ready" && isComplete(vehicle)
          ? `Found ${plural(records.recalls.length, "recall", "recalls")} and ${plural(records.complaints.length, "owner complaint", "owner complaints")} for the ${vehicle.year} ${vehicle.make} ${vehicle.model}${records.relatedRecalls.length ? `, and ${plural(records.relatedRecalls.length, "recall", "recalls")} under similar names` : ""}.`
          : "";

  return (
    <>
      <a className="skip-link" href="#results">
        Skip to results
      </a>
      <header className="topbar">
        <div className="container topbar-inner">
          <p className="brand">
            <span className="logo">
              <CarIcon />
            </span>
            Car Safety Checker
          </p>
          <div className="topbar-actions">
            <button
              type="button"
              role="switch"
              aria-checked={theme === "dark"}
              aria-label="Dark mode"
              className="theme-switch"
              onClick={toggleTheme}
            >
              <MoonIcon />
              <span className="wide-only" aria-hidden="true">
                Dark mode
              </span>
              <span className="switch-track" aria-hidden="true">
                <span className="switch-thumb" />
              </span>
            </button>
            <ExternalLink href={VIN_LOOKUP} className="topbar-link">
              <span className="wide-only">Check your VIN at NHTSA</span>
              <span className="narrow-only">VIN check</span>
            </ExternalLink>
          </div>
        </div>
      </header>

      <div className="container hero">
        <h1>Look up recalls and owner complaints for your car</h1>
        <p className="lead">
          Describe what's happening in your own words. See NHTSA's recalls for your vehicle and the owner complaints that sound most
          like yours, each linked to the official record.
        </p>
        <p className="notice">
          <AlertIcon />
          <span>
            This isn't a safety inspection, and it never says a car is safe. To check your car for open recalls, enter your VIN on{" "}
            <ExternalLink href={VIN_LOOKUP}>NHTSA's recall lookup</ExternalLink>.
          </span>
        </p>
      </div>

      <main className="container layout">
        <form className="card search" onSubmit={check} noValidate aria-label="Search NHTSA's records">
          <section aria-labelledby="vehicle-heading">
            <h2 id="vehicle-heading" className="step">
              <span className="step-num" aria-hidden="true">
                1
              </span>
              Your vehicle
            </h2>
            <VehiclePicker value={vehicle} onChange={pickVehicle} />
          </section>

          <section aria-labelledby="problem-heading">
            <h2 id="problem-heading" className="step">
              <span className="step-num" aria-hidden="true">
                2
              </span>
              What's happening?
            </h2>
            <label htmlFor="description">Describe the problem in your own words</label>
            <textarea
              id="description"
              rows={5}
              maxLength={MAX_LENGTH}
              value={description}
              placeholder="For example: the engine hesitates when I speed up, and the check engine light comes on."
              aria-describedby="description-hint"
              onChange={(event) => setDescription(event.target.value)}
            />
            <p id="description-hint" className="textarea-foot">
              <span>At least {MIN_LENGTH} characters</span>
              <span className="counter">
                {number.format(description.length)} / {number.format(MAX_LENGTH)}
              </span>
            </p>
            <div className="examples">
              <span className="examples-label">Try an example:</span>
              {EXAMPLES.map((example) => (
                <button key={example.label} type="button" className="example" onClick={() => setDescription(example.text)}>
                  {example.label}
                </button>
              ))}
            </div>
          </section>

          <button type="submit" className="primary">
            <SearchIcon />
            Find matches
          </button>
          <button type="button" className="link-button start-over" onClick={startOver} disabled={!hasInput}>
            <ResetIcon width="16" height="16" />
            Start over
          </button>
          <p className="privacy">
            <LockIcon />
            <span>Your description is analyzed in your browser. It isn't sent anywhere. Only the year, make, and model go to NHTSA.</span>
          </p>
          {problem && (
            <p className="error" role="alert">
              {problem}
            </p>
          )}
          {modelFailed && (
            <p className="error" role="alert">
              The model didn't load, so components can't be guessed. Recalls still work.
            </p>
          )}
          {unknownWords && (
            <p className="error" role="alert">
              The model didn't recognize those words. Try naming the part and what it does.
            </p>
          )}
        </form>

        <section id="results" className="results-panel" ref={resultsRef} aria-label="Results" aria-busy={records.status === "loading"}>
          <p className="visually-hidden" role="status">
            {status}
          </p>
          {records.status === "idle" && <Welcome />}
          {records.status === "loading" && <Loading />}
          {records.status === "error" && (
            <div className="card state-card">
              <AlertIcon />
              <div>
                <h2>Couldn't load NHTSA's records</h2>
                <p>{records.message}</p>
                <button type="button" className="secondary" onClick={() => setAttempt((n) => n + 1)}>
                  Try again
                </button>
              </div>
            </div>
          )}
          {records.status === "ready" && view && isComplete(vehicle) && (
            <Results
              vehicle={vehicle}
              names={records.names}
              models={records.models}
              recalls={view.recalls}
              relatedRecalls={view.relatedRecalls}
              complaintCount={records.complaints.length}
              leftOut={records.leftOut}
              analysis={analysis}
              matches={view.matches}
            />
          )}
        </section>
      </main>

      <footer className="site-footer">
        <div className="container footer-inner">
          <div>
            <h2>About</h2>
            <p>
              Car Safety Checker searches NHTSA's public recall and complaint records. Not affiliated with or endorsed by NHTSA or the
              U.S. Department of Transportation.
            </p>
          </div>
          <div>
            <h2>Privacy</h2>
            <p>
              Recalls and complaints come from NHTSA's public data (api.nhtsa.gov) when you choose a vehicle. Only the year, make, and
              model are sent. Your description stays in your browser. This page sets no cookies and has no analytics. It remembers
              only your light or dark choice, in this browser.
            </p>
          </div>
          <div>
            <h2>The complaints</h2>
            <p>
              Complaints are reports from owners that NHTSA hasn't verified. Emails, phone numbers, and full VINs in their text are
              hidden, and the partial VIN that NHTSA keeps with each complaint is never shown.
            </p>
          </div>
        </div>
      </footer>
    </>
  );
}

function Welcome() {
  return (
    <div className="card welcome">
      <span className="welcome-icon">
        <CarIcon width="28" height="28" />
      </span>
      <h2>Choose a vehicle to begin</h2>
      <p className="muted">
        Recalls load as soon as you pick the model year, make, and model. Then describe the problem to find complaints like yours.
      </p>
      <ol className="how">
        <li>
          <span className="how-num">1</span>
          <div>
            <h3>NHTSA's records, live</h3>
            <p>The recalls and owner complaints NHTSA has published for the vehicle, fetched from its public API.</p>
          </div>
        </li>
        <li>
          <span className="how-num">2</span>
          <div>
            <h3>A model in your browser</h3>
            <p>It names the likely component from your words. What you type stays on your device.</p>
          </div>
        </li>
        <li>
          <span className="how-num">3</span>
          <div>
            <h3>Sources you can check</h3>
            <p>Every recall and complaint links to NHTSA's official record.</p>
          </div>
        </li>
      </ol>
    </div>
  );
}

function Loading() {
  return (
    <div className="loading" aria-hidden="true">
      <div className="skeleton skeleton-title" />
      <div className="stats">
        <div className="skeleton skeleton-stat" />
        <div className="skeleton skeleton-stat" />
      </div>
      {[0, 1, 2].map((i) => (
        <div key={i} className="card skeleton-card">
          <div className="skeleton skeleton-line wide" />
          <div className="skeleton skeleton-line" />
          <div className="skeleton skeleton-line short" />
        </div>
      ))}
    </div>
  );
}
