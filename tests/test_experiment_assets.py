from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class ExperimentAssetTests(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, *args], cwd=ROOT, text=True,
            capture_output=True, check=False,
            env={**__import__('os').environ, 'PYTHONDONTWRITEBYTECODE': '1'},
            timeout=60,
        )

    def test_pinned_tfx_source_digest_and_projection(self):
        source_dir = ROOT / 'external' / 'tfx-penguin'
        source = json.loads((source_dir / 'SOURCE.json').read_text(encoding='utf-8'))
        digest = hashlib.sha256((source_dir / 'schema.pbtxt').read_bytes()).hexdigest()
        self.assertEqual(source['local_sha256'], digest)
        self.assertEqual('cd99075bfad794a3ea9df49ee77f9c06578f895d', source['commit'])
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'projection'
            result = self._run('tools/tfx_projection.py', '--output', str(output))
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            report = json.loads((output / 'result.json').read_text(encoding='utf-8'))
            self.assertEqual(5, report['features_projected'])
            self.assertEqual(31, report['selected_mask'])
            self.assertTrue(report['certificate_valid'])
            self.assertTrue(report['independently_safe'])

    def test_random_differential_inputs_and_results_are_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / 'first'
            second = Path(tmp) / 'second'
            for output in (first, second):
                result = self._run(
                    'tools/random_differential.py', '--output', str(output),
                    '--seed', '17', '--problems', '8')
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            for name in ('problems.jsonl', 'cases.csv', 'summary.json'):
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())
            summary = json.loads((first / 'summary.json').read_text(encoding='utf-8'))
            self.assertEqual(8, summary['problems'])
            self.assertEqual(0, summary['safety_mismatches'])
            self.assertEqual(0, summary['optimizer_mismatches'])
            self.assertEqual(0, summary['certificate_failures'])

    def test_cost_sensitivity_has_real_inputs_and_verified_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'cost'
            result = self._run('tools/cost_sensitivity.py', '--output', str(output))
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            summary = json.loads((output / 'summary.json').read_text(encoding='utf-8'))
            inputs = json.loads((output / 'inputs.json').read_text(encoding='utf-8'))
            self.assertEqual(11, summary['feasible_declarations'])
            self.assertEqual(1, summary['infeasible_declarations_skipped'])
            self.assertGreater(summary['perturbations'], 0)
            self.assertEqual(0, summary['certificate_failures'])
            self.assertEqual(11, len(inputs))

    def test_all_experiment_tools_refuse_preexisting_output(self):
        commands = (
            ('tools/random_differential.py', '--problems', '1'),
            ('tools/cost_sensitivity.py',),
            ('tools/tfx_projection.py',),
            ('tools/release_check.py',),
        )
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / 'existing'
            existing.mkdir()
            for command in commands:
                with self.subTest(command=command[0]):
                    result = self._run(*command, '--output', str(existing))
                    self.assertNotEqual(0, result.returncode)

    def test_release_checker_is_present_and_reproduction_invokes_missing_asset_checks(self):
        release = (ROOT / 'tools' / 'release_check.py').read_text(encoding='utf-8')
        reproduce = (ROOT / 'tools' / 'reproduce.py').read_text(encoding='utf-8')
        self.assertIn('tools/reproduce.py', release)
        self.assertIn('tools/random_differential.py', reproduce)
        self.assertIn('tools/cost_sensitivity.py', reproduce)
        self.assertIn('tools/tfx_projection.py', reproduce)
        spec = importlib.util.spec_from_file_location(
            'release_check_under_test', ROOT / 'tools' / 'release_check.py')
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(module.platform, 'python_implementation', return_value='PyPy'), \
                self.assertRaises(RuntimeError):
            module.run(Path(tmp) / 'release')


if __name__ == '__main__':
    unittest.main()
