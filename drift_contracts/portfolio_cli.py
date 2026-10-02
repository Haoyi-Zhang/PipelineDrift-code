"""Command-line analysis for declarative retention portfolios."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from .portfolio import (build_conflict_analysis, is_safe, make_optimal_certificate,
                        make_unsafe_certificate, optimize_portfolio, shortest_failure)
from .portfolio_dsl import load_declaration
from .portfolio_verify import verify_optimal, verify_safe, verify_unsafe


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("declaration", type=Path)
    parser.add_argument("--selected", type=int,
                        help="also check this numeric atom mask")
    args = parser.parse_args(argv)
    try:
        problem = load_declaration(args.declaration)
        analysis = build_conflict_analysis(problem)
        optimum = optimize_portfolio(problem, analysis)
        verification_failed = False
        result = {
            "problem": problem.name,
            "atoms": [{"name": atom.name, "cost": atom.cost,
                       "states": len(atom.transition)} for atom in problem.atoms],
            "updates": [{"name": update.name, "states": len(update.history)}
                        for update in problem.updates],
            "obstruction_basis": list(analysis.obligations),
            "feasible": optimum["feasible"],
            "optimal_mask": optimum["selected_mask"],
            "optimal_atoms": [] if optimum["selected_mask"] is None else
                             problem.selected_names(int(optimum["selected_mask"])),
            "optimal_cost": optimum["cost"],
        }
        if optimum["feasible"]:
            certificate = make_optimal_certificate(
                problem, analysis, int(optimum["selected_mask"]))
            valid = verify_optimal(problem, certificate)
            result["certificate"] = certificate
            result["certificate_valid"] = valid
            verification_failed |= not valid
        else:
            witness = shortest_failure(problem.all_mask, analysis)
            certificate = (make_unsafe_certificate(problem, problem.all_mask, witness)
                           if witness is not None else None)
            valid = bool(certificate and certificate.get("separator_mask") == 0 and
                         verify_unsafe(problem, certificate) and
                         not verify_safe(problem, problem.all_mask))
            result["certificate"] = certificate
            result["certificate_valid"] = valid
            verification_failed |= not valid
        if args.selected is not None:
            problem.cost(args.selected)
            predicted_safe = is_safe(args.selected, analysis)
            checked_safe = verify_safe(problem, args.selected)
            selected = {"mask": args.selected,
                        "atoms": problem.selected_names(args.selected),
                        "cost": problem.cost(args.selected),
                        "safe": predicted_safe,
                        "safety_check_valid": predicted_safe == checked_safe}
            verification_failed |= predicted_safe != checked_safe
            if not predicted_safe:
                witness = shortest_failure(args.selected, analysis)
                cert = (make_unsafe_certificate(problem, args.selected, witness)
                        if witness is not None else None)
                valid = bool(cert and verify_unsafe(problem, cert))
                selected["certificate"] = cert
                selected["certificate_valid"] = valid
                verification_failed |= not valid
            result["selected"] = selected
        print(json.dumps(result, indent=2, sort_keys=True))
        # A scientifically negative diagnosis is a successful analysis when its
        # evidence verifies.  Any produced main/selected certificate failure is
        # an execution failure and therefore returns nonzero.
        return 3 if verification_failed else 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
