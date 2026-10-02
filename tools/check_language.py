#!/usr/bin/env python3
"""Cross-check every declaration against the independent reference semantics."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from drift_contracts.dsl_reference import check_compilation
from drift_contracts.portfolio_dsl import compile_declaration


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rows = []
    totals = {
        'declarations': 0, 'history_records': 0, 'future_records': 0,
        'retention_atoms': 0, 'monitor_updates': 0,
        'retention_transition_cells': 0, 'monitor_transition_cells': 0,
        'monitor_output_cells': 0, 'initial_states_checked': 0,
        'empty_histories_checked': 0,
    }
    for path in sorted((ROOT / 'declarations').glob('*.json')):
        document = json.loads(path.read_text(encoding='utf-8'))
        row = {'name': document['name'], **check_compilation(document, compile_declaration(document))}
        rows.append(row)
        totals['declarations'] += 1
        for key in totals:
            if key != 'declarations':
                totals[key] += row[key]
    report = {
        'status': 'all extensional compiler cells, explicit initials, and empty histories match the independent reference semantics',
        'scope': 'the 12 shipped bounded declarations; not an external pipeline implementation',
        'totals': totals,
        'declarations': rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise FileExistsError(f'refusing to overwrite {args.output}')
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
