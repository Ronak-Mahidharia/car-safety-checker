// Links can fill in the form: #year=2019&make=HONDA&model=CR-V&q=... The part after "#" stays in
// the browser; it isn't sent to the web server. The page only ever writes the vehicle there, never
// the description, so a copied link doesn't carry what someone typed unless they added it themselves.
import type { Vehicle } from "./nhtsa";

export interface Prefill {
  year?: string;
  make?: string;
  model?: string;
  description?: string;
}

export function readHash(hash: string): Prefill {
  const params = new URLSearchParams(hash.replace(/^#/, ""));
  const get = (key: string) => params.get(key)?.trim() || undefined;
  // NHTSA lists makes and models in capitals ("HONDA", "CR-V").
  return { year: get("year"), make: get("make")?.toUpperCase(), model: get("model")?.toUpperCase(), description: get("q") };
}

export function vehicleHash(vehicle: Vehicle): string {
  return `#${new URLSearchParams({ year: vehicle.year, make: vehicle.make, model: vehicle.model })}`;
}

/**
 * The address to switch to after reading a link: the vehicle only, or nothing after "#" while no full
 * vehicle is chosen. A description ("q") never stays in the address. Null means no change is needed.
 */
export function cleanAddress(vehicle: Partial<Vehicle>, location: { pathname: string; search: string; hash: string }): string | null {
  const { year, make, model } = vehicle;
  if (year && make && model) {
    const hash = vehicleHash({ year, make, model });
    return location.hash === hash ? null : hash;
  }
  return location.hash ? location.pathname + location.search : null;
}
