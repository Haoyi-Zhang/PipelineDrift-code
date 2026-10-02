from __future__ import annotations

import contextlib
import copy
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

from drift_contracts.dsl_reference import check_compilation
from drift_contracts.limits import AnalysisLimitError
from drift_contracts.portfolio import (_future_distances, build_conflict_analysis,
                                      optimize_portfolio)
from drift_contracts.portfolio_cli import main as portfolio_cli_main
from drift_contracts.portfolio_dsl import compile_declaration, load_declaration
from drift_contracts.portfolio_verify import verify_safe


def minimal_document() -> dict:
    return {
        "name": "minimal",
        "history_schema": {"fields": {"x": [False, 0, True, 1]}},
        "future_schema": {"fields": {"x": [False, 0, True, 1]}},
        "retention_atoms": [
            {"name": "zero", "kind": "seen", "initial": 0,
             "predicate": {"op": "in", "args": [{"field": "x"}, {"const": [0]}]}},
            {"name": "one", "kind": "seen", "initial": 0,
             "predicate": {"op": "in", "args": [{"field": "x"}, {"const": [1]}]}},
        ],
        "monitor_updates": [
            {"name": "u", "kind": "seen", "initial": 0,
             "predicate": {"op": "eq", "args": [{"field": "x"}, {"const": 0}]}}
        ],
    }


