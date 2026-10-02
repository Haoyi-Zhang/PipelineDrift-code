from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from . import Contract, analyze, verify


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit exact, replay-equivalent finite monitor migration.")
    parser.add_argument("case", type=Path)
    parser.add_argument("--certificate", type=Path, help="check this certificate instead of searching")
    args = parser.parse_args()
    try:
        data = json.loads(args.case.read_text())
        if not isinstance(data, dict):
            raise ValueError("case must be a JSON object")
        c = Contract.from_dict(data["contract"] if "contract" in data else data)
        if args.certificate:
            cert = json.loads(args.certificate.read_text())
            if isinstance(cert, dict) and "certificate" in cert:
                cert = cert["certificate"]
            valid = verify(c, cert)
            print(json.dumps({"valid_certificate": valid}))
            return 0 if valid else 2
        result = analyze(c)
        if not verify(c, result["certificate"]):
            raise RuntimeError("internally produced certificate did not verify")
        print(json.dumps(result, indent=2))
        # Both admissible and inadmissible are successfully computed results.
        return 0
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
