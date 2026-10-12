#!/usr/bin/env python3
"""Put data/ back to the seeded demo state from data-pristine/.

This is the one deliberate exception to "logs are append-only": it exists so
a team can practise on the demo and start again. Never point it at a real log.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def reset(root: Path = ROOT) -> None:
    pristine = root / "data-pristine"
    data = root / "data"
    if not pristine.is_dir():
        raise FileNotFoundError(f"{pristine} is missing; nothing to restore from")
    if data.exists():
        shutil.rmtree(data)
    shutil.copytree(pristine, data)


def main() -> int:
    try:
        reset()
    except FileNotFoundError as error:
        print(error, file=sys.stderr)
        return 1
    print("data/ restored from data-pristine/ (seeded September 2026 demo state)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
