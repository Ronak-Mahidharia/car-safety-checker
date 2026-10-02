import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Results, type Analysis } from "./components/Results";
import { VehiclePicker } from "./components/VehiclePicker";
import { cleanAddress, readHash } from "./lib/hash";
import { matchComplaints, orderRecalls } from "./lib/match";
import { NhtsaError, records as loadRecords, type Complaint, type Recall, type Vehicle } from "./lib/nhtsa";
import { relatedNames, vehicleModels } from "./lib/vehicles";
import { KeywordModel } from "./model/keywordModel";

// The answer key only scored descriptions of at least 20 characters.
const MIN_LENGTH = 20;

type Records =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; names: string[]; recalls: Recall[]; complaints: Complaint[] }
  | { status: "error"; message: string };

const isComplete = (v: Partial<Vehicle>): v is Vehicle => Boolean(v.year && v.make && v.model);

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
    // NHTSA may file the same vehicle under related model names ("AIR" and "AIR BEV"), so search them all.
    vehicleModels(chosen.year, chosen.make, controller.signal)
      .catch(() => [chosen.model])
      .then(async (models) => {
        const names = relatedNames(chosen.model, models);
        const found = await loadRecords(chosen, names, controller.signal);
        if (!controller.signal.aborted) setRecords({ status: "ready", names, ...found });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setRecords({ status: "error", message: error instanceof NhtsaError ? error.message : "Couldn't load NHTSA's records." });
      });
    return () => controller.abort();
  }, [year, make, modelName, attempt]);

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

  function check(event: FormEvent) {
    event.preventDefault();
    const text = description.trim();
    if (!isComplete(vehicle)) setProblem("Choose the year, make, and model first.");
    else if (text.length < MIN_LENGTH) setProblem(`Please describe the problem in at least ${MIN_LENGTH} characters.`);
    else {
      setProblem(null);
      setSubmitted(text);
    }
  }

  return (
    <>
      <header>
        <h1>Car Safety Checker</h1>
        <p className="lead">Describe a problem with your car to see NHTSA's recalls and the owner complaints that match it.</p>
        <p className="notice">
          This isn't a safety inspection, and it never says a car is safe. To check your car for open recalls, enter your VIN on{" "}
          <a href="https://www.nhtsa.gov/recalls">NHTSA's recall lookup</a>.
        </p>
      </header>

      <main>
        <form onSubmit={check} noValidate>
          <section aria-labelledby="vehicle-heading">
            <h2 id="vehicle-heading">1. Your vehicle</h2>
            <VehiclePicker value={vehicle} onChange={pickVehicle} />
          </section>

          <section aria-labelledby="problem-heading">
            <h2 id="problem-heading">2. What's happening?</h2>
            <label htmlFor="description">Describe the problem in your own words</label>
            <textarea
              id="description"
              rows={4}
              maxLength={2000}
              value={description}
              placeholder="For example: the engine hesitates when I speed up, and the check engine light comes on."
              aria-describedby="description-hint"
              onChange={(event) => setDescription(event.target.value)}
            />
            <p id="description-hint" className="hint">
              Your description is analyzed in your browser. It isn't sent anywhere.
            </p>
            <button type="submit">Find matches</button>
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
          </section>
        </form>

        <div aria-live="polite">
          {records.status === "loading" && <p className="summary">Loading NHTSA's records...</p>}
          {records.status === "error" && (
            <p className="error" role="alert">
              {records.message}{" "}
              <button type="button" className="link-button" onClick={() => setAttempt((n) => n + 1)}>
                Try again
              </button>
            </p>
          )}
          {records.status === "ready" && view && isComplete(vehicle) && (
            <Results
              vehicle={vehicle}
              names={records.names}
              recalls={view.recalls}
              complaintCount={records.complaints.length}
              analysis={analysis}
              matches={view.matches}
            />
          )}
        </div>
      </main>

      <footer>
        <p>Not affiliated with or endorsed by NHTSA or the U.S. Department of Transportation.</p>
        <p>
          Recalls and complaints come from NHTSA's public data (api.nhtsa.gov) when you choose a vehicle. Only the year, make,
          and model are sent. Your description stays in your browser. This page sets no cookies and has no analytics.
        </p>
        <p>
          Complaints are reports from owners that NHTSA hasn't verified. Emails, phone numbers, and full VINs in their text are
          hidden, and the partial VIN that NHTSA keeps with each complaint is never shown.
        </p>
      </footer>
    </>
  );
}
