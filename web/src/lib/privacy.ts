// A second safety net for complaint text, the same as src/carsafety/privacy.py. NHTSA already
// removes personal details before publishing complaints; this also masks anything that still looks
// like an email address, a US phone number, or a full 17-character VIN.
//
// Python's \w, \d, and \b understand every alphabet, while JavaScript's only know A-Z and 0-9, so these
// patterns spell out the Unicode classes to behave like the Python ones. A test compares the two.

const WORD = String.raw`\p{L}\p{N}_`;

const PATTERNS = [
  new RegExp(String.raw`[${WORD}.+\-]+@[${WORD}\-]+\.[${WORD}.\-]+`, "gu"), // email
  new RegExp(String.raw`(?<!\p{Nd})(?:\+?1[\s.\-]?)?\(?\p{Nd}{3}\)?[\s.\-]?\p{Nd}{3}[\s.\-]?\p{Nd}{4}(?!\p{Nd})`, "gu"), // US phone
  new RegExp(String.raw`(?<![${WORD}])[A-HJ-NPR-Z0-9]{17}(?![${WORD}])`, "gu"), // VIN (no I, O, Q)
];

export const MASK = "[removed]";

/** The text with emails, phone numbers, and full VINs masked. */
export function scrub(text: string): string {
  return PATTERNS.reduce((result, pattern) => result.replace(pattern, MASK), text);
}
