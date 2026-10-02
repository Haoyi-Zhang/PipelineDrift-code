#!/usr/bin/env python3
"""Validate complete deterministic coverage and summarize scientific outcomes."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path


def summarize(root: Path) -> dict:
    paths = sorted(root.glob('cases-*.csv'))
    seen: set[int] = set()
    total = Counter()
    strata: dict[tuple[int, int, int], Counter] = defaultdict(Counter)
    costs = Counter()
    measurements = []
    for path in paths:
        marker = path.with_suffix('.json')
        if not marker.exists():
            raise ValueError(f'incomplete chunk: {path.name}')
        metric = json.loads(marker.read_text())
        if metric['disagreements'] or metric['timed_out']:
            raise ValueError(f'failed chunk: {path.name}')
        chunk_count = chunk_unsafe = 0
        lo, hi = metric['selection']
        chunk_ids = []
        with path.open(newline='') as source:
            for row in csv.DictReader(source):
                idx = int(row['case'])
                if idx in seen:
                    raise ValueError(f'duplicate case {idx}')
                seen.add(idx)
                chunk_ids.append(idx)
                a, o = int(row['admissible']), int(row['oracle_admissible'])
                if a != o or row['minimum_cost'] != row['oracle_minimum_cost'] or row['certificate_valid'] != '1':
                    raise ValueError(f'checker disagreement in case {idx}')
                if a not in (0, 1) or bool(int(row['oracle_migration_maps'])) != bool(a):
                    raise ValueError(f'inconsistent map count in case {idx}')
                key = tuple(int(row[k]) for k in ('alphabet', 'retained_states', 'target_states'))
                result = Counter(cases=1, admissible=a, inadmissible=1-a,
                                 type_only_false_accept=1-a,
                                 current_only_false_accept=int(row['current_only'])*(1-a),
                                 current_only_false_reject=(1-int(row['current_only']))*a,
                                 state_equality_false_accept=int(row['state_equality'])*(1-a),
                                 state_equality_false_reject=(1-int(row['state_equality']))*a)
                total.update(result)
                strata[key].update(result)
                if not a:
                    costs[int(row['minimum_cost'])] += 1
                chunk_count += 1
                chunk_unsafe += 1-a
        if chunk_ids != list(range(lo, hi)) or chunk_count != metric['cases'] or chunk_unsafe != metric['inadmissible']:
            raise ValueError(f'coverage/metric mismatch: {path.name}')
        measurements.append(metric)
    if seen != set(range(46932)):
        raise ValueError(f'expected exactly cases 0..46931, found {len(seen)}')
    return {'scope': 'complete predeclared finite table space, not a workload sample',
            'totals': dict(total),
            'strata': [dict(alphabet=k[0], retained_states=k[1], target_states=k[2], **v)
                       for k, v in sorted(strata.items())],
            'minimum_cost_distribution': {str(k): v for k,v in sorted(costs.items())},
            'measurements': {'chunks': len(measurements),
                             'summed_inner_cpu_seconds': sum(x['cpu_seconds'] for x in measurements),
                             'summed_inner_elapsed_seconds': sum(x['elapsed_seconds'] for x in measurements),
                             'max_process_peak_rss_kib': max(x['peak_rss_kib'] for x in measurements),
                             'timed_out_chunks': sum(x['timed_out'] for x in measurements)},
            'oracle_disagreements': 0, 'invalid_certificates': 0}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('root', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = summarize(args.root)
    if args.output.exists():
        p.error('refusing to overwrite existing summary')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
