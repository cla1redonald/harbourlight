"""Cost ledger for every live call this repo makes to the Claude API.

Every response's `usage` is priced at list rates, appended to
evals/results/spend.jsonl with the model id, and added to a running total that
is read back from the file, so the total survives across processes and runs.

The hard stop is a constant in this file, on purpose. There is no flag,
environment variable or argument that raises it: spending past it means editing
this code, in a commit someone can see. When the running total passes it, the
process exits at once with status 3, after writing the row that crossed it.

    from ledger import Ledger
    ledger = Ledger()
    ledger.check()                       # before a call: abort if already over
    ledger.record(model, response.usage, label="H1a")

Prices are US dollars per million tokens, list rates, as published for each
model (see docs/design/0005-phase-2b.md for the source and date).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HARD_STOP_USD = 50.00
ABORT_EXIT_CODE = 3

DEFAULT_PATH = Path(__file__).resolve().parent / "results" / "spend.jsonl"


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float
    cache_write_5m: float
    # Claude Haiku 5.5 bills a prompt over 100K tokens on a second, higher card.
    long_prompt_threshold: int | None = None
    long_input: float | None = None
    long_output: float | None = None


PRICES: dict[str, Price] = {
    # Cache writes (5-minute TTL) are 1.25x the input rate on both models.
    "claude-sonnet-5-5": Price(input=2.00, output=10.00, cache_read=0.20, cache_write_5m=2.50),
    "claude-haiku-5-5": Price(input=0.10, output=0.50, cache_read=0.01, cache_write_5m=0.125,
                              long_prompt_threshold=100_000, long_input=0.50, long_output=2.50),
}


class SpendCeilingReached(SystemExit):
    """Raised (and exits the process) when the running total passes HARD_STOP_USD."""


def _field(usage: Any, name: str) -> int:
    value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
    if isinstance(value, dict):  # some APIs break a count down by TTL; add the parts
        return sum(int(v or 0) for v in value.values() if isinstance(v, (int, float)))
    if value is not None and not isinstance(value, (int, float, str)):
        value = sum(int(v or 0) for v in vars(value).values() if isinstance(v, (int, float)))
    return int(value or 0)


def usage_dict(usage: Any) -> dict[str, int]:
    return {
        "input_tokens": _field(usage, "input_tokens"),
        "output_tokens": _field(usage, "output_tokens"),
        "cache_read_input_tokens": _field(usage, "cache_read_input_tokens"),
        "cache_creation_input_tokens": _field(usage, "cache_creation_input_tokens"),
    }


def cost_usd(model: str, usage: Any) -> float:
    """Price one response's usage at list rates. Unknown models are refused, not guessed."""
    if model not in PRICES:
        raise KeyError(f"no list price recorded for {model!r}; add it to PRICES before calling it")
    price = PRICES[model]
    u = usage_dict(usage)
    prompt = u["input_tokens"] + u["cache_read_input_tokens"] + u["cache_creation_input_tokens"]
    rate_in, rate_out = price.input, price.output
    cache_read, cache_write = price.cache_read, price.cache_write_5m
    if price.long_prompt_threshold is not None and prompt > price.long_prompt_threshold:
        scale = price.long_input / price.input
        rate_in, rate_out = price.long_input, price.long_output
        cache_read, cache_write = cache_read * scale, cache_write * scale
    return (
        u["input_tokens"] * rate_in
        + u["output_tokens"] * rate_out
        + u["cache_read_input_tokens"] * cache_read
        + u["cache_creation_input_tokens"] * cache_write
    ) / 1_000_000


class Ledger:
    def __init__(self, path: Path = DEFAULT_PATH, hard_stop: float | None = None) -> None:
        # `hard_stop` exists only so the tests can prove the abort with pennies. It can
        # lower the ceiling, never raise it.
        self.path = path
        self.hard_stop = HARD_STOP_USD if hard_stop is None else min(hard_stop, HARD_STOP_USD)
        self.total = self._read_total()

    def _read_total(self) -> float:
        if not self.path.exists():
            return 0.0
        total = 0.0
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                total += float(json.loads(line)["cost_usd"])
        return total

    def check(self) -> None:
        """Call before every request. Exits if the ceiling has already been passed."""
        if self.total > self.hard_stop:
            self._abort()

    def record(self, model: str, usage: Any, label: str = "", run: str = "",
               request_id: str | None = None, estimated: bool = False) -> float:
        cost = cost_usd(model, usage)
        self.total += cost
        row = {
            "at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "run": run,
            "label": label,
            "model": model,
            "request_id": request_id,
            "estimated": estimated,
            **usage_dict(usage),
            "cost_usd": round(cost, 8),
            "running_total_usd": round(self.total, 6),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        if self.total > self.hard_stop:
            self._abort()
        return cost

    def record_cost(self, model: str, usd: float, label: str = "", run: str = "",
                    usage: Any = None) -> float:
        """Record spend the platform priced itself, such as a Managed Agents session's list cost
        (tokens plus session running time). Counts against the same hard stop."""
        self.total += usd
        row = {
            "at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "run": run, "label": label, "model": model, "request_id": None,
            "estimated": False, "platform_priced": True,
            **(usage_dict(usage) if usage is not None else {}),
            "cost_usd": round(usd, 8), "running_total_usd": round(self.total, 6),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        if self.total > self.hard_stop:
            self._abort()
        return usd

    def _abort(self) -> None:
        message = (f"SPEND CEILING: running total ${self.total:.4f} has passed the hard stop of "
                   f"${self.hard_stop:.2f} recorded in {self.path}. Stopping now.")
        print(message, file=sys.stderr)
        raise SpendCeilingReached(ABORT_EXIT_CODE)


def summary(path: Path = DEFAULT_PATH) -> dict:
    """Totals by model and by run, for reports."""
    by_model: dict[str, float] = {}
    by_run: dict[str, float] = {}
    calls = 0
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            calls += 1
            by_model[row["model"]] = by_model.get(row["model"], 0.0) + row["cost_usd"]
            by_run[row["run"]] = by_run.get(row["run"], 0.0) + row["cost_usd"]
    return {"calls": calls, "total_usd": sum(by_model.values()), "by_model": by_model,
            "by_run": by_run, "hard_stop_usd": HARD_STOP_USD}


if __name__ == "__main__":
    print(json.dumps(summary(), indent=2))
