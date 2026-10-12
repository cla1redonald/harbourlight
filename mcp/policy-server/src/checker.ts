// A line-for-line port of evals/check_post.py, the deterministic checker.
//
// Two implementations of one rule set can drift, so test/parity.test.ts runs
// the Python checker and this one over every labelled case and seeded draft and
// fails on any difference. If you change one, change the other in the same commit.

export interface Product {
  name: string;
  aliases: string[];
  claim: string;
  signpost: boolean;
}

export interface Rules {
  voice_version: number;
  word_count: { min: number; max: number };
  products: Product[];
  competitors: string[];
  disparaging_words: string[];
  advice_phrases: string[];
  sensitive_patterns: string[];
  h7_fail_phrases: string[];
  ai_words: string[];
  hype_phrases: string[];
  american_spellings: Record<string, string>;
}

export interface Finding {
  rule: string;
  severity: "fail" | "flag";
  quote: string;
  why: string;
}

export interface CheckResult {
  verdict: "PASS" | "FLAG" | "FAIL";
  needs_human: boolean;
  word_count: number;
  findings: Finding[];
  what_would_change: string[];
  rules: string[];
}

const EM_DASH = "\u2014";

const FIXES: Record<string, string> = {
  H1: "cite the story this comes from, or cut the statement",
  H2: "use the product's approved line word for word, or drop the product",
  H3: "put the figure on a source line with where it came from, or cut it",
  H4: "describe the options without telling the reader what to do or promising an outcome",
  H5: "remove the name and any detail that could identify the person",
  H6: "remove the comment about the other firm",
  H7: "remove the product or the light-hearted framing; only the Steady Ground line may appear",
};

const FIGURE_PATTERNS: RegExp[] = [
  /\d+(?:\.\d+)?\s?(?:%|per\s?cent\b)/gi,
  /£\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:k|m|bn|million|billion)\b)?/gi,
  /\b\d+\s+in\s+\d+\b/g,
  /\b\d{1,3}(?:,\d{3})+\b/g,
  /\b\d+\.\d+\b/g,
  /\b\d{4,}\b/g,
];

const NAMED_PERSON_PATTERNS: RegExp[] = [
  /\b(?:Mr|Mrs|Ms|Miss|Mx|Dr)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?/g,
  /\b(?:member|customer|policyholder|homeowner|borrower)s?\s+(?:called\s+|named\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?/g,
  /\b[A-Z][a-z]+\s+[A-Z][a-z]+,\s+(?:a|an|one of our|who is a)\s+(?:\d+-year-old\s+)?(?:member|customer|policyholder|homeowner|borrower)/g,
  /\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?,\s+(?:aged\s+)?\d{2},/g,
];

const SOURCES_HEADER = /^\W*sources\W*:?\W*$/i;
export const URL_PATTERN = /https?:\/\/[^\s)\]>,;]+/g;

export function cleanUrl(url: string): string {
  return url.replace(/[.,;:)'"]+$/, "");
}

export function corpusUrls(corpusText: string): Set<string> {
  return new Set([...corpusText.matchAll(URL_PATTERN)].map((m) => cleanUrl(m[0])));
}

function stripFrontMatter(text: string): string {
  if (text.startsWith("---\n")) {
    const end = text.indexOf("\n---", 4);
    if (end !== -1) return text.slice(end + 4).replace(/^\n+/, "");
  }
  return text;
}

// Python's str.splitlines() for the text this checker sees.
function splitLines(text: string): string[] {
  const lines = text.split(/\r\n|\r|\n/);
  if (lines.length && lines[lines.length - 1] === "") lines.pop();
  return lines;
}

export function splitPost(text: string): { body: string; sources: string[] | null } {
  const lines = splitLines(stripFrontMatter(text));
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]!.trim();
    if (line && SOURCES_HEADER.test(line)) {
      return {
        body: lines.slice(0, i).join("\n"),
        sources: lines.slice(i + 1).map((s) => s.trim()).filter((s) => s),
      };
    }
  }
  return { body: lines.join("\n"), sources: null };
}

