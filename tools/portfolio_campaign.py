#!/usr/bin/env python3
"""Run the exact retention-portfolio validation campaign.

Only Python's standard library is used.  Output paths are created atomically at
file granularity and existing campaign files are not overwritten unless
--replace is supplied.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import replace
import json
import os
from pathlib import Path
import resource
import sys
import time
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from drift_contracts.portfolio import (analyze_selected, build_conflict_analysis,
    greedy_portfolio, independent_union_baseline, is_safe, make_optimal_certificate,
    make_unsafe_certificate, optimize_portfolio, shortest_failure)
from drift_contracts.portfolio_cases import binary_catalogue, unary_catalogue
from drift_contracts.portfolio_dsl import load_declaration
from drift_contracts.portfolio_model import MonitorUpdate, PortfolioProblem, run_table
from drift_contracts.portfolio_verify import verify_optimal, verify_safe, verify_unsafe
from drift_contracts.limits import require_subset_budget


def _write_json(path: Path, value: Any, replace_existing: bool) -> None:
    if path.exists() and not replace_existing:
        raise FileExistsError(f"refusing to overwrite {path}")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _word_state(problem: PortfolioProblem, update_index: int, word: tuple[int, ...], mask: int):
    summary = tuple(run_table(atom.transition, atom.initial, word)
                    for i, atom in enumerate(problem.atoms) if mask >> i & 1)
    update = problem.updates[update_index]
    target = run_table(update.history, update.initial, word)
    return summary, target


def _unary_minimum(problem: PortfolioProblem, mask: int) -> int | None:
    """Direct word enumeration for unary catalogues; no conflict-basis calls."""
    assert len(problem.history_symbols) == len(problem.future_symbols) == 1
    answer: int | None = None
    for update_index, update in enumerate(problem.updates):
        state_bound = len(update.history)
        for i, atom in enumerate(problem.atoms):
            if mask >> i & 1:
                state_bound *= len(atom.transition)
        histories = [tuple(0 for _ in range(length)) for length in range(state_bound)]
        endpoints = [_word_state(problem, update_index, word, mask) for word in histories]
        for i, left in enumerate(histories):
            left_summary, p = endpoints[i]
            for j in range(i + 1, len(histories)):
                right = histories[j]
                right_summary, q = endpoints[j]
                if left_summary != right_summary:
                    continue
                for length in range(len(update.history) ** 2):
                    suffix = tuple(0 for _ in range(length))
                    pp = run_table(update.future, p, suffix)
                    qq = run_table(update.future, q, suffix)
                    if update.output[pp] != update.output[qq]:
                        cost = len(left) + len(right) + length
                        if answer is None or cost < answer:
                            answer = cost
                        break
    return answer


def _independent_best(problem: PortfolioProblem) -> tuple[int, int] | None:
    best: tuple[int, int, int] | None = None
    subset_count = require_subset_budget(len(problem.atoms), "campaign independent optimum")
    for mask in range(subset_count):
        if verify_safe(problem, mask):
            candidate = (problem.cost(mask), mask.bit_count(), mask)
            if best is None or candidate < best:
                best = candidate
    return None if best is None else (best[2], best[0])


def _run_catalogue(name: str, cases: Iterable, csv_path: Path,
                   witness_minimum: bool, replace_existing: bool) -> dict[str, Any]:
    if csv_path.exists() and not replace_existing:
        raise FileExistsError(f"refusing to overwrite {csv_path}")
    tmp = csv_path.with_suffix(csv_path.suffix + ".tmp")
    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    cases_count = feasible_count = safe_masks = unsafe_masks = 0
    safety_mismatch = optimizer_mismatch = certificate_failure = witness_mismatch = 0
    total_nodes = total_pruned = 0
    basis_sizes: list[int] = []
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = ["case_id", "encoding", "feasible", "basis", "safe_masks",
                      "optimal_mask", "optimal_cost", "nodes", "pruned",
                      "safety_mismatches", "certificate_failures", "witness_mismatches"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for case_id, problem, encoding in cases:
            analysis = build_conflict_analysis(problem)
            basis_sizes.append(len(analysis.obligations))
            case_safe = case_safety_mismatch = case_certificate_failure = case_witness_mismatch = 0
            subset_count = require_subset_budget(len(problem.atoms), f"campaign {case_id}")
            for mask in range(subset_count):
                predicted = is_safe(mask, analysis)
                checked = verify_safe(problem, mask)
                if predicted != checked:
                    case_safety_mismatch += 1
                if checked:
                    case_safe += 1
                else:
                    witness = shortest_failure(mask, analysis)
                    if witness is None:
                        case_certificate_failure += 1
                    else:
                        certificate = make_unsafe_certificate(problem, mask, witness)
                        if not verify_unsafe(problem, certificate):
                            case_certificate_failure += 1
                        if witness_minimum:
                            direct = _unary_minimum(problem, mask)
                            if direct != witness.cost:
                                case_witness_mismatch += 1
            result = optimize_portfolio(problem, analysis)
            independent = _independent_best(problem)
            if result["feasible"]:
                feasible_count += 1
                certificate = make_optimal_certificate(
                    problem, analysis, int(result["selected_mask"]))
                if not verify_optimal(problem, certificate):
                    case_certificate_failure += 1
                optimized = (int(result["selected_mask"]), int(result["cost"]))
            else:
                optimized = None
            if optimized != independent:
                optimizer_mismatch += 1
            cases_count += 1
            safe_masks += case_safe
            unsafe_masks += subset_count - case_safe
            safety_mismatch += case_safety_mismatch
            certificate_failure += case_certificate_failure
            witness_mismatch += case_witness_mismatch
            total_nodes += int(result["nodes"])
            total_pruned += int(result["pruned"])
            writer.writerow({
                "case_id": case_id,
                "encoding": ":".join(map(str, encoding)),
                "feasible": int(result["feasible"]),
                "basis": ";".join(map(str, analysis.obligations)),
                "safe_masks": case_safe,
                "optimal_mask": "" if result["selected_mask"] is None else result["selected_mask"],
                "optimal_cost": "" if result["cost"] is None else result["cost"],
                "nodes": result["nodes"], "pruned": result["pruned"],
                "safety_mismatches": case_safety_mismatch,
                "certificate_failures": case_certificate_failure,
                "witness_mismatches": case_witness_mismatch,
            })
    os.replace(tmp, csv_path)
    return {
        "name": name,
        "cases": cases_count,
        "feasible_candidate_catalogues": feasible_count,
        "safe_portfolio_masks": safe_masks,
        "unsafe_portfolio_masks": unsafe_masks,
        "safety_equivalence_mismatches": safety_mismatch,
        "optimizer_mismatches": optimizer_mismatch,
        "certificate_failures": certificate_failure,
        "minimum_witness_mismatches": witness_mismatch,
        "basis_size_min": min(basis_sizes),
        "basis_size_max": max(basis_sizes),
        "branch_nodes": total_nodes,
        "branch_pruned": total_pruned,
        "wall_seconds": time.perf_counter() - started_wall,
        "cpu_seconds": time.process_time() - started_cpu,
        "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }


def _example_record(path: Path) -> tuple[dict[str, Any], PortfolioProblem, Any, dict[str, Any]]:
    problem = load_declaration(path)
    analysis = build_conflict_analysis(problem)
    optimum = optimize_portfolio(problem, analysis)
    greedy = greedy_portfolio(problem, analysis)
    separate = independent_union_baseline(problem, analysis)
    record: dict[str, Any] = {
        "name": problem.name,
        "source": str(path.relative_to(ROOT)),
        "history_records": len(problem.history_symbols),
        "future_records": len(problem.future_symbols),
        "candidate_atoms": len(problem.atoms),
        "updates": len(problem.updates),
        "candidate_cost": sum(atom.cost for atom in problem.atoms),
        "conflict_pairs": analysis.conflict_pairs,
        "obstruction_basis": list(analysis.obligations),
        "feasible": optimum["feasible"],
        "optimal_mask": optimum["selected_mask"],
        "optimal_atoms": [] if optimum["selected_mask"] is None else problem.selected_names(int(optimum["selected_mask"])),
        "optimal_cost": optimum["cost"],
        "greedy_mask": greedy,
        "greedy_atoms": [] if greedy is None else problem.selected_names(greedy),
        "greedy_cost": None if greedy is None else problem.cost(greedy),
        "per_update_union_mask": separate,
        "per_update_union_atoms": [] if separate is None else problem.selected_names(separate),
        "per_update_union_cost": None if separate is None else problem.cost(separate),
        "reachable_signatures": list(analysis.reachable_signatures),
    }
    certificate: dict[str, Any]
    if optimum["feasible"]:
        certificate = make_optimal_certificate(
            problem, analysis, int(optimum["selected_mask"]))
        record["certificate_valid"] = verify_optimal(problem, certificate)
    else:
        witness = shortest_failure(problem.all_mask, analysis)
        certificate = make_unsafe_certificate(problem, problem.all_mask, witness) if witness else {}
        record["certificate_valid"] = bool(
            witness and witness.separator_mask == 0
            and not verify_safe(problem, problem.all_mask)
            and verify_unsafe(problem, certificate)
        )
    return record, problem, analysis, certificate


def _problem_table_signature(problem: PortfolioProblem) -> tuple[Any, ...]:
    """Full extensional monitor representation used for mutation deduplication."""
    return tuple((update.initial, update.history, update.future, update.output)
                 for update in problem.updates)


def _mutants(problem: PortfolioProblem):
    seen: set[tuple[Any, ...]] = set()
    for update_index, update in enumerate(problem.updates):
        n = len(update.history)
        # Exactly one cyclic redirection per transition cell.  For the fixed
        # two-state campaign subspace this flips the destination; no alternate
        # destinations are enumerated.
        for part_name in ("history", "future"):
            table = getattr(update, part_name)
            for state, row in enumerate(table):
                for symbol, old in enumerate(row):
                    if n <= 1:
                        continue
                    new_destination = (old + 1) % n
                    rows = [list(r) for r in table]
                    rows[state][symbol] = new_destination
                    mutant_update = replace(update, **{
                        part_name: tuple(tuple(r) for r in rows)})
                    updates = list(problem.updates)
                    updates[update_index] = mutant_update
                    mutant = replace(problem, updates=tuple(updates))
                    key = _problem_table_signature(mutant)
                    if key in seen:
                        continue
                    seen.add(key)
                    yield f"u{update_index}-{part_name}-{state}-{symbol}", mutant
        for state in range(n):
            output = list(update.output)
            output[state] = 1 - output[state]
            mutant_update = replace(update, output=tuple(output))
            updates = list(problem.updates)
            updates[update_index] = mutant_update
            mutant = replace(problem, updates=tuple(updates))
            key = _problem_table_signature(mutant)
            if key in seen:
                continue
            seen.add(key)
            yield f"u{update_index}-output-{state}", mutant


def _run_examples(output: Path, replace_existing: bool) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    certificates: dict[str, Any] = {}
    mutation_rows: list[dict[str, Any]] = []
    for path in sorted((ROOT / "declarations").glob("*.json")):
        record, problem, analysis, certificate = _example_record(path)
        records.append(record); certificates[problem.name] = certificate
        if not record["feasible"]:
            continue
        old_mask = int(record["optimal_mask"])
        old_cost = int(record["optimal_cost"])
        for mutant_id, mutant in _mutants(problem):
            mutant_analysis = build_conflict_analysis(mutant)
            old_safe = verify_safe(mutant, old_mask)
            result = optimize_portfolio(mutant, mutant_analysis)
            cert_valid = True
            old_failure_valid = True
            if not old_safe:
                witness = shortest_failure(old_mask, mutant_analysis)
                old_failure_valid = bool(witness and verify_unsafe(
                    mutant, make_unsafe_certificate(mutant, old_mask, witness)))
                cert_valid = cert_valid and old_failure_valid
            infeasibility_valid = True
            if result["feasible"]:
                opt_cert = make_optimal_certificate(
                    mutant, mutant_analysis, int(result["selected_mask"]))
                cert_valid = cert_valid and verify_optimal(mutant, opt_cert)
            else:
                # Failure of the old optimum is not evidence that the whole
                # catalogue is infeasible.  Independently test all candidates
                # and replay a zero-separator certificate.
                all_mask_witness = shortest_failure(mutant.all_mask, mutant_analysis)
                infeasibility_valid = bool(
                    not verify_safe(mutant, mutant.all_mask)
                    and all_mask_witness is not None
                    and all_mask_witness.separator_mask == 0
                    and verify_unsafe(
                        mutant,
                        make_unsafe_certificate(mutant, mutant.all_mask,
                                                all_mask_witness),
                    )
                )
                cert_valid = cert_valid and infeasibility_valid
            mutation_rows.append({
                "base": problem.name, "mutation": mutant_id,
                "old_mask": old_mask, "old_cost": old_cost,
                "old_portfolio_safe": old_safe,
                "old_failure_certificate_valid": old_failure_valid,
                "mutated_catalogue_feasible": result["feasible"],
                "catalogue_infeasibility_verified": infeasibility_valid,
                "mutated_optimal_mask": result["selected_mask"],
                "mutated_optimal_cost": result["cost"],
                "cost_delta": None if result["cost"] is None else int(result["cost"]) - old_cost,
                "certificate_valid": cert_valid,
            })
    _write_json(output / "example-results.json", records, replace_existing)
    _write_json(output / "example-certificates.json", certificates, replace_existing)
    csv_path = output / "mutation-results.csv"
    if csv_path.exists() and not replace_existing:
        raise FileExistsError(f"refusing to overwrite {csv_path}")
    with csv_path.with_suffix(".csv.tmp").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(mutation_rows[0]))
        writer.writeheader(); writer.writerows(mutation_rows)
    os.replace(csv_path.with_suffix(".csv.tmp"), csv_path)
    return {
        "declarations": len(records),
        "feasible_declarations": sum(int(r["feasible"]) for r in records),
        "infeasible_declarations": sum(not r["feasible"] for r in records),
        "all_example_certificates_valid": all(r["certificate_valid"] for r in records),
        "greedy_suboptimal_cases": sum(r["feasible"] and r["greedy_cost"] > r["optimal_cost"] for r in records),
        "separate_union_suboptimal_cases": sum(r["feasible"] and r["per_update_union_cost"] > r["optimal_cost"] for r in records),
        "mutations": len(mutation_rows),
        "old_portfolio_became_unsafe": sum(not row["old_portfolio_safe"] for row in mutation_rows),
        "mutated_catalogue_infeasible": sum(not row["mutated_catalogue_feasible"] for row in mutation_rows),
        "mutation_certificate_failures": sum(not row["certificate_valid"] for row in mutation_rows),
        "mutation_infeasibility_verification_failures": sum(
            (not row["mutated_catalogue_feasible"]) and
            (not row["catalogue_infeasibility_verified"])
            for row in mutation_rows),
        "mutations_increasing_optimal_cost": sum(row["cost_delta"] is not None and row["cost_delta"] > 0 for row in mutation_rows),
        "mutations_decreasing_optimal_cost": sum(row["cost_delta"] is not None and row["cost_delta"] < 0 for row in mutation_rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "portfolio")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    started_wall = time.perf_counter(); started_cpu = time.process_time()
    examples = _run_examples(args.output, args.replace)
    unary = _run_catalogue("unary-complete", unary_catalogue(),
                           args.output / "unary-catalogue.csv", True, args.replace)
    binary = _run_catalogue("binary-complete-subspace", binary_catalogue(),
                            args.output / "binary-catalogue.csv", False, args.replace)
    summary = {
        "scope": "bounded finite exact validation; not production prevalence or throughput",
        "examples": examples,
        "catalogues": [unary, binary],
        "totals": {
            "cases": unary["cases"] + binary["cases"],
            "portfolio_masks_checked": (unary["safe_portfolio_masks"] + unary["unsafe_portfolio_masks"] +
                                         binary["safe_portfolio_masks"] + binary["unsafe_portfolio_masks"]),
            "safety_equivalence_mismatches": unary["safety_equivalence_mismatches"] + binary["safety_equivalence_mismatches"],
            "optimizer_mismatches": unary["optimizer_mismatches"] + binary["optimizer_mismatches"],
            "certificate_failures": unary["certificate_failures"] + binary["certificate_failures"] + examples["mutation_certificate_failures"] + (0 if examples["all_example_certificates_valid"] else 1),
            "minimum_witness_mismatches": unary["minimum_witness_mismatches"],
            "wall_seconds": time.perf_counter() - started_wall,
            "cpu_seconds": time.process_time() - started_cpu,
            "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        },
    }
    _write_json(args.output / "summary.json", summary, args.replace)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if all(summary["totals"][key] == 0 for key in (
        "safety_equivalence_mismatches", "optimizer_mismatches",
        "certificate_failures", "minimum_witness_mismatches")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
