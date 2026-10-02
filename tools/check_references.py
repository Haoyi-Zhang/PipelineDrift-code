#!/usr/bin/env python3
"""Check manuscript citations, BibTeX, verification ledger, and calibration matrix."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from drift_contracts.bibliography import BibliographyError, audit_bibliography


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bib", type=Path, required=True)
    parser.add_argument("--tex", type=Path, action="append", required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--minimum-cited", type=int, default=55)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_bibliography(
        bib_path=args.bib,
        tex_paths=args.tex,
        ledger_path=args.ledger,
        calibration_path=args.calibration,
        minimum_cited=args.minimum_cited,
    )
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BibliographyError, OSError, ValueError) as exc:
        print(f"reference check failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
