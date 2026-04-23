/**
 * Client-side PII detector. Mirrors (a subset of) the regex patterns in
 * ``apps/api/app/services/pii_service.py`` so participants get an in-UI
 * warning before they hit Next. The backend always re-strips on save —
 * this is a warning layer, not a guarantee.
 *
 * We deliberately keep the list conservative so we don't over-warn on
 * things like room numbers or short digit strings.
 */

export type PiiCategory =
  | "ssn"
  | "email"
  | "phone"
  | "credit_card"
  | "address"
  | "dob"
  | "ip"
  | "license"
  | "account"
  | "name"
  | "id"
  | "zip"
  | "sensitive";

export interface PiiMatch {
  category: PiiCategory;
  snippet: string;
}

const SSN_WITH_SEP = /\b(?:\d{3}[- ]\d{2}[- ]\d{4})\b/g;
const SSN_NO_SEP = /(?<![\w-])(\d{9})(?![\w-])/g;
const EMAIL = /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g;
const US_PHONE = /\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b/g;
const INTL_PHONE = /\+\d{1,3}[-.\s]?\d{3,14}/g;
const CREDIT_CARD_LIKE = /\b(?:\d[ -]*?){13,19}\b/g;
const STREET_ADDRESS =
  /\b\d{1,5}\s+[A-Za-z0-9.\s]{1,60}\b(?:street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|lane|ln|way|court|ct|place|pl|square|sq|terrace|ter|parkway|pkwy|circle|cir|highway|hwy)\b\.?/gi;
const DOB_NUMERIC = /\b(?:0?[1-9]|1[0-2])[\/\-](?:0?[1-9]|[12]\d|3[01])[\/\-](?:19|20)\d{2}\b/g;
const IPV4 = /\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b/g;

// Pull the first ~3 examples per category so the UI can show a concrete
// hint without leaking the full PII.
const MAX_MATCHES_PER_CATEGORY = 3;

function luhnValid(digits: string): boolean {
  const d = digits.replace(/\D/g, "");
  if (d.length < 13 || d.length > 19) return false;
  let sum = 0;
  let alt = false;
  for (let i = d.length - 1; i >= 0; i--) {
    let n = parseInt(d[i], 10);
    if (alt) {
      n *= 2;
      if (n > 9) n -= 9;
    }
    sum += n;
    alt = !alt;
  }
  return sum % 10 === 0;
}

function collect(
  pattern: RegExp,
  text: string,
  category: PiiCategory,
  out: PiiMatch[],
  filter?: (m: string) => boolean,
) {
  let count = 0;
  pattern.lastIndex = 0;
  for (const match of text.matchAll(pattern)) {
    const raw = match[0];
    if (filter && !filter(raw)) continue;
    if (count >= MAX_MATCHES_PER_CATEGORY) break;
    out.push({ category, snippet: raw.slice(0, 40) });
    count += 1;
  }
}

/**
 * Scan ``text`` for common PII patterns. Returns an empty array when
 * nothing is flagged.
 */
export function detectPii(text: string | null | undefined): PiiMatch[] {
  if (!text || typeof text !== "string") return [];
  const matches: PiiMatch[] = [];

  collect(SSN_WITH_SEP, text, "ssn", matches);
  collect(SSN_NO_SEP, text, "ssn", matches);
  collect(EMAIL, text, "email", matches);
  collect(US_PHONE, text, "phone", matches);
  collect(INTL_PHONE, text, "phone", matches);
  collect(CREDIT_CARD_LIKE, text, "credit_card", matches, luhnValid);
  collect(STREET_ADDRESS, text, "address", matches);
  collect(DOB_NUMERIC, text, "dob", matches);
  collect(IPV4, text, "ip", matches);

  return matches;
}

export function describeCategory(category: PiiCategory): string {
  switch (category) {
    case "ssn":
      return "Social Security number";
    case "email":
      return "email address";
    case "phone":
      return "phone number";
    case "credit_card":
      return "credit card number";
    case "address":
      return "address";
    case "dob":
      return "date of birth";
    case "ip":
      return "IP address";
    case "license":
      return "driver's license";
    case "account":
      return "account number";
    case "name":
      return "name";
    case "id":
      return "identification number";
    case "zip":
      return "ZIP code";
    case "sensitive":
      return "sensitive personal information";
    default:
      return "personal information";
  }
}

/**
 * Best-effort human label for any PII category, including strings emitted
 * by the backend (``detect_and_redact_pii_with_ai``) that may not be in the
 * client ``PiiCategory`` union yet. Falls back to "personal information"
 * for unknown categories instead of leaking the raw enum value.
 */
export function describeCategoryLabel(category: string): string {
  const known: Record<string, string> = {
    ssn: "Social Security number",
    email: "email address",
    phone: "phone number",
    credit_card: "credit card number",
    address: "address",
    dob: "date of birth",
    ip: "IP address",
    license: "driver's license",
    account: "account number",
    name: "name",
    id: "identification number",
    zip: "ZIP code",
    sensitive: "sensitive personal information",
  };
  return known[category] ?? "personal information";
}

export function summarisePii(matches: PiiMatch[]): string {
  if (matches.length === 0) return "";
  const uniq = Array.from(new Set(matches.map((m) => m.category)));
  return uniq.map(describeCategory).join(", ");
}

/**
 * Format a deduped list of category strings (possibly sourced from both
 * client regex and backend AI) into a human-readable summary suitable for
 * the banner. Uses ``describeCategoryLabel`` so unknown labels don't leak.
 */
export function summariseCategoryList(categories: string[]): string {
  if (categories.length === 0) return "";
  const uniq = Array.from(new Set(categories));
  return uniq.map(describeCategoryLabel).join(", ");
}

// Backend uses "***" as the redaction placeholder (see REDACTED_TOKEN in
// apps/api/app/services/pii_service.py). Keep them identical so server- and
// client-redacted text looks the same.
const REDACTED_TOKEN = "***";

/**
 * Redact common PII patterns from ``text`` client-side. Mirrors the regexes
 * in ``detectPii``. Returns the redacted text plus the count of redactions
 * and the set of categories that matched. Used by the voice recorder's
 * Web Speech shortcut path, where Whisper's server-side redaction is
 * bypassed — without this, "Show original" would reveal raw PII.
 *
 * This is defence-in-depth. The server always re-strips on save.
 */
export function stripPii(text: string | null | undefined): {
  text: string;
  count: number;
  categories: PiiCategory[];
} {
  if (!text || typeof text !== "string") {
    return { text: text ?? "", count: 0, categories: [] };
  }

  let out = text;
  let count = 0;
  const categories = new Set<PiiCategory>();

  const apply = (
    pattern: RegExp,
    category: PiiCategory,
    filter?: (m: string) => boolean,
  ) => {
    // Build a fresh global pattern so state doesn't leak between calls.
    const p = new RegExp(pattern.source, pattern.flags.includes("g") ? pattern.flags : pattern.flags + "g");
    out = out.replace(p, (match) => {
      if (filter && !filter(match)) return match;
      count += 1;
      categories.add(category);
      return REDACTED_TOKEN;
    });
  };

  apply(SSN_WITH_SEP, "ssn");
  apply(SSN_NO_SEP, "ssn");
  apply(EMAIL, "email");
  apply(US_PHONE, "phone");
  apply(INTL_PHONE, "phone");
  apply(CREDIT_CARD_LIKE, "credit_card", luhnValid);
  apply(STREET_ADDRESS, "address");
  apply(DOB_NUMERIC, "dob");
  apply(IPV4, "ip");

  return { text: out, count, categories: Array.from(categories) };
}
