#!/usr/bin/env python3
"""Run the complete standalone artifact check in a fresh output directory.

The checked environment is Linux with CPython 3.10 or newer.  The artifact has
no third-party Python dependency and performs no network access.  Other
platforms are untested rather than claimed unsupported by theorem.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def _meminfo_bytes(key: str) -> int | None:
    try:
        for line in Path('/proc/meminfo').read_text(encoding='utf-8').splitlines():
            if line.startswith(key + ':'):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _os_release() -> str | None:
    try:
        fields = {}
        for line in Path('/etc/os-release').read_text(encoding='utf-8').splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                fields[key] = value.strip().strip('"')
        return fields.get('PRETTY_NAME')
    except OSError:
        return None


def run(output: Path) -> dict:
    if output.exists():
        raise FileExistsError(f"output must not already exist: {output}")
    if sys.version_info < (3, 10):
        raise RuntimeError("this checked artifact requires CPython 3.10 or newer")
    if platform.system() != 'Linux':
        raise RuntimeError("the release checker is validated only on Linux")
    if platform.python_implementation() != 'CPython':
        raise RuntimeError("the release checker is validated only with CPython")
    free_disk = shutil.disk_usage(output.parent.resolve()).free
    available_memory = _meminfo_bytes('MemAvailable')
    swap_total = _meminfo_bytes('SwapTotal')
    # These are preflight requirements for the shipped bounded campaign, not
    # claims about all possible declarations accepted by the library.
    if free_disk < 250 * 1024**2:
        raise RuntimeError("less than 250 MiB free disk is available")
    if available_memory is not None and available_memory < 512 * 1024**2:
        raise RuntimeError("less than 512 MiB available memory is reported")
    output.mkdir(parents=True)
    started = time.perf_counter()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    reproduction = output / 'reproduction'
    process = subprocess.run(
        [sys.executable, 'tools/reproduce.py', '--output', str(reproduction)],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False,
        timeout=45 * 60,
    )
    (output / 'reproduce.txt').write_text(
        process.stdout + process.stderr, encoding='utf-8')
    if process.returncode:
        raise RuntimeError(
            f"reproduction returned {process.returncode}; inspect reproduce.txt")
    report = json.loads((reproduction / 'reproduction.json').read_text(encoding='utf-8'))
    environment = {
        'supported_and_checked_platform': 'Linux',
        'platform_observed': platform.platform(),
        'os_release_observed': _os_release(),
        'python_implementation': platform.python_implementation(),
        'python_version': platform.python_version(),
        'python_executable': sys.executable,
        'cpu_count_observed': os.cpu_count(),
        'available_memory_bytes_before_run': available_memory,
        'swap_total_bytes_observed': swap_total,
        'free_disk_bytes_before_run': free_disk,
        'workers': 1,
        'network_required': False,
        'third_party_python_packages_required': False,
        'untested_environment_note': 'macOS, Windows, PyPy, and other Python versions were not checked by this release run',
    }
    final = {
        'status': 'pass',
        'meaning': 'all shipped bounded commands succeeded and deterministic scientific records matched; not external review or a general proof',
        'environment': environment,
        'reproduction': report,
        'elapsed_seconds': time.perf_counter() - started,
    }
    (output / 'release-check.json').write_text(
        json.dumps(final, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return final


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        final = run(args.output)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"release check failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(final, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
