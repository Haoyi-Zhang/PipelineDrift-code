#!/usr/bin/env python3
"""Deterministic one-at-a-time sensitivity analysis for declared atom costs."""
from __future__ import annotations

import argparse
import csv
from dataclasses import replace
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from drift_contracts.portfolio import build_conflict_analysis, make_optimal_certificate, optimize_portfolio
from drift_contracts.portfolio_dsl import load_declaration
from drift_contracts.portfolio_verify import verify_optimal, verify_safe


def run(output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"output must not already exist: {output}")
    output.mkdir(parents=True)
    rows: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []
    feasible_declarations = 0
    infeasible_declarations = 0
    certificate_failures = 0

    for path in sorted((ROOT / "declarations").glob("*.json")):
        problem = load_declaration(path)
        analysis = build_conflict_analysis(problem)
        baseline = optimize_portfolio(problem, analysis)
        if not baseline["feasible"]:
            infeasible_declarations += 1
            continue
        feasible_declarations += 1
        baseline_mask = int(baseline["selected_mask"])
        baseline_cost = int(baseline["cost"])
        baseline_vector = tuple(atom.cost for atom in problem.atoms)
        seen_vectors: set[tuple[int, ...]] = set()
        vectors: list[tuple[str, int, int, tuple[int, ...]]] = []
        for index, atom in enumerate(problem.atoms):
            candidates = []
            if atom.cost > 1:
                candidates.append(atom.cost - 1)
            candidates.append(atom.cost + 1)
            for value in candidates:
                vector = list(baseline_vector)
                vector[index] = value
                frozen = tuple(vector)
                if frozen in seen_vectors:
                    continue
                seen_vectors.add(frozen)
                vectors.append((atom.name, atom.cost, value, frozen))
        inputs.append({
            "declaration": problem.name,
            "baseline_cost_vector": list(baseline_vector),
            "perturbed_cost_vectors": [list(item[3]) for item in vectors],
        })
        for atom_name, old_cost, new_cost, vector in vectors:
            changed_atoms = tuple(replace(atom, cost=vector[i])
                                  for i, atom in enumerate(problem.atoms))
            changed = replace(problem, atoms=changed_atoms)
            result = optimize_portfolio(changed, analysis)
            if not result["feasible"]:
                raise AssertionError("cost-only perturbation changed feasibility")
            mask = int(result["selected_mask"])
            cost = int(result["cost"])
            certificate = make_optimal_certificate(changed, analysis, mask)
            certificate_valid = verify_optimal(changed, certificate)
            safe = verify_safe(changed, mask)
            if not certificate_valid or not safe:
                certificate_failures += 1
            rows.append({
                "declaration": problem.name,
                "atom": atom_name,
                "old_cost": old_cost,
                "new_cost": new_cost,
                "baseline_mask": baseline_mask,
                "baseline_optimal_cost": baseline_cost,
                "perturbed_mask": mask,
                "perturbed_optimal_cost": cost,
                "mask_changed": mask != baseline_mask,
                "numeric_optimum_changed": cost != baseline_cost,
                "certificate_valid": certificate_valid,
            })

    if not rows:
        raise RuntimeError("no feasible declaration produced a sensitivity case")
    with (output / "variations.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (output / "inputs.json").write_text(
        json.dumps(inputs, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "scope": "one-at-a-time integer cost perturbations over shipped feasible declarations; no claim about real storage prices",
        "feasible_declarations": feasible_declarations,
        "infeasible_declarations_skipped": infeasible_declarations,
        "perturbations": len(rows),
        "optimal_mask_changes": sum(bool(row["mask_changed"]) for row in rows),
        "numeric_optimum_changes": sum(bool(row["numeric_optimum_changed"]) for row in rows),
        "declarations_with_mask_change": len({row["declaration"] for row in rows if row["mask_changed"]}),
        "certificate_failures": certificate_failures,
        "status": "pass" if certificate_failures == 0 else "fail",
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = run(args.output)
    except (OSError, ValueError, RuntimeError, AssertionError) as exc:
        print(f"cost sensitivity failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["status"] == "pass" else 3


if __name__ == "__main__":
    raise SystemExit(main())
