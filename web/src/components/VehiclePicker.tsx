import { useEffect, useState } from "react";
import type { Vehicle } from "../lib/nhtsa";
import { vehicleMakes, vehicleModels, vehicleYears } from "../lib/vehicles";

interface Options {
  status: "loading" | "ready" | "error";
  items: string[];
}

/** Loads one list from NHTSA whenever its inputs change, cancelling the previous request. */
function useOptions(load: ((signal: AbortSignal) => Promise<string[]>) | null, inputs: readonly unknown[]) {
  const [options, setOptions] = useState<Options>({ status: load ? "loading" : "ready", items: [] });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!load) {
      setOptions({ status: "ready", items: [] });
      return;
    }
    const controller = new AbortController();
    setOptions({ status: "loading", items: [] });
    load(controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) setOptions({ status: "ready", items });
      })
      .catch(() => {
        if (!controller.signal.aborted) setOptions({ status: "error", items: [] });
      });
    return () => controller.abort();
    // `load` is rebuilt on every render, so the inputs it depends on decide when to reload.
  }, [...inputs, attempt]);
  return { ...options, retry: () => setAttempt((n) => n + 1) };
}

interface Props {
  value: Partial<Vehicle>;
  onChange: (vehicle: Partial<Vehicle>) => void;
}

export function VehiclePicker({ value, onChange }: Props) {
  const { year, make, model } = value;
  const years = useOptions((signal) => vehicleYears(signal), []);
  const makeList = useOptions(year ? (signal) => vehicleMakes(year, signal) : null, [year]);
  const modelList = useOptions(year && make ? (signal) => vehicleModels(year, make, signal) : null, [year, make]);

  // A value from a link that NHTSA doesn't list is cleared, along with the choices after it.
  useEffect(() => {
    if (year && years.status === "ready" && !years.items.includes(year)) onChange({});
    else if (make && makeList.status === "ready" && year && !makeList.items.includes(make)) onChange({ year });
    else if (model && modelList.status === "ready" && make && !modelList.items.includes(model)) onChange({ year, make });
  }, [year, make, model, years.status, years.items, makeList.status, makeList.items, modelList.status, modelList.items, onChange]);

  const failed = [years, makeList, modelList].find((list) => list.status === "error");

  return (
    <fieldset className="picker">
      <legend className="visually-hidden">Vehicle</legend>
      <Select id="year" label="Model year" value={year} list={years} enabled onPick={(y) => onChange({ year: y })} />
      <Select id="make" label="Make" value={make} list={makeList} enabled={Boolean(year)} onPick={(m) => onChange({ year, make: m })} />
      <Select id="model" label="Model" value={model} list={modelList} enabled={Boolean(year && make)} onPick={(m) => onChange({ year, make, model: m })} />
      {failed && (
        <p className="error" role="alert">
          Couldn't load NHTSA's vehicle list.{" "}
          <button type="button" className="link-button" onClick={failed.retry}>
            Try again
          </button>
        </p>
      )}
    </fieldset>
  );
}

interface SelectProps {
  id: string;
  label: string;
  value: string | undefined;
  list: Options;
  enabled: boolean;
  onPick: (value: string | undefined) => void;
}

function Select({ id, label, value, list, enabled, onPick }: SelectProps) {
  const loading = enabled && list.status === "loading";
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select
        id={id}
        value={list.items.includes(value ?? "") ? value : ""}
        disabled={!enabled || list.status !== "ready" || !list.items.length}
        onChange={(event) => onPick(event.target.value || undefined)}
      >
        <option value="">{loading ? "Loading..." : `Choose a ${label.toLowerCase()}`}</option>
        {list.items.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </select>
    </div>
  );
}
