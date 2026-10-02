#!/usr/bin/env python3
"""Clean one-worker rerun and deterministic-record comparison.

Use a new output directory. No files in the shipped repository are overwritten.
Timing and peak-RSS observations are recorded but deliberately not required to
match the shipped run.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import resource
import re
import subprocess
import sys
import time
from summarize import summarize


def _portfolio_science(summary: dict) -> dict:
    """Drop run-local measurements while retaining every scientific count."""
    clean = json.loads(json.dumps(summary))
    for item in clean.get("catalogues", []):
        for key in ("cpu_seconds", "wall_seconds", "max_rss_kib"):
            item.pop(key, None)
    for key in ("cpu_seconds", "wall_seconds", "max_rss_kib"):
        clean.get("totals", {}).pop(key, None)
    return clean


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    out = args.output.resolve()
    root = Path(__file__).resolve().parents[1]
    if out.exists():
        p.error('output must not already exist')
    resource.setrlimit(resource.RLIMIT_AS, (3*1024**3, 3*1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    if hasattr(os, 'sched_getaffinity'):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    out.mkdir(parents=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    start_time, start_cpu = time.perf_counter(), time.process_time()
    initial_children = resource.getrusage(resource.RUSAGE_CHILDREN)
    commands = []

    def run(arguments: list[str], label: str, timeout: int = 60) -> str:
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        t0 = time.perf_counter()
        try:
            r = subprocess.run([sys.executable, *arguments], cwd=root, env=env,
                               capture_output=True, text=True, timeout=timeout,
                               check=False)
            status, stdout, stderr = r.returncode, r.stdout, r.stderr
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f'{label} exceeded the {timeout}-second wall limit') from exc
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        (out/f'{label}.txt').write_text(stdout+stderr, encoding='utf-8')
        commands.append({'step': label, 'returncode': status,
                         'child_cpu_seconds': after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                         'wall_seconds': time.perf_counter()-t0})
        if status:
            raise RuntimeError(f'{label} failed with exit {status}; inspect its output')
        return stdout + stderr

    test_output = run(['-m', 'unittest', 'discover', '-s', 'tests', '-v'], 'tests')
    test_match = re.search(r'Ran (\d+) tests?', test_output)
    if not test_match:
        raise RuntimeError('could not parse unit-test count')
    unit_tests = int(test_match.group(1))
    run(['tools/check_language.py', '--output', str(out/'language-check.json')],
        'language-check')
    run(['tools/campaign.py', '--pilot', '--output', str(out/'pilot')], 'pilot')
    for lo in range(0, 46932, 6000):
        hi = min(lo+6000, 46932)
        run(['tools/campaign.py', '--start', str(lo), '--stop', str(hi),
             '--output', str(out/'exhaustive')], f'cases-{lo:05d}-{hi:05d}')
    run(['tools/counter_family.py', '--output', str(out/'counter-family')],
        'counter-family')
    run(['tools/portfolio_campaign.py', '--output', str(out/'portfolio')],
        'portfolio-campaign')
    run(['tools/random_differential.py', '--output', str(out/'random-differential'),
         '--seed', '20260915', '--problems', '256'], 'random-differential')
    run(['tools/cost_sensitivity.py', '--output', str(out/'cost-sensitivity')],
        'cost-sensitivity')
    run(['tools/tfx_projection.py', '--output', str(out/'tfx-projection')],
        'tfx-projection')

    summary = summarize(out/'exhaustive')
    (out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    expected = json.loads((root/'results/summary.json').read_text(encoding='utf-8'))
    for key in ('totals', 'strata', 'minimum_cost_distribution',
                'oracle_disagreements', 'invalid_certificates'):
        if summary[key] != expected[key]:
            raise RuntimeError(f'legacy scientific summary differs: {key}')

    comparisons: list[str] = []
    if (root/'results/language-check.json').read_bytes() != (out/'language-check.json').read_bytes():
        raise RuntimeError('language semantic report differs')
    comparisons.append('language-check.json')
    for path in sorted((root/'results/exhaustive').glob('cases-*.csv')):
        replica = out/'exhaustive'/path.name
        if path.read_bytes() != replica.read_bytes():
            raise RuntimeError(f'legacy scientific CSV differs: {path.name}')
        comparisons.append(f'exhaustive/{path.name}')
    for name in ('pilot.csv', 'scenarios.json'):
        if (root/'results/pilot'/name).read_bytes() != (out/'pilot'/name).read_bytes():
            raise RuntimeError(f'pilot evidence differs: {name}')
        comparisons.append(f'pilot/{name}')
    for name in ('counter-family.csv', 'counter-certificates.json'):
        if (root/'results/counter-family'/name).read_bytes() != (out/'counter-family'/name).read_bytes():
            raise RuntimeError(f'counter evidence differs: {name}')
        comparisons.append(f'counter-family/{name}')

    expected_portfolio = json.loads((root/'results/portfolio/summary.json').read_text(encoding='utf-8'))
    actual_portfolio = json.loads((out/'portfolio/summary.json').read_text(encoding='utf-8'))
    if _portfolio_science(actual_portfolio) != _portfolio_science(expected_portfolio):
        raise RuntimeError('portfolio scientific summary differs')
    for name in ('unary-catalogue.csv', 'binary-catalogue.csv',
                 'mutation-results.csv', 'example-results.json',
                 'example-certificates.json'):
        if (root/'results/portfolio'/name).read_bytes() != (out/'portfolio'/name).read_bytes():
            raise RuntimeError(f'portfolio evidence differs: {name}')
        comparisons.append(f'portfolio/{name}')

    deterministic_groups = {
        'random-differential': ('problems.jsonl', 'cases.csv', 'summary.json'),
        'cost-sensitivity': ('inputs.json', 'variations.csv', 'summary.json'),
        'tfx-projection': ('projected-declaration.json', 'projection-map.json',
                           'certificate.json', 'result.json'),
    }
    for group, names in deterministic_groups.items():
        for name in names:
            expected_path = root/'results'/group/name
            actual_path = out/group/name
            if expected_path.read_bytes() != actual_path.read_bytes():
                raise RuntimeError(f'{group} evidence differs: {name}')
            comparisons.append(f'{group}/{name}')

    language_report = json.loads((out/'language-check.json').read_text(encoding='utf-8'))
    random_report = json.loads((out/'random-differential/summary.json').read_text(encoding='utf-8'))
    cost_report = json.loads((out/'cost-sensitivity/summary.json').read_text(encoding='utf-8'))
    tfx_report = json.loads((out/'tfx-projection/result.json').read_text(encoding='utf-8'))
    language_cells = (language_report['totals']['retention_transition_cells'] +
                      language_report['totals']['monitor_transition_cells'] +
                      language_report['totals']['monitor_output_cells'] +
                      language_report['totals']['initial_states_checked'] +
                      language_report['totals']['empty_histories_checked'])

    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    report = {
        'status': 'commands succeeded and deterministic scientific records matched',
        'legacy_case_count': summary['totals']['cases'],
        'portfolio_case_count': actual_portfolio['totals']['cases'],
        'portfolio_masks_checked': actual_portfolio['totals']['portfolio_masks_checked'],
        'declarations': actual_portfolio['examples']['declarations'],
        'mutations': actual_portfolio['examples']['mutations'],
        'unit_tests': unit_tests,
        'language_cells_checked': language_cells,
        'random_problems': random_report['problems'],
        'random_portfolio_masks_checked': random_report['portfolio_masks_checked'],
        'cost_perturbations': cost_report['perturbations'],
        'tfx_features_projected': tfx_report['features_projected'],
        'scientific_record_comparisons': comparisons,
        'commands': commands,
        'workers': 1,
        'elapsed_seconds': time.perf_counter()-start_time,
        'parent_cpu_seconds': time.process_time()-start_cpu,
        'children_cpu_seconds': after.ru_utime+after.ru_stime-initial_children.ru_utime-initial_children.ru_stime,
        'parent_peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'children_peak_rss_kib': after.ru_maxrss,
        'timings_are_not_expected_to_match': True,
        'meaning': 'reproduction of bounded finite checks, not independent proof, production validation, or external review'
    }
    (out/'reproduction.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError) as exc:
        print(f'reproduction failed: {exc}', file=sys.stderr)
        raise SystemExit(1)