class RequestedRepairTests(unittest.TestCase):
    def test_required_duplicates_are_idempotent_set_membership(self):
        doc = {
            "name": "duplicate-required",
            "history_schema": {"fields": {"x": ["a", "b"]}},
            "future_schema": {"fields": {"x": ["a", "b"]}},
            "retention_atoms": [
                {"name": "last", "kind": "last", "initial": 0,
                 "value": {"field": "x"}, "values": ["a", "b"]}
            ],
            "monitor_updates": [
                {"name": "all-a", "kind": "bitset_all", "initial": 0,
                 "value": {"field": "x"}, "values": ["a", "b"],
                 "required": ["a", "a"]}
            ],
        }
        problem = compile_declaration(doc)
        output = problem.updates[0].output
        self.assertEqual(1, output[1], "seeing only a must satisfy required={a}")
        self.assertEqual(0, output[2], "seeing only b must not satisfy required={a}")
        check_compilation(doc, problem)

    def test_membership_uses_typed_equality_like_eq_and_ne(self):
        doc = minimal_document()
        problem = compile_declaration(doc)
        # Record order is False, 0, True, 1. From initial state, a true predicate
        # moves a seen atom to state 1.
        self.assertEqual((0, 1, 0, 0), problem.atoms[0].transition[0])
        self.assertEqual((0, 0, 0, 1), problem.atoms[1].transition[0])
        check_compilation(doc, problem)

    def test_reference_semantics_detects_old_python_membership_mutation(self):
        doc = minimal_document()
        problem = compile_declaration(doc)
        old_python_row = (1, 1, 0, 0)  # False aliases 0 under Python membership.
        bad_atom = replace(problem.atoms[0], transition=(old_python_row, problem.atoms[0].transition[1]))
        bad_problem = replace(problem, atoms=(bad_atom, problem.atoms[1]))
        with self.assertRaises(AssertionError):
            check_compilation(doc, bad_problem)

    def test_declaration_layers_reject_unknown_fields_and_require_initial(self):
        base = minimal_document()
        variants = []
        v = copy.deepcopy(base); v["retention_atoms"][0]["predciate"] = True; variants.append(v)
        v = copy.deepcopy(base); v["monitor_updates"][0]["threshhold"] = 1; variants.append(v)
        v = copy.deepcopy(base); v["history_schema"]["unknown"] = 1; variants.append(v)
        v = copy.deepcopy(base); v["unknown"] = 1; variants.append(v)
        v = copy.deepcopy(base); del v["retention_atoms"][0]["initial"]; variants.append(v)
        v = copy.deepcopy(base); del v["monitor_updates"][0]["initial"]; variants.append(v)
        v = copy.deepcopy(base); v["retention_atoms"][0]["initial"] = -1; variants.append(v)
        v = copy.deepcopy(base); v["monitor_updates"][0]["initial"] = -1; variants.append(v)
        for index, document in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(ValueError):
                compile_declaration(document)

    def test_reference_checks_atom_and_target_initial_and_empty_history(self):
        doc = minimal_document()
        problem = compile_declaration(doc)
        bad_atom = replace(problem.atoms[0], initial=1)
        with self.assertRaises(AssertionError):
            check_compilation(doc, replace(problem, atoms=(bad_atom, problem.atoms[1])))
        bad_update = replace(problem.updates[0], initial=1)
        with self.assertRaises(AssertionError):
            check_compilation(doc, replace(problem, updates=(bad_update,)))


    def test_all_atom_primitive_budgets_are_checked_before_table_allocation(self):
        atom_specs = [
            {"name": "a", "kind": "seen", "initial": 0, "predicate": {"const": True}},
            {"name": "a", "kind": "count", "initial": 0, "cap": 1, "predicate": {"const": True}},
            {"name": "a", "kind": "run", "initial": 0, "cap": 1, "predicate": {"const": True}},
            {"name": "a", "kind": "last", "initial": 0, "value": {"field": "x"}, "values": ["v"]},
            {"name": "a", "kind": "bitset", "initial": 0, "value": {"field": "x"}, "values": ["v"]},
            {"name": "a", "kind": "histogram", "initial": 0, "cap": 1, "value": {"field": "x"}, "values": ["v"]},
            {"name": "a", "kind": "window", "initial": 0, "width": 1, "predicate": {"const": True}},
        ]
        for spec in atom_specs:
            doc = {
                "name": "budget", "history_schema": {"fields": {"x": ["v"]}},
                "future_schema": {"fields": {"x": ["v"]}},
                "retention_atoms": [spec],
                "monitor_updates": [{"name": "u", "kind": "seen", "initial": 0,
                                     "predicate": {"const": False}}],
            }
            with self.subTest(kind=spec["kind"]), \
                    patch("drift_contracts.limits.MAX_TRANSITION_CELLS", 1), \
                    self.assertRaises(AnalysisLimitError):
                compile_declaration(doc)

    def test_all_monitor_primitive_budgets_are_checked_before_table_allocation(self):
        update_specs = [
            {"name": "u", "kind": "seen", "initial": 0, "predicate": {"const": True}},
            {"name": "u", "kind": "count_threshold", "initial": 0, "threshold": 1, "predicate": {"const": True}},
            {"name": "u", "kind": "run_threshold", "initial": 0, "threshold": 1, "predicate": {"const": True}},
            {"name": "u", "kind": "last_equals", "initial": 0, "value": {"field": "x"}, "values": ["v"], "target": "v"},
            {"name": "u", "kind": "bitset_any", "initial": 0, "value": {"field": "x"}, "values": ["v"], "required": ["v"]},
            {"name": "u", "kind": "bitset_all", "initial": 0, "value": {"field": "x"}, "values": ["v"], "required": ["v"]},
            {"name": "u", "kind": "window_pattern", "initial": 0, "predicate": {"const": True}, "pattern": [True]},
        ]
        for spec in update_specs:
            doc = {
                "name": "budget", "history_schema": {"fields": {"x": ["v"]}},
                "future_schema": {"fields": {"x": ["v"]}},
                "retention_atoms": [{"name": "a", "kind": "seen", "initial": 0,
                                     "predicate": {"const": False}}],
                "monitor_updates": [spec],
            }
            # Atom table has two cells and passes; every monitor has at least
            # four cells across history and future and must refuse before build.
            with self.subTest(kind=spec["kind"]), \
                    patch("drift_contracts.limits.MAX_TRANSITION_CELLS", 2), \
                    self.assertRaises(AnalysisLimitError):
                compile_declaration(doc)

    def test_large_state_formulas_refuse_without_expansion(self):
        doc = minimal_document()
        doc["history_schema"] = {"fields": {"x": [0]}}
        doc["future_schema"] = {"fields": {"x": [0]}}
        doc["retention_atoms"] = [{"name": "count", "kind": "count", "initial": 0,
                                   "cap": 4096, "predicate": {"const": True}}]
        with self.assertRaises(AnalysisLimitError):
            compile_declaration(doc)
        doc["retention_atoms"] = [{"name": "hist", "kind": "histogram", "initial": 0,
                                   "cap": 15, "value": {"field": "x"},
                                   "values": [0, 1, 2, 3]}]
        with self.assertRaises(AnalysisLimitError):
            compile_declaration(doc)
        doc["retention_atoms"] = [{"name": "small", "kind": "seen", "initial": 0,
                                   "predicate": {"const": False}}]
        doc["monitor_updates"] = [{"name": "u", "kind": "count_threshold", "initial": 0,
                                   "threshold": 4096, "predicate": {"const": True}}]
        with self.assertRaises(AnalysisLimitError):
            compile_declaration(doc)

    def test_product_pair_and_subset_budgets_are_analysis_refusals(self):
        problem = load_declaration(ROOT / "declarations" / "threshold-family.json")
        with patch("drift_contracts.limits.MAX_PRODUCT_STATES", 100), \
                self.assertRaises(AnalysisLimitError):
            build_conflict_analysis(problem)
        with patch("drift_contracts.limits.MAX_PRODUCT_STATES", 100), \
                self.assertRaises(AnalysisLimitError):
            verify_safe(problem, problem.all_mask)
        with patch("drift_contracts.limits.MAX_STATE_PAIRS", 1), \
                self.assertRaises(AnalysisLimitError):
            build_conflict_analysis(problem)
        _future_distances.cache_clear()
        with patch("drift_contracts.limits.MAX_PAIR_TRANSITION_CELLS", 1), \
                self.assertRaises(AnalysisLimitError):
            build_conflict_analysis(problem)
        _future_distances.cache_clear()
        analysis = build_conflict_analysis(problem)
        with patch("drift_contracts.limits.MAX_PORTFOLIO_SUBSETS", 8), \
                self.assertRaises(AnalysisLimitError):
            optimize_portfolio(problem, analysis)

    def test_empty_separator_has_the_mathematical_minimal_basis_only(self):
        problem = load_declaration(ROOT / "declarations" / "marginals-only-infeasible.json")
        analysis = build_conflict_analysis(problem)
        self.assertEqual((0,), analysis.obligations)

    def test_joint_control_changes_only_the_candidate_catalogue(self):
        marginals = load_declaration(ROOT / "declarations" / "marginals-only-infeasible.json")
        joint = load_declaration(ROOT / "declarations" / "joint-marginals.json")
        self.assertEqual(marginals.history_symbols, joint.history_symbols)
        self.assertEqual(marginals.future_symbols, joint.future_symbols)
        self.assertEqual(marginals.updates, joint.updates)
        self.assertEqual(marginals.atoms, joint.atoms[: len(marginals.atoms)])

    def _invoke_portfolio_cli(self, declaration: Path, selected: int | None = None):
        argv = [str(declaration)]
        if selected is not None:
            argv += ["--selected", str(selected)]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = portfolio_cli_main(argv)
        return code, json.loads(out.getvalue())

    def test_cli_returns_nonzero_when_main_certificate_verification_fails(self):
        path = ROOT / "declarations" / "threshold-family.json"
        with patch("drift_contracts.portfolio_cli.verify_optimal", return_value=False):
            code, payload = self._invoke_portfolio_cli(path)
        self.assertNotEqual(0, code)
        self.assertFalse(payload["certificate_valid"])

    def test_cli_returns_nonzero_when_selected_certificate_verification_fails(self):
        path = ROOT / "declarations" / "threshold-family.json"
        with patch("drift_contracts.portfolio_cli.verify_unsafe", return_value=False):
            code, payload = self._invoke_portfolio_cli(path, selected=0)
        self.assertNotEqual(0, code)
        self.assertFalse(payload["selected"]["certificate_valid"])

    def test_valid_scientific_negative_diagnosis_is_success(self):
        path = ROOT / "declarations" / "marginals-only-infeasible.json"
        code, payload = self._invoke_portfolio_cli(path)
        self.assertEqual(0, code)
        self.assertFalse(payload["feasible"])
        self.assertTrue(payload["certificate_valid"])


if __name__ == "__main__":
    unittest.main()
