// NHTSA component names -> the 31 clean labels, the same way as src/carsafety/labels.py.
// A test checks both give the same label for all 800 component names in NHTSA's files.

// Old or variant names -> the current NHTSA category.
const MERGE = new Map<string, string>([
  ["ENGINE AND ENGINE COOLING", "ENGINE"],
  ["SERVICE BRAKES, HYDRAULIC", "SERVICE BRAKES"],
  ["SERVICE BRAKES, AIR", "SERVICE BRAKES"],
  ["SERVICE BRAKES, ELECTRIC", "SERVICE BRAKES"],
  ["SERVICE BRAKES, HYDRAULIC; AUTOHOLD BRAKE SYSTEM/BRAKE HOLD", "SERVICE BRAKES"],
  ["FUEL SYSTEM, GASOLINE", "FUEL/PROPULSION SYSTEM"],
  ["FUEL SYSTEM, DIESEL", "FUEL/PROPULSION SYSTEM"],
  ["FUEL SYSTEM, OTHER", "FUEL/PROPULSION SYSTEM"],
  ["HYBRID PROPULSION SYSTEM", "FUEL/PROPULSION SYSTEM"],
  ["VISIBILITY", "VISIBILITY/WIPER"],
  ["ELECTRONIC STABILITY CONTROL", "ELECTRONIC STABILITY CONTROL (ESC)"],
  ["COMMUNICATIONS", "COMMUNICATION"],
  // Sub-parts from NHTSA's car-seat form
  ["CHEST CLIP, BUCKLE, HARNESS", "CHILD SEAT"],
  ["CARRY HANDLE, SHELL, BASE", "CHILD SEAT"],
  ["TETHER, LOWER ANCHOR (ON CAR SEAT OR VEHICLE)", "CHILD SEAT"],
  ["INSERT, PADDING", "CHILD SEAT"],
  ["I SUSPECT THE CAR SEAT IS COUNTERFEIT", "CHILD SEAT"],
]);

// Values that mean "the owner didn't know". Not a label.
const UNKNOWN = new Set(["", "UNKNOWN OR OTHER", "OTHER/UNKNOWN", "OTHER/I AM NOT SURE", "NONE", "OTHER"]);

/** The clean top-level label for one NHTSA component name, or null if it means "unknown". */
export function normalize(component: string): string | null {
  const top = component.split(":", 1)[0].trim().toUpperCase();
  if (UNKNOWN.has(top)) return null;
  return MERGE.get(top) ?? top;
}

/** Clean labels for several component names: sorted, unique, unknowns dropped. */
export function normalizeAll(components: readonly string[]): string[] {
  const labels = new Set<string>();
  for (const component of components) {
    const label = normalize(component);
    if (label !== null) labels.add(label);
  }
  return [...labels].sort();
}

/**
 * Split the complaints API's list of components. It joins them with a comma and no space
 * ("SERVICE BRAKES,FORWARD COLLISION AVOIDANCE"), while names that contain a comma have a space
 * after it ("FUEL SYSTEM, GASOLINE"). No NHTSA category name has a comma followed by a letter.
 */
export function splitComponents(value: string): string[] {
  return value ? value.split(/,(?=\S)/) : [];
}

const SPECIAL_NAMES = new Map([["FIRERELATED", "Fire-related"]]);

/** A friendlier way to show a label: "SERVICE BRAKES" -> "Service brakes", keeping "(ESC)". */
export function displayName(label: string): string {
  const special = SPECIAL_NAMES.get(label);
  if (special) return special;
  const lower = label.toLowerCase().replace(/\(([^)]*)\)/g, (_, inside: string) => `(${inside.toUpperCase()})`);
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}
