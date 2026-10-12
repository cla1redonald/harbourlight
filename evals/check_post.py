#!/usr/bin/env python3
"""Deterministic pre-checks for a Harbourlight post.

Stdlib only. Reads the rule data from references/rules.json and the list of
real story URLs from data/incoming-stories.md, then checks one or more post
files against the compliance checklist (references/compliance-checklist.md).

This is not the compliance reviewer. It runs in front of the reviewer and
catches the things a pattern can catch, so the reviewer's attention goes on
the things only judgement can catch. See docs/design/0003.

Usage:
    python3 evals/check_post.py data/posts/*.draft.md
    python3 evals/check_post.py --json --strict post.md
    python3 evals/check_post.py --disable H3 post.md   # seeded fault

Exit codes (only with --strict): 0 PASS, 1 FLAG, 2 FAIL.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES = ROOT / "references" / "rules.json"
DEFAULT_CORPUS = ROOT / "data" / "incoming-stories.md"
PRISTINE_CORPUS = ROOT / "data-pristine" / "incoming-stories.md"

EM_DASH = "\u2014"
HARD_RULES = ("H1", "H2", "H3", "H4", "H5", "H6", "H7")
SOFT_RULES = ("S1", "S2", "S3", "S4", "S5")
ALL_RULES = HARD_RULES + SOFT_RULES

# What a writer would have to do to clear a failing rule.
FIXES = {
    "H1": "cite the story this comes from, or cut the statement",
    "H2": "use the product's approved line word for word, or drop the product",
    "H3": "put the figure on a source line with where it came from, or cut it",
    "H4": "describe the options without telling the reader what to do or promising an outcome",
    "H5": "remove the name and any detail that could identify the person",
    "H6": "remove the comment about the other firm",
    "H7": "remove the product or the light-hearted framing; only the Steady Ground line may appear",
}

FIGURE_PATTERNS = (
    re.compile(r"\d+(?:\.\d+)?\s?(?:%|per\s?cent\b)", re.IGNORECASE),
    re.compile(r"£\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:k|m|bn|million|billion)\b)?", re.IGNORECASE),
    re.compile(r"\b\d+\s+in\s+\d+\b"),
    re.compile(r"\b\d{1,3}(?:,\d{3})+\b"),
    re.compile(r"\b\d+\.\d+\b"),
    re.compile(r"\b\d{4,}\b"),
)

NAMED_PERSON_PATTERNS = (
    # Mr Thomson, Mrs Agnes Ritchie
    re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Mx|Dr)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?"),
    # member Douglas Thomson, customer called Ann
    re.compile(
        r"\b(?:member|customer|policyholder|homeowner|borrower)s?\s+(?:called\s+|named\s+)?"
        r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?"
    ),
    # Douglas Thomson, a member / Douglas Thomson, a 72-year-old member
    re.compile(
        r"\b[A-Z][a-z]+\s+[A-Z][a-z]+,\s+(?:a|an|one of our|who is a)\s+(?:\d+-year-old\s+)?"
        r"(?:member|customer|policyholder|homeowner|borrower)"
    ),
    # Douglas Thomson, 72,
    re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?,\s+(?:aged\s+)?\d{2},"),
)

SOURCES_HEADER = re.compile(r"^\W*sources\W*:?\W*$", re.IGNORECASE)
URL_PATTERN = re.compile(r"https?://[^\s)\]>,;]+")


@dataclass
class Finding:
    rule: str
    severity: str  # "fail" or "flag"
    quote: str
    why: str


@dataclass
class Result:
    verdict: str
    needs_human: bool
    word_count: int
    findings: list[Finding] = field(default_factory=list)
    what_would_change: list[str] = field(default_factory=list)

    def rules(self) -> list[str]:
        return sorted({f.rule for f in self.findings})

    def to_dict(self) -> dict:
        data = asdict(self)
        data["rules"] = self.rules()
        return data


def load_rules(path: Path | None = None) -> dict:
    return json.loads((path or DEFAULT_RULES).read_text(encoding="utf-8"))


def load_corpus_urls(path: Path | None = None) -> set[str]:
    """Return every story URL in the corpus. Missing corpus means no H1 URL check."""
    candidates = [path] if path else [DEFAULT_CORPUS, PRISTINE_CORPUS]
    for candidate in candidates:
        if candidate and candidate.exists():
            text = candidate.read_text(encoding="utf-8")
            return {_clean_url(u) for u in URL_PATTERN.findall(text)}
    return set()


def _clean_url(url: str) -> str:
    return url.rstrip(".,;:)'\"")


def strip_front_matter(text: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            return text[end + 4 :].lstrip("\n")
    return text


def split_post(text: str) -> tuple[str, list[str] | None]:
    """Split a post into body text and source lines (None if no Sources block)."""
    lines = strip_front_matter(text).splitlines()
    for index, line in enumerate(lines):
        if SOURCES_HEADER.match(line.strip()) and line.strip():
            body = "\n".join(lines[:index])
            sources = [s.strip() for s in lines[index + 1 :] if s.strip()]
            return body, sources
    return "\n".join(lines), None


def count_words(body: str) -> int:
    prose = "\n".join(l for l in body.splitlines() if not l.lstrip().startswith("#"))
    return sum(1 for token in prose.split() if re.search(r"[A-Za-z0-9]", token))


def sentences(body: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", body)
    return [p.strip().lstrip("#").strip() for p in parts if p.strip().lstrip("#").strip()]


def _norm(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").lower()
    return re.sub(r"\s+", " ", text).strip().rstrip(".")


_EDGE_PUNCT = re.compile(r"^[\"'“”‘’(\[\s]+|[\"'“”‘’)\].,;:!?\s]+$")


def _is_approved_line(sentence: str, claim: str) -> bool:
    """A sentence naming a product passes H2 only if it IS the approved line.

    Equal after normalisation, allowing only quotation marks and punctuation
    at either end. Containing the line is not enough, or extra claims could
    ride alongside it.
    """
    strip = lambda text: _EDGE_PUNCT.sub("", _norm(text))
    return strip(sentence) == strip(claim)


def _norm_figure(text: str) -> str:
    text = re.sub(r"per\s?cent", "%", text.lower())
    return re.sub(r"\s+", "", text)


def _phrase_regex(phrase: str, stem: bool = False) -> re.Pattern[str]:
    tail = r"\w*" if stem else r"\b"
    return re.compile(r"(?<![\w-])" + re.escape(phrase) + tail, re.IGNORECASE)


def _sentence_with(sents: list[str], pattern: re.Pattern[str]) -> list[tuple[str, str]]:
    hits = []
    for sentence in sents:
        match = pattern.search(sentence)
        if match:
            hits.append((sentence, match.group(0)))
    return hits


def products_mentioned(sents: list[str], rules: dict) -> list[tuple[dict, str]]:
    """Return (product, sentence) pairs for every sentence naming a product."""
    found = []
    for sentence in sents:
        for product in rules["products"]:
            if any(_phrase_regex(a).search(sentence) for a in product["aliases"]):
                found.append((product, sentence))
    return found


def check_text(
    text: str,
    rules: dict | None = None,
    corpus_urls: set[str] | None = None,
    disabled: set[str] | frozenset[str] = frozenset(),
) -> Result:
    rules = rules or load_rules()
    corpus_urls = load_corpus_urls() if corpus_urls is None else corpus_urls
    body, sources = split_post(text)
    sents = sentences(body)
    words = count_words(body)
    findings: list[Finding] = []
    needs_human = False

    def add(rule: str, severity: str, quote: str, why: str) -> None:
        if rule in disabled:
            return
        if any(f.rule == rule and f.quote == quote for f in findings):
            return
        findings.append(Finding(rule, severity, quote, why))

    # H1: facts must trace to a real story in the corpus.
    source_urls = [_clean_url(u) for line in (sources or []) for u in URL_PATTERN.findall(line)]
    if not source_urls:
        add("H1", "fail", "(no sources block)", "nothing in the post can be traced to a story")
    elif corpus_urls:
        for url in source_urls:
            if url not in corpus_urls:
                add("H1", "fail", url, "cited source is not a story in the corpus")

    # H2 and S2: products only by their approved line, and only one of them.
    mentions = products_mentioned(sents, rules)
    for product, sentence in mentions:
        if not _is_approved_line(sentence, product["claim"]):
            add("H2", "fail", sentence, f"names {product['name']} outside its approved line")
    distinct = []
    for product, _ in mentions:
        if product["name"] not in distinct:
            distinct.append(product["name"])
    if len(distinct) > 1:
        add("S2", "flag", distinct[1], f"{len(distinct)} products mentioned: {', '.join(distinct)}")

    # H3: every figure in the body must appear on a source line.
    scan = body
    for product in rules["products"]:
        scan = re.sub(re.escape(product["claim"]), " ", scan, flags=re.IGNORECASE)
    taken: list[tuple[int, int]] = []
    figures: list[str] = []
    for pattern in FIGURE_PATTERNS:
        for match in pattern.finditer(scan):
            start, end = match.span()
            if any(start < e and end > s for s, e in taken):
                continue
            value = match.group(0).strip()
            if re.fullmatch(r"\d{4}", value) and 1900 <= int(value) <= 2099:
                continue  # a year, not a statistic
            taken.append((start, end))
            figures.append(value)
    source_text = [_norm_figure(line) for line in (sources or [])]
    for figure in figures:
        if not any(_norm_figure(figure) in line for line in source_text):
            add("H3", "fail", figure, "figure has no source line")

    # H4: advice, promises, guarantees.
    for phrase in rules["advice_phrases"]:
        for sentence, matched in _sentence_with(sents, _phrase_regex(phrase)):
            add("H4", "fail", sentence, f"advice or promise: '{matched}'")

    # H5: named customers or members.
    for pattern in NAMED_PERSON_PATTERNS:
        for match in pattern.finditer(body):
            add("H5", "fail", match.group(0), "identifies an individual customer or member")

    # H6: competitors. Disparaging is a fail; a neutral mention is a flag.
    for name in rules["competitors"]:
        for sentence, _ in _sentence_with(sents, _phrase_regex(name)):
            if any(f.rule == "H6" and f.quote == sentence for f in findings):
                continue
            negative = [w for w in rules["disparaging_words"] if _phrase_regex(w).search(sentence)]
            if negative:
                add("H6", "fail", sentence, f"criticises a competitor: '{negative[0]}'")
            else:
                add("H6", "flag", sentence, "names a competitor; approver to confirm it is neutral")

    # H7: sensitive topics never auto-pass, and fail if paired with selling.
    sensitive_hits = []
    for stem in rules["sensitive_patterns"]:
        sensitive_hits += _sentence_with(sents, _phrase_regex(stem, stem=True))
    if sensitive_hits and "H7" not in disabled:
        needs_human = True
        sentence, matched = sensitive_hits[0]
        add("H7", "flag", sentence, f"sensitive topic ('{matched}'): a person must read this")
        for product, p_sentence in mentions:
            if not product["signpost"]:
                add("H7", "fail", p_sentence, f"sells {product['name']} in a post about a sensitive topic")
        for phrase in rules["h7_fail_phrases"]:
            for p_sentence, matched in _sentence_with(sents, _phrase_regex(phrase)):
                add("H7", "fail", p_sentence, f"promotional framing on a sensitive topic: '{matched}'")

    # S1: tone. Marketing filler, exclamation marks, em dashes.
    for word in rules["ai_words"]:
        for _, matched in _sentence_with(sents, _phrase_regex(word)):
            add("S1", "flag", matched, "marketing filler word")
    if "!" in body:
        add("S1", "flag", "!", "exclamation mark")
    if EM_DASH in text:
        add("S1", "flag", EM_DASH, "em dash")

    # S3: honest framing.
    for phrase in rules["hype_phrases"]:
        for _, matched in _sentence_with(sents, _phrase_regex(phrase)):
            add("S3", "flag", matched, "hype or absolute claim")

    # S4: length.
    bounds = rules["word_count"]
    if not bounds["min"] <= words <= bounds["max"]:
        add("S4", "flag", f"{words} words", f"body must be {bounds['min']} to {bounds['max']} words")

    # S5: British spelling.
    for american, british in rules["american_spellings"].items():
        for _, matched in _sentence_with(sents, _phrase_regex(american)):
            add("S5", "flag", matched, f"use '{british}'")

    has_fail = any(f.severity == "fail" for f in findings)
    has_flag = any(f.severity == "flag" for f in findings)
    verdict = "FAIL" if has_fail else "FLAG" if (has_flag or needs_human) else "PASS"
    changes = []
    if has_fail:
        for f in findings:
            if f.severity == "fail":
                changes.append(f"{f.rule}: {FIXES[f.rule]} (\"{_shorten(f.quote)}\")")
    return Result(verdict, needs_human, words, findings, changes)


def _shorten(text: str, limit: int = 80) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def format_result(name: str, result: Result) -> str:
    lines = [
        f"{name}: {result.verdict} ({result.word_count} words, "
        f"needs human: {'yes' if result.needs_human else 'no'})"
    ]
    for f in result.findings:
        lines.append(f"  {f.rule} {f.severity:<4}  \"{_shorten(f.quote)}\"  {f.why}")
    for change in result.what_would_change:
        lines.append(f"  to pass: {change}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("posts", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    parser.add_argument("--strict", action="store_true", help="exit 1 on FLAG, 2 on FAIL")
    parser.add_argument("--disable", action="append", default=[], choices=ALL_RULES,
                        help="switch a rule off (seeded-fault testing only)")
    parser.add_argument("--rules", type=Path, default=None)
    parser.add_argument("--corpus", type=Path, default=None)
    args = parser.parse_args(argv)

    rules = load_rules(args.rules)
    corpus = load_corpus_urls(args.corpus)
    worst = "PASS"
    output = []
    for post in args.posts:
        result = check_text(post.read_text(encoding="utf-8"), rules, corpus, set(args.disable))
        if ["PASS", "FLAG", "FAIL"].index(result.verdict) > ["PASS", "FLAG", "FAIL"].index(worst):
            worst = result.verdict
        if args.json:
            output.append({"file": str(post), **result.to_dict()})
        else:
            print(format_result(str(post), result))
    if args.json:
        print(json.dumps(output, indent=2, ensure_ascii=False))
    if args.strict:
        return {"PASS": 0, "FLAG": 1, "FAIL": 2}[worst]
    return 0


if __name__ == "__main__":
    sys.exit(main())
