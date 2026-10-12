// Loads the policy once, at start-up, from a fixed allowlist of files.
//
// Deny by default: no tool takes a path, nothing outside ALLOWED_FILES is ever
// opened, and nothing is written. The server holds an in-memory snapshot, so a
// rule change reaches it only on restart, after it has passed the approval gate.

import { readFileSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { checkText, corpusUrls, type CheckResult, type Product, type Rules } from "./checker.js";

export const ALLOWED_FILES = [
  "references/rules.json",
  "references/compliance-checklist.md",
  "references/brand-voice.md",
  "references/approved-claims.md",
  "data/incoming-stories.md",
  "data-pristine/incoming-stories.md",
] as const;

export interface Policy {
  root: string;
  rules: Rules;
  checklist: string;
  voice: string;
  approvedClaims: string;
  urls: Set<string>;
}

function defaultRoot(): string {
  // dist/src/policy.js -> repo root is four levels up (dist/src, dist, policy-server, mcp).
  const here = dirname(fileURLToPath(import.meta.url));
  return resolve(here, "..", "..", "..", "..");
}

function read(root: string, file: (typeof ALLOWED_FILES)[number]): string {
  return readFileSync(join(root, file), "utf-8");
}

export function loadPolicy(root: string = process.env.HARBOURLIGHT_ROOT ?? defaultRoot()): Policy {
  const rules = JSON.parse(read(root, "references/rules.json")) as Rules;
  const corpus = existsSync(join(root, "data/incoming-stories.md"))
    ? read(root, "data/incoming-stories.md")
    : existsSync(join(root, "data-pristine/incoming-stories.md"))
      ? read(root, "data-pristine/incoming-stories.md")
      : "";
  return {
    root,
    rules,
    checklist: read(root, "references/compliance-checklist.md"),
    voice: read(root, "references/brand-voice.md"),
    approvedClaims: read(root, "references/approved-claims.md"),
    urls: corpusUrls(corpus),
  };
}

function normaliseClaim(text: string): string {
  return text.replace(/[’‘]/g, "'").replace(/\s+/g, " ").trim().replace(/\.+$/, "").toLowerCase();
}

export interface ClaimCheck {
  approved: boolean;
  claim: string | null;
  product: string | null;
  names_product: string | null;
  reason: string;
}

// Does this text match an approved one-liner? Exact wording, ignoring case, spacing,
// curly apostrophes and a trailing full stop. Nothing fuzzier: "close enough" is how
// an unapproved claim gets through.
export function checkClaim(policy: Policy, text: string): ClaimCheck {
  const wanted = normaliseClaim(text);
  for (const product of policy.rules.products) {
    if (normaliseClaim(product.claim) === wanted) {
      return { approved: true, claim: product.claim, product: product.name, names_product: product.name,
        reason: "matches the approved line word for word" };
    }
  }
  const named = policy.rules.products.find((p: Product) =>
    p.aliases.some((a) => new RegExp(`(?<![\\w-])${a.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "i").test(text)));
  return {
    approved: false,
    claim: null,
    product: null,
    names_product: named ? named.name : null,
    reason: named
      ? `names ${named.name} but is not its approved line; use the line word for word (H2)`
      : "does not match any approved product line",
  };
}

export function checkPost(policy: Policy, text: string): CheckResult & { voice_version: number } {
  return { ...checkText(text, policy.rules, policy.urls), voice_version: policy.rules.voice_version };
}

export function voiceRules(policy: Policy) {
  const r = policy.rules;
  return {
    voice_version: r.voice_version,
    guide: policy.voice,
    word_count: r.word_count,
    banned_filler_words: r.ai_words,
    hype_phrases: r.hype_phrases,
    american_spellings: r.american_spellings,
    punctuation: { exclamation_marks: false, em_dashes: false },
  };
}

