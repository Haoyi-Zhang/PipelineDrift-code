#!/usr/bin/env python3
"""Check the predeclared 48-case counter grid against its closed-form theorem."""
from __future__ import annotations
import argparse
import csv
import json
import os
from pathlib import Path
import resource
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from drift_contracts import Contract, analyze, verify


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        p.error('output must be a new directory')
    resource.setrlimit(resource.RLIMIT_AS, (3*1024**3, 3*1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (35, 35))
    if hasattr(os, 'sched_getaffinity'):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    args.output.mkdir(parents=True)
    t0, c0 = time.perf_counter(), time.process_time()
    rows, certificates = [], []
    def streak(cap):
        return tuple((0, min(s+1, cap)) for s in range(cap+1))
    for k in range(1, 7):
        for t in range(1, 9):
            c = Contract(streak(k), streak(t), streak(t), tuple(int(s == t) for s in range(t+1)))
            answer = analyze(c)
            cost = None if answer['admissible'] else answer['certificate']['cost']
            expected = t <= k
            expected_cost = None if expected else k+t
            ok = answer['admissible'] == expected and cost == expected_cost and verify(c, answer['certificate'])
            if not ok:
                raise RuntimeError(f'counter theorem mismatch at k={k}, t={t}')
            rows.append({'retained_cap': k, 'target_cap': t, 'admissible': int(answer['admissible']),
                         'expected_admissible': int(expected), 'minimum_cost': cost,
                         'expected_minimum_cost': expected_cost, 'certificate_valid': 1})
            certificates.append({'retained_cap': k, 'target_cap': t, 'certificate': answer['certificate']})
    with (args.output/'counter-family.csv').open('w', newline='') as out:
        w = csv.DictWriter(out, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (args.output/'counter-certificates.json').write_text(json.dumps(certificates, indent=2)+'\n')
    report = {'cases': len(rows), 'admissible': sum(r['admissible'] for r in rows),
              'inadmissible': sum(not r['admissible'] for r in rows), 'disagreements': 0,
              'cpu_seconds': time.process_time()-c0, 'elapsed_seconds': time.perf_counter()-t0,
              'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              'workers': 1, 'timed_out': False}
    (args.output/'counter-family.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
