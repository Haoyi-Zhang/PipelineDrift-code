from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from drift_contracts.portfolio import (analyze_selected, build_conflict_analysis,
    greedy_portfolio, independent_union_baseline, is_safe, make_optimal_certificate,
    make_unsafe_certificate, optimize_portfolio, shortest_failure)
from drift_contracts.portfolio_cases import binary_catalogue, unary_catalogue
from drift_contracts.portfolio_dsl import compile_declaration, load_declaration
from drift_contracts.dsl_reference import check_compilation
from drift_contracts.portfolio_verify import verify_optimal, verify_safe, verify_unsafe


class PortfolioTests(unittest.TestCase):
    def load(self, name):
        return load_declaration(ROOT / "declarations" / f"{name}.json")

    def test_all_declarations_match_independent_language_semantics(self):
        paths = sorted((ROOT / "declarations").glob("*.json"))
        checked = 0
        for path in paths:
            document = json.loads(path.read_text(encoding="utf-8"))
            report = check_compilation(document, compile_declaration(document))
            checked += report["retention_transition_cells"] + report["monitor_transition_cells"] + report["monitor_output_cells"]
        self.assertGreater(checked, 0)

    def test_all_declarations_compile_and_analysis_matches_checker(self):
        paths = sorted((ROOT / "declarations").glob("*.json"))
        self.assertEqual(12, len(paths))
        for path in paths:
            problem = load_declaration(path)
            analysis = build_conflict_analysis(problem)
            for mask in range(1 << len(problem.atoms)):
                self.assertEqual(is_safe(mask, analysis), verify_safe(problem, mask), path.name)

    def test_threshold_family_global_sharing(self):
        problem = self.load("threshold-family")
        analysis = build_conflict_analysis(problem)
        result = optimize_portfolio(problem, analysis)
        self.assertEqual(["error-count-3"], problem.selected_names(result["selected_mask"]))
        self.assertEqual(2, result["cost"])
        separate = independent_union_baseline(problem, analysis)
        self.assertEqual(5, problem.cost(separate))

    def test_class_coverage_tie_prefers_one_atom(self):
        problem = self.load("class-coverage")
        analysis = build_conflict_analysis(problem)
        result = optimize_portfolio(problem, analysis)
        self.assertEqual(1, result["selected_mask"])
        self.assertEqual(3, result["cost"])
        self.assertEqual(3, problem.cost(greedy_portfolio(problem, analysis)))
        self.assertGreater(greedy_portfolio(problem, analysis).bit_count(), 1)


    def test_weighted_greedy_counterexample(self):
        problem = self.load("weighted-greedy-trap")
        analysis = build_conflict_analysis(problem)
        exact = optimize_portfolio(problem, analysis)
        greedy = greedy_portfolio(problem, analysis)
        self.assertEqual(10, exact["cost"])
        self.assertEqual(11, problem.cost(greedy))
        self.assertTrue(verify_safe(problem, exact["selected_mask"]))

    def test_infeasible_catalogue_has_replayable_zero_separator(self):
        problem = self.load("marginals-only-infeasible")
        analysis = build_conflict_analysis(problem)
        self.assertIn(0, analysis.obligations)
        self.assertFalse(optimize_portfolio(problem, analysis)["feasible"])
        witness = shortest_failure(problem.all_mask, analysis)
        self.assertIsNotNone(witness)
        certificate = make_unsafe_certificate(problem, problem.all_mask, witness)
        self.assertEqual(0, certificate["separator_mask"])
        self.assertTrue(verify_unsafe(problem, certificate))

    def test_optimal_certificate_rejects_cheaper_unsafe_claim(self):
        problem = self.load("threshold-family")
        analysis = build_conflict_analysis(problem)
        cert = make_optimal_certificate(problem, analysis, 4)
        cert["selected_mask"] = 1
        cert["selected_atoms"] = ["ever-error"]
        cert["cost"] = 1
        self.assertFalse(verify_optimal(problem, cert))

    def test_unsafe_certificate_rejects_tampering(self):
        problem = self.load("threshold-family")
        analysis = build_conflict_analysis(problem)
        witness = shortest_failure(0, analysis)
        cert = make_unsafe_certificate(problem, 0, witness)
        self.assertTrue(verify_unsafe(problem, cert))
        bad = dict(cert); bad["cost"] += 1
        self.assertFalse(verify_unsafe(problem, bad))
        bad = dict(cert); bad["history_left"] = ["unknown"]
        self.assertFalse(verify_unsafe(problem, bad))

    def test_optimal_certificate_carries_replayable_migration_maps(self):
        problem = self.load("threshold-family")
        analysis = build_conflict_analysis(problem)
        result = optimize_portfolio(problem, analysis)
        cert = make_optimal_certificate(problem, analysis, int(result["selected_mask"]))
        self.assertEqual(list(analysis.obligations), cert["obstruction_basis"])
        self.assertEqual([u.name for u in problem.updates],
                         [entry["update"] for entry in cert["representatives"]])
        self.assertTrue(all(entry["fibers"] for entry in cert["representatives"]))
        self.assertTrue(verify_optimal(problem, cert))

    def test_optimal_certificate_rejects_basis_tampering(self):
        problem = self.load("threshold-family")
        analysis = build_conflict_analysis(problem)
        cert = make_optimal_certificate(problem, analysis, 4)
        bad = copy.deepcopy(cert)
        bad["obstruction_basis"] = []
        self.assertFalse(verify_optimal(problem, bad))
        bad = copy.deepcopy(cert)
        bad["obstruction_basis"].append(1)
        self.assertFalse(verify_optimal(problem, bad))

    def test_optimal_certificate_rejects_migration_map_tampering(self):
        problem = self.load("threshold-family")
        analysis = build_conflict_analysis(problem)
        cert = make_optimal_certificate(problem, analysis, 4)
        corruptions = []
        bad = copy.deepcopy(cert); bad["representatives"][0]["fibers"].pop(); corruptions.append(bad)
        bad = copy.deepcopy(cert); bad["representatives"][0]["update"] = "unknown"; corruptions.append(bad)
        bad = copy.deepcopy(cert); bad["representatives"][0]["fibers"][0]["target_state"] = 1; corruptions.append(bad)
        bad = copy.deepcopy(cert); bad["representatives"][0]["fibers"][0]["summary_state"] = [99]; corruptions.append(bad)
        bad = copy.deepcopy(cert); bad["representatives"].append(copy.deepcopy(bad["representatives"][0])); corruptions.append(bad)
        for bad in corruptions:
            with self.subTest(certificate=bad):
                self.assertFalse(verify_optimal(problem, bad))

    def test_unsafe_certificate_binds_selected_mask(self):
        problem = self.load("threshold-family")
        analysis = build_conflict_analysis(problem)
        cert = make_unsafe_certificate(problem, 0, shortest_failure(0, analysis))
        self.assertTrue(verify_unsafe(problem, cert))
        bad = copy.deepcopy(cert); bad["selected_mask"] = problem.all_mask
        self.assertFalse(verify_unsafe(problem, bad))
        bad = copy.deepcopy(cert); bad["selected_mask"] = True
        self.assertFalse(verify_unsafe(problem, bad))
        bad = copy.deepcopy(cert); bad["selected_mask"] = 1 << len(problem.atoms)
        self.assertFalse(verify_unsafe(problem, bad))

    def test_certificate_schema_rejects_extra_fields(self):
        problem = self.load("threshold-family")
        analysis = build_conflict_analysis(problem)
        positive = make_optimal_certificate(problem, analysis, 4)
        positive["producer_trace"] = []
        self.assertFalse(verify_optimal(problem, positive))
        negative = make_unsafe_certificate(problem, 0, shortest_failure(0, analysis))
        negative["producer_trace"] = []
        self.assertFalse(verify_unsafe(problem, negative))

    def test_unsafe_certificate_rejects_boolean_state_aliases(self):
        problem = self.load("threshold-family")
        analysis = build_conflict_analysis(problem)
        cert = make_unsafe_certificate(problem, 0, shortest_failure(0, analysis))
        self.assertTrue(verify_unsafe(problem, cert))
        for field in ("target_left", "target_right"):
            bad = copy.deepcopy(cert)
            bad[field] = bool(bad[field])
            self.assertFalse(verify_unsafe(problem, bad), field)

    def test_optimal_certificate_rejects_boolean_obstruction_aliases(self):
        problem = self.load("field-deletion")
        analysis = build_conflict_analysis(problem)
        result = optimize_portfolio(problem, analysis)
        cert = make_optimal_certificate(problem, analysis, int(result["selected_mask"]))
        self.assertIn(1, cert["obstruction_basis"])
        bad = copy.deepcopy(cert)
        bad["obstruction_basis"] = [True if value == 1 else value
                                    for value in bad["obstruction_basis"]]
        self.assertFalse(verify_optimal(problem, bad))

    def test_window_and_histogram_compilation(self):
        doc = {
            "name": "language-smoke",
            "history_schema": {"fields": {"b": [False, True], "x": ["a", "b"]}},
            "future_schema": {"fields": {"b": [False, True], "x": ["a", "b"]}},
            "retention_atoms": [
                {"name": "window", "kind": "window", "initial": 0, "width": 2,
                 "predicate": {"field": "b"}},
                {"name": "hist", "kind": "histogram", "initial": 0, "cap": 1,
                 "value": {"field": "x"}, "values": ["a", "b"]}],
            "monitor_updates": [{"name": "pattern", "kind": "window_pattern", "initial": 0,
                                  "pattern": [True, False],
                                  "predicate": {"field": "b"}}]}
        problem = compile_declaration(doc)
        self.assertEqual(4, len(problem.history_symbols))
        self.assertEqual(7, len(problem.atoms[0].transition))
        self.assertEqual(4, len(problem.atoms[1].transition))
        self.assertEqual(7, len(problem.updates[0].history))

    def test_compiled_trace_matches_hand_calculation(self):
        problem = self.load("threshold-family")
        # Symbols are error=false then error=true.
        word = (1, 0, 1, 1)
        expected = {"ever-error": 1, "error-count-2": 2,
                    "error-count-3": 3, "last-error": 2}
        for atom in problem.atoms:
            state = atom.initial
            for symbol in word:
                state = atom.transition[state][symbol]
            self.assertEqual(expected[atom.name], state)
        for update, threshold in zip(problem.updates, (1, 2, 3)):
            state = update.initial
            for symbol in word:
                state = update.history[state][symbol]
            self.assertEqual(threshold, state)
            self.assertEqual(1, update.output[state])

    def test_unary_catalogue_prefix_matches_independent_checker(self):
        for index, (_, problem, _) in enumerate(unary_catalogue()):
            if index == 96:
                break
            analysis = build_conflict_analysis(problem)
            result = optimize_portfolio(problem, analysis)
            for mask in range(1 << len(problem.atoms)):
                self.assertEqual(is_safe(mask, analysis), verify_safe(problem, mask))
            if result["feasible"]:
                cert = make_optimal_certificate(
                    problem, analysis, int(result["selected_mask"]))
                self.assertTrue(verify_optimal(problem, cert))

    def test_binary_catalogue_count_and_prefix(self):
        count = 0
        for _, problem, _ in binary_catalogue():
            if count < 64:
                analysis = build_conflict_analysis(problem)
                for mask in range(4):
                    self.assertEqual(is_safe(mask, analysis), verify_safe(problem, mask))
            count += 1
        self.assertEqual(16384, count)

    def test_analyze_selected_emits_only_unsafe_certificate(self):
        problem = self.load("threshold-family")
        analysis = build_conflict_analysis(problem)
        unsafe = analyze_selected(problem, analysis, 0)
        self.assertFalse(unsafe["safe"])
        self.assertTrue(verify_unsafe(problem, unsafe["certificate"]))
        safe = analyze_selected(problem, analysis, 4)
        self.assertTrue(safe["safe"])
        self.assertNotIn("certificate", safe)

    def test_declaration_rejects_unbounded_or_unknown_constructs(self):
        base = json.loads((ROOT / "declarations" / "threshold-family.json").read_text())
        base["retention_atoms"][0]["kind"] = "unbounded-count"
        with self.assertRaises(ValueError):
            compile_declaration(base)
        base = json.loads((ROOT / "declarations" / "threshold-family.json").read_text())
        base["history_schema"]["fields"]["huge"] = list(range(4097))
        with self.assertRaises(ValueError):
            compile_declaration(base)


if __name__ == "__main__":
    unittest.main()