export function countWords(body: string): number {
  const prose = splitLines(body).filter((l) => !l.trimStart().startsWith("#")).join("\n");
  return prose.split(/\s+/).filter((t) => t && /[A-Za-z0-9]/.test(t)).length;
}

function sentences(body: string): string[] {
  return body
    .split(/(?<=[.!?])\s+|\n+/)
    .map((p) => p.trim().replace(/^#+/, "").trim())
    .filter((p) => p);
}

function norm(text: string): string {
  const lowered = text.replace(/[’‘]/g, "'").toLowerCase();
  return lowered.replace(/\s+/g, " ").trim().replace(/\.+$/, "");
}

/**
 * A sentence that names a product passes H2 only if it IS the approved line:
 * equal after normalisation, allowing only quotation marks and punctuation at
 * either end. Containing the line is not enough, or extra claims could ride
 * alongside it.
 */
function isApprovedLine(sentence: string, claim: string): boolean {
  const strip = (text: string) => norm(text).replace(/^["'“”‘’(\[\s]+|["'“”‘’)\].,;:!?\s]+$/g, "");
  return strip(sentence) === strip(claim);
}

function normFigure(text: string): string {
  return text.toLowerCase().replace(/per\s?cent/g, "%").replace(/\s+/g, "");
}

function escapeRegex(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\/-]/g, "\\$&");
}

function phraseRegex(phrase: string, stem = false): RegExp {
  const tail = stem ? "\\w*" : "\\b";
  return new RegExp("(?<![\\w-])" + escapeRegex(phrase) + tail, "i");
}

function sentenceWith(sents: string[], pattern: RegExp): Array<[string, string]> {
  const hits: Array<[string, string]> = [];
  for (const sentence of sents) {
    const match = pattern.exec(sentence);
    if (match) hits.push([sentence, match[0]]);
  }
  return hits;
}

function productsMentioned(sents: string[], rules: Rules): Array<[Product, string]> {
  const found: Array<[Product, string]> = [];
  for (const sentence of sents) {
    for (const product of rules.products) {
      if (product.aliases.some((a) => phraseRegex(a).test(sentence))) found.push([product, sentence]);
    }
  }
  return found;
}

function shorten(text: string, limit = 80): string {
  return text.length <= limit ? text : text.slice(0, limit - 3) + "...";
}

export function checkText(text: string, rules: Rules, urls: Set<string>): CheckResult {
  const { body, sources } = splitPost(text);
  const sents = sentences(body);
  const words = countWords(body);
  const findings: Finding[] = [];
  let needsHuman = false;

  const add = (rule: string, severity: "fail" | "flag", quote: string, why: string): void => {
    if (findings.some((f) => f.rule === rule && f.quote === quote)) return;
    findings.push({ rule, severity, quote, why });
  };

  // H1
  const sourceUrls = (sources ?? []).flatMap((line) => [...line.matchAll(URL_PATTERN)].map((m) => cleanUrl(m[0])));
  if (sourceUrls.length === 0) {
    add("H1", "fail", "(no sources block)", "nothing in the post can be traced to a story");
  } else if (urls.size > 0) {
    for (const url of sourceUrls) {
      if (!urls.has(url)) add("H1", "fail", url, "cited source is not a story in the corpus");
    }
  }

  // H2 and S2
  const mentions = productsMentioned(sents, rules);
  for (const [product, sentence] of mentions) {
    if (!isApprovedLine(sentence, product.claim)) {
      add("H2", "fail", sentence, `names ${product.name} outside its approved line`);
    }
  }
  const distinct: string[] = [];
  for (const [product] of mentions) if (!distinct.includes(product.name)) distinct.push(product.name);
  if (distinct.length > 1) {
    add("S2", "flag", distinct[1]!, `${distinct.length} products mentioned: ${distinct.join(", ")}`);
  }

  // H3
  let scan = body;
  for (const product of rules.products) scan = scan.replace(new RegExp(escapeRegex(product.claim), "gi"), " ");
  const taken: Array<[number, number]> = [];
  const figures: string[] = [];
  for (const pattern of FIGURE_PATTERNS) {
    pattern.lastIndex = 0;
    for (const match of scan.matchAll(pattern)) {
      const start = match.index ?? 0;
      const end = start + match[0].length;
      if (taken.some(([s, e]) => start < e && end > s)) continue;
      const value = match[0].trim();
      if (/^\d{4}$/.test(value) && Number(value) >= 1900 && Number(value) <= 2099) continue;
      taken.push([start, end]);
      figures.push(value);
    }
  }
  const sourceText = (sources ?? []).map(normFigure);
  for (const figure of figures) {
    if (!sourceText.some((line) => line.includes(normFigure(figure)))) {
      add("H3", "fail", figure, "figure has no source line");
    }
  }

  // H4
  for (const phrase of rules.advice_phrases) {
    for (const [sentence, matched] of sentenceWith(sents, phraseRegex(phrase))) {
      add("H4", "fail", sentence, `advice or promise: '${matched}'`);
    }
  }

  // H5
  for (const pattern of NAMED_PERSON_PATTERNS) {
    for (const match of body.matchAll(pattern)) {
      add("H5", "fail", match[0], "identifies an individual customer or member");
    }
  }

  // H6
  for (const name of rules.competitors) {
    for (const [sentence] of sentenceWith(sents, phraseRegex(name))) {
      if (findings.some((f) => f.rule === "H6" && f.quote === sentence)) continue;
      const negative = rules.disparaging_words.filter((w) => phraseRegex(w).test(sentence));
      if (negative.length) add("H6", "fail", sentence, `criticises a competitor: '${negative[0]}'`);
      else add("H6", "flag", sentence, "names a competitor; approver to confirm it is neutral");
    }
  }

  // H7
  const sensitiveHits: Array<[string, string]> = [];
  for (const stem of rules.sensitive_patterns) sensitiveHits.push(...sentenceWith(sents, phraseRegex(stem, true)));
  if (sensitiveHits.length) {
    needsHuman = true;
    const [sentence, matched] = sensitiveHits[0]!;
    add("H7", "flag", sentence, `sensitive topic ('${matched}'): a person must read this`);
    for (const [product, pSentence] of mentions) {
      if (!product.signpost) add("H7", "fail", pSentence, `sells ${product.name} in a post about a sensitive topic`);
    }
    for (const phrase of rules.h7_fail_phrases) {
      for (const [pSentence, m] of sentenceWith(sents, phraseRegex(phrase))) {
        add("H7", "fail", pSentence, `promotional framing on a sensitive topic: '${m}'`);
      }
    }
  }

  // S1
  for (const word of rules.ai_words) {
    for (const [, matched] of sentenceWith(sents, phraseRegex(word))) add("S1", "flag", matched, "marketing filler word");
  }
  if (body.includes("!")) add("S1", "flag", "!", "exclamation mark");
  if (text.includes(EM_DASH)) add("S1", "flag", EM_DASH, "em dash");

  // S3
  for (const phrase of rules.hype_phrases) {
    for (const [, matched] of sentenceWith(sents, phraseRegex(phrase))) add("S3", "flag", matched, "hype or absolute claim");
  }

  // S4
  const bounds = rules.word_count;
  if (!(bounds.min <= words && words <= bounds.max)) {
    add("S4", "flag", `${words} words`, `body must be ${bounds.min} to ${bounds.max} words`);
  }

  // S5
  for (const [american, british] of Object.entries(rules.american_spellings)) {
    for (const [, matched] of sentenceWith(sents, phraseRegex(american))) add("S5", "flag", matched, `use '${british}'`);
  }

  const hasFail = findings.some((f) => f.severity === "fail");
  const hasFlag = findings.some((f) => f.severity === "flag");
  const verdict = hasFail ? "FAIL" : hasFlag || needsHuman ? "FLAG" : "PASS";
  const changes = hasFail
    ? findings.filter((f) => f.severity === "fail").map((f) => `${f.rule}: ${FIXES[f.rule]} ("${shorten(f.quote)}")`)
    : [];
  return {
    verdict,
    needs_human: needsHuman,
    word_count: words,
    findings,
    what_would_change: changes,
    rules: [...new Set(findings.map((f) => f.rule))].sort(),
  };
}
