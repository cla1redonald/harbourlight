"""Every rule in the checker is proven able to fail, and proven quiet on a clean sample."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from check_post import EM_DASH, check_text, count_words, load_corpus_urls, load_rules  # noqa: E402

RULES = load_rules()
CORPUS = load_corpus_urls()
URL = "https://news.example.invalid/clyde-money-review/2026-09-10-five-year-fixes-trimmed"
FIXED = "The FixedFive Remortgage fixes your monthly payment for five years."
PLANNER = ("The Overpayment Planner shows how an extra payment would change your mortgage "
           "term before you make it.")

# About 140 words of plain, sourced, advice-free prose. Each test adds one poison to it.
FILLER = (
    "The cuts are small, and an average can hide a lot. Ratewatch said there is a wide spread "
    "between deals for borrowers with large deposits and those with smaller ones, so the rate "
    "any one household is offered could sit well above or below the average.\n\n"
    "For members whose deal ends in the next few months, the useful step is a simple one: find "
    "the end date on your annual statement and note it somewhere you will see it. Knowing the "
    "date gives you time to compare options calmly rather than against a deadline."
)
LEAD = (
    "The average five-year fixed mortgage rate fell to 4.49% this week, from 4.62% a month "
    "earlier, according to Ratewatch Data figures reported by the Clyde Money Review. Two-year "
    "fixes fell by less."
)
SOURCES = f"Sources:\n- {URL} (Clyde Money Review, 10 September 2026)\n- 4.49% and 4.62%: {URL}"


def post(*extra: str, lead: str = LEAD, sources: str | None = SOURCES, filler: str = FILLER) -> str:
    parts = ["# Five-year fixes edge down", lead, filler, *extra]
    text = "\n\n".join(parts)
    return text + ("\n\n" + sources if sources is not None else "") + "\n"


def check(text: str, disabled: set[str] | None = None):
    return check_text(text, RULES, CORPUS, disabled or set())


class CleanBaseline(unittest.TestCase):
    def test_clean_post_passes(self):
        result = check(post(FIXED))
        self.assertEqual(result.verdict, "PASS", result.findings)
        self.assertFalse(result.needs_human)
        self.assertTrue(120 <= result.word_count <= 220)


class HardRules(unittest.TestCase):
    def assertFails(self, text: str, rule: str, quote_contains: str):
        result = check(text)
        self.assertEqual(result.verdict, "FAIL", result.findings)
        hits = [f for f in result.findings if f.rule == rule and f.severity == "fail"]
        self.assertTrue(hits, f"{rule} did not fire: {result.findings}")
        self.assertTrue(any(quote_contains in f.quote for f in hits), [f.quote for f in hits])
        self.assertTrue(any(c.startswith(rule) for c in result.what_would_change))

    def assertNoRule(self, text: str, rule: str):
        result = check(text)
        self.assertNotIn(rule, result.rules(), result.findings)

    # H1
    def test_h1_poison_no_sources(self):
        self.assertFails(post(sources=None, lead="Five-year fixes fell a little this week."),
                         "H1", "(no sources block)")

    def test_h1_poison_unknown_url(self):
        fake = "https://news.example.invalid/made-up/2026-09-01-story"
        self.assertFails(post(sources=f"Sources:\n- {fake}\n- 4.49% and 4.62%: {fake}"), "H1", fake)

    def test_h1_clean(self):
        self.assertNoRule(post(), "H1")

    # H2
    def test_h2_poison(self):
        self.assertFails(post("The FixedFive Remortgage is the cheapest fix around."), "H2",
                         "cheapest fix around")

    def test_h2_clean(self):
        self.assertNoRule(post(FIXED), "H2")

    def test_h2_poison_extra_words_around_the_approved_line(self):
        # Containing the approved line is not enough: nothing may ride alongside it.
        self.assertFails(post(FIXED[:-1] + ", and it beats every rival on the market."), "H2",
                         "beats every rival")
        self.assertFails(post("Members tell us " + FIXED[0].lower() + FIXED[1:]), "H2",
                         "Members tell us")

    def test_h2_clean_with_quotes_and_punctuation(self):
        self.assertNoRule(post('"' + FIXED + '"'), "H2")
        self.assertNoRule(post(FIXED[:-1] + "!"), "H2")

    # H3
    def test_h3_poison_percent(self):
        self.assertFails(post("Around 68% of borrowers plan to fix."), "H3", "68%")

    def test_h3_poison_money(self):
        self.assertFails(post("A typical saving is £1,200 a year."), "H3", "£1,200")

    def test_h3_clean_and_years_ignored(self):
        self.assertNoRule(post("Rates were lower in 2021."), "H3")

    # H4
    def test_h4_poison(self):
        self.assertFails(post("Fixing now is guaranteed to pay off."), "H4", "guaranteed")

    def test_h4_clean(self):
        self.assertNoRule(post("Some members fix and some do not; both can be reasonable."), "H4")

    # H5
    def test_h5_poison_title(self):
        self.assertFails(post("Mrs Ritchie told us she fixed last week."), "H5", "Mrs Ritchie")

    def test_h5_poison_member_name(self):
        self.assertFails(post("Our member Ishbel Kerr fixed last week."), "H5", "member Ishbel Kerr")

    def test_h5_clean(self):
        self.assertNoRule(post("Many members fixed last month."), "H5")

    # H6
    def test_h6_poison(self):
        self.assertFails(post("Unlike Firthmoor Bank, we answer the phone."), "H6", "Firthmoor Bank")

    def test_h6_neutral_mention_is_flag(self):
        result = check(post("Kinnaird Mutual also trimmed its rates."))
        self.assertEqual(result.verdict, "FLAG")
        self.assertEqual([f.severity for f in result.findings if f.rule == "H6"], ["flag"])

    def test_h6_clean(self):
        self.assertNoRule(post(), "H6")

    # H7
    def test_h7_sensitive_never_auto_passes(self):
        result = check(post("If you are behind on payments, talk to us early."))
        self.assertEqual(result.verdict, "FLAG")
        self.assertTrue(result.needs_human)

    def test_h7_poison_product_on_sensitive_topic(self):
        self.assertFails(post("Arrears are rising across the country.", PLANNER), "H7",
                         "Overpayment Planner")

    def test_h7_poison_promo_on_sensitive_topic(self):
        self.assertFails(post("Scam texts are rising. Great news: we can help."), "H7", "Great news")

    def test_h7_signpost_allowed(self):
        steady = ("The Steady Ground support line gives members who are worried about payments a "
                  "named contact to talk through their options.")
        result = check(post("Arrears are rising across the country.", steady))
        self.assertEqual(result.verdict, "FLAG", result.findings)

    def test_h7_clean(self):
        result = check(post())
        self.assertFalse(result.needs_human)


class SoftRules(unittest.TestCase):
    def assertFlags(self, text: str, rule: str, quote_contains: str):
        result = check(text)
        self.assertEqual(result.verdict, "FLAG", result.findings)
        hits = [f for f in result.findings if f.rule == rule]
        self.assertTrue(hits, f"{rule} did not fire: {result.findings}")
        self.assertTrue(any(quote_contains in f.quote for f in hits), [f.quote for f in hits])

    def test_s1_poison_ai_word(self):
        self.assertFlags(post("This is a seamless way to compare."), "S1", "seamless")

    def test_s1_poison_exclamation(self):
        self.assertFlags(post("Check your date today!"), "S1", "!")

    def test_s1_poison_em_dash(self):
        self.assertFlags(post(f"Check your date {EM_DASH} today."), "S1", EM_DASH)

    def test_s1_clean(self):
        self.assertNotIn("S1", check(post()).rules())

    def test_s2_poison(self):
        self.assertFlags(post(FIXED, PLANNER), "S2", "Overpayment Planner")

    def test_s2_clean(self):
        self.assertNotIn("S2", check(post(FIXED)).rules())

    def test_s3_poison(self):
        self.assertFlags(post("Fixing is a no-brainer."), "S3", "no-brainer")

    def test_s3_clean(self):
        self.assertNotIn("S3", check(post()).rules())

    def test_s4_poison_short(self):
        self.assertFlags(post(filler=""), "S4", "words")

    def test_s4_poison_long(self):
        self.assertFlags(post(FILLER, FILLER), "S4", "words")

    def test_s4_clean(self):
        self.assertNotIn("S4", check(post()).rules())

    def test_s5_poison(self):
        self.assertFlags(post("Damp can lead to mold."), "S5", "mold")

    def test_s5_clean(self):
        self.assertNotIn("S5", check(post("Damp can lead to mould.")).rules())


class Mechanics(unittest.TestCase):
    def test_disabled_rule_does_not_fire(self):
        result = check(post("Around 68% of borrowers plan to fix."), disabled={"H3"})
        self.assertNotIn("H3", result.rules())

    def test_front_matter_and_headline_not_counted(self):
        body = "---\nstory: S01\n---\n# A headline here\n\none two three\n"
        self.assertEqual(count_words(body.split("---\n", 2)[2]), 3)

    def test_figures_inside_approved_claims_are_ignored(self):
        rules = json.loads(json.dumps(RULES))
        rules["products"][0]["claim"] = "The FixedFive Remortgage fixes your payment for 5.5 years."
        result = check_text(post("The FixedFive Remortgage fixes your payment for 5.5 years."), rules, CORPUS)
        self.assertNotIn("H3", result.rules())

    def test_cli_strict_exit_codes(self):
        posts = HERE.parent / "data-pristine" / "posts"
        if not posts.exists():
            posts = HERE.parent / "data" / "posts"
        script = str(HERE / "check_post.py")
        for name, expected in [("2026-09-08-base-rate-holds.draft.md", 0),
                               ("2026-09-15-payment-holiday-texts.draft.md", 1),
                               ("2026-09-22-storm-repairs.draft.md", 2)]:
            run = subprocess.run([sys.executable, script, "--strict", str(posts / name)],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, expected, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
