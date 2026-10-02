#!/usr/bin/env python3
"""Fixed-seed differential checks over newly generated finite problems.

This is a deterministic fault-detection campaign, not a statistical sample of
production pipelines.  Exact generated inputs are written beside the results.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
import json
from pathlib import Path
import random
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from drift_contracts.portfolio import (
    build_conflict_analysis, is_safe, make_optimal_certificate,
    make_unsafe_certificate, optimize_portfolio, shortest_failure,
)
from drift_contracts.portfolio_model import MonitorUpdate, PortfolioProblem, RetentionAtom
from drift_contracts.portfolio_verify import verify_optimal, verify_safe, verify_unsafe


def _table(rng: random.Random, states: int, alphabet: int) -> tuple[tuple[int, ...], ...]:
    return tuple(tuple(rng.randrange(states) for _ in range(alphabet))
                 for _ in range(states))


def _problem(rng: random.Random, index: int) -> PortfolioProblem:
    history_width = rng.randint(1, 2)
    future_width = rng.randint(1, 2)
    atom_count = rng.randint(2, 4)
    update_count = rng.randint(1, 2)
    atoms = []
    for atom_index in range(atom_count):
        states = rng.randint(1, 3)
        atoms.append(RetentionAtom(
            name=f"a{atom_index}",
            cost=rng.randint(1, 5),
            transition=_table(rng, states, history_width),
            initial=rng.randrange(states),
        ))
    updates = []
    for update_index in range(update_count):
        states = rng.randint(1, 3)
        updates.append(MonitorUpdate(
            name=f"u{update_index}",
            history=_table(rng, states, history_width),
            future=_table(rng, states, future_width),
            output=tuple(rng.randrange(2) for _ in range(states)),
            initial=rng.randrange(states),
        ))
    return PortfolioProblem(
        name=f"random-{index:04d}",
        history_symbols=tuple(f"h{i}" for i in range(history_width)),
        future_symbols=tuple(f"f{i}" for i in range(future_width)),
        atoms=tuple(atoms),
        updates=tuple(updates),
        metadata={"generator": "fixed-seed bounded extensional tables"},
    )


def _encode(problem: PortfolioProblem) -> dict[str, Any]:
    return {
        "name": problem.name,
        "history_symbols": list(problem.history_symbols),
        "future_symbols": list(problem.future_symbols),
        "atoms": [
            {
                "name": atom.name,
                "cost": atom.cost,
                "initial": atom.initial,
                "transition": [list(row) for row in atom.transition],
            }
            for atom in problem.atoms
        ],
        "updates": [
            {
                "name": update.name,
                "initial": update.initial,
                "history": [list(row) for row in update.history],
                "future": [list(row) for row in update.future],
                "output": list(update.output),
            }
            for update in problem.updates
        ],
    }


def _independent_optimum(problem: PortfolioProblem) -> tuple[int, int] | None:
    best: tuple[int, int, int] | None = None
    for mask in range(1 << len(problem.atoms)):
        if not verify_safe(problem, mask):
            continue
        candidate = (problem.cost(mask), mask.bit_count(), mask)
        if best is None or candidate < best:
            best = candidate
    return None if best is None else (best[2], best[0])


def run(output: Path, *, seed: int, problems: int) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"output must not already exist: {output}")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    if type(problems) is not int or problems <= 0:
        raise ValueError("problems must be a positive integer")
    output.mkdir(parents=True)
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    inputs: list[str] = []
    safety_mismatches = 0
    optimizer_mismatches = 0
    certificate_failures = 0
    masks_checked = 0
    feasible = 0
    infeasible = 0

    for index in range(problems):
        problem = _problem(rng, index)
        inputs.append(json.dumps(_encode(problem), sort_keys=True, separators=(",", ":")))
        analysis = build_conflict_analysis(problem)
        for mask in range(1 << len(problem.atoms)):
            masks_checked += 1
            if is_safe(mask, analysis) != verify_safe(problem, mask):
                safety_mismatches += 1
        result = optimize_portfolio(problem, analysis)
        oracle = _independent_optimum(problem)
        expected = None if oracle is None else {"mask": oracle[0], "cost": oracle[1]}
        actual = None if not result["feasible"] else {
            "mask": int(result["selected_mask"]), "cost": int(result["cost"])}
        if actual != expected:
            optimizer_mismatches += 1
        certificate_valid = False
        if result["feasible"]:
            feasible += 1
            certificate = make_optimal_certificate(problem, analysis, int(result["selected_mask"]))
            certificate_valid = verify_optimal(problem, certificate)
        else:
            infeasible += 1
            witness = shortest_failure(problem.all_mask, analysis)
            certificate_valid = bool(
                witness is not None
                and witness.separator_mask == 0
                and verify_unsafe(problem, make_unsafe_certificate(problem, problem.all_mask, witness))
            )
        if not certificate_valid:
            certificate_failures += 1
        rows.append({
            "problem": problem.name,
            "atoms": len(problem.atoms),
            "updates": len(problem.updates),
            "masks_checked": 1 << len(problem.atoms),
            "feasible": result["feasible"],
            "selected_mask": result["selected_mask"],
            "selected_cost": result["cost"],
            "oracle_mask": None if oracle is None else oracle[0],
            "oracle_cost": None if oracle is None else oracle[1],
            "certificate_valid": certificate_valid,
        })

    (output / "problems.jsonl").write_text("\n".join(inputs) + "\n", encoding="utf-8")
    with (output / "cases.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "scope": "fixed-seed bounded differential fault detection; not a statistical population estimate",
        "seed": seed,
        "problems": problems,
        "portfolio_masks_checked": masks_checked,
        "feasible_problems": feasible,
        "infeasible_problems": infeasible,
        "safety_mismatches": safety_mismatches,
        "optimizer_mismatches": optimizer_mismatches,
        "certificate_failures": certificate_failures,
        "status": "pass" if safety_mismatches == optimizer_mismatches == certificate_failures == 0 else "fail",
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260915)
    parser.add_argument("--problems", type=int, default=256)
    args = parser.parse_args()
    try:
        summary = run(args.output, seed=args.seed, problems=args.problems)
    except (OSError, ValueError) as exc:
        print(f"random differential check failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["status"] == "pass" else 3


if __name__ == "__main__":
    raise SystemExit(main())
