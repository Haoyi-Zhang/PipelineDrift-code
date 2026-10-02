#!/usr/bin/env python3
"""One-worker, bounded, resumable exhaustive diagnostic chunks.

Run from the repository root. The tool does not install or download anything.
"""
from __future__ import annotations
import argparse, csv, json, os, resource, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from drift_contracts import Contract, analyze, verify
from drift_contracts.cases import parameters, from_parameters, named_examples
from drift_contracts.oracle import oracle

COLUMNS = ["case", "alphabet", "retained_states", "target_states", "retained_table", "history_table",
           "future_table", "output_code", "admissible", "oracle_admissible", "minimum_cost",
           "oracle_minimum_cost", "oracle_migration_maps", "reachable_pairs", "current_only",
           "state_equality", "certificate_valid"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--stop", type=int, default=6000)
    parser.add_argument("--pilot", action="store_true", help="64 evenly spaced fixed cases plus eight scenarios")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 0 <= args.start < args.stop <= 46932:
        parser.error("require 0 <= start < stop <= 46932")
    if not args.pilot and args.stop - args.start > 6000:
        parser.error("a diagnostic chunk may contain at most 6000 cases")
    resource.setrlimit(resource.RLIMIT_AS, (3*1024**3, 3*1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (35, 35))
    if hasattr(os, "sched_getaffinity"):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    args.output.mkdir(parents=True, exist_ok=True)
    label = "pilot" if args.pilot else f"cases-{args.start:05d}-{args.stop:05d}"
    csv_path = args.output / f"{label}.csv"
    metrics_path = args.output / f"{label}.json"
    if csv_path.exists() or metrics_path.exists():
        raise SystemExit("refusing to overwrite existing diagnostic evidence")
    selected = {i * (46932-1) // 63 for i in range(64)} if args.pilot else None
    start_time, start_cpu = time.perf_counter(), time.process_time()
    count = disagreements = unsafe = 0
    with csv_path.open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        for row in parameters():
            idx = row[0]
            if selected is not None:
                if idx not in selected:
                    continue
            elif idx < args.start:
                continue
            elif idx >= args.stop:
                break
            c = from_parameters(row)
            answer, ground = analyze(c), oracle(c)
            minimum = None if answer["admissible"] else answer["certificate"]["cost"]
            valid = verify(c, answer["certificate"])
            mismatch = answer["admissible"] != ground["admissible"] or minimum != ground["minimum_cost"] or not valid
            disagreements += mismatch
            if mismatch:
                (args.output / f"failure-case-{idx}.json").write_text(json.dumps({
                    "contract": c.to_dict(), "answer": answer, "oracle": ground}, indent=2))
            writer.writerow(dict(zip(COLUMNS, list(row) + [int(answer["admissible"]), int(ground["admissible"]),
                         "" if minimum is None else minimum,
                         "" if ground["minimum_cost"] is None else ground["minimum_cost"],
                         ground["migration_maps"], answer["reachable_pairs"],
                         int(answer["current_only_admissible"]), int(answer["state_equality_admissible"]), int(valid)])))
            count += 1
            unsafe += not answer["admissible"]
    scenarios = []
    if args.pilot:
        for example in named_examples():
            c = Contract.from_dict(example["contract"])
            answer = analyze(c)
            valid = verify(c, answer["certificate"])
            ok = valid and answer["admissible"] == example["expected_admissible"]
            disagreements += not ok
            scenarios.append({"case": example["case"], "expected": example["expected_admissible"],
                              "answer": answer, "certificate_valid": valid, "matches_expected": ok})
        (args.output / "scenarios.json").write_text(json.dumps(scenarios, indent=2)+"\n")
    measurement = dict(label=label, cases=count, inadmissible=unsafe, disagreements=disagreements,
                       scenario_cases=len(scenarios), elapsed_seconds=time.perf_counter()-start_time,
                       cpu_seconds=time.process_time()-start_cpu,
                       peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                       workers=1, address_space_limit_bytes=3*1024**3, cpu_limit_seconds=35,
                       timed_out=False, selection="fixed 64-case pilot" if args.pilot else [args.start, args.stop])
    metrics_path.write_text(json.dumps(measurement, indent=2)+"\n")
    print(json.dumps(measurement))
    return 1 if disagreements else 0


if __name__ == "__main__":
    raise SystemExit(main())
