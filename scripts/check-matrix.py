#!/usr/bin/env python3
"""Thin runner: `./scripts/check-matrix.py` — see scripts/check_matrix.py for logic."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.check_matrix import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
