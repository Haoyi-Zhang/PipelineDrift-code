"""Exact JSON container semantics, independent of the historical declarations."""
from __future__ import annotations

import copy
from dataclasses import replace
import json
import unittest

from drift_contracts.dsl_reference import check_compilation
from drift_contracts.portfolio_dsl import compile_declaration


def declaration(domain, expression):
    return {
        "name": "container-values",
        "history_schema": {"fields": {"x": domain}},
        "future_schema": {"fields": {"x": copy.deepcopy(domain)}},
        "retention_atoms": [{"name": "match", "kind": "seen", "initial": 0,
                             "cost": 1, "predicate": expression}],
        "monitor_updates": [{"name": "match", "kind": "seen", "initial": 0,
                             "predicate": expression}],
    }


class ContainerValueTests(unittest.TestCase):
    def test_object_and_pair_array_are_distinct_for_eq_ne_and_in(self):
        domain = [{"a": False}, [["a", False]]]
        for op, constant, expected in (
            ("eq", {"a": False}, (1, 0)),
            ("ne", {"a": False}, (0, 1)),
            ("in", [{"a": False}], (1, 0)),
        ):
            with self.subTest(op=op):
                doc = declaration(domain, {"op": op, "args": [
                    {"field": "x"}, {"const": constant}]})
                problem = compile_declaration(doc)
                self.assertEqual(expected, problem.atoms[0].transition[0])
                self.assertEqual(expected, problem.updates[0].history[0])
                check_compilation(doc, problem)

    def test_record_symbols_preserve_json_container_types(self):
        domain = [{"a": False}, [["a", False]]]
        doc = declaration(domain, {"const": False})
        problem = compile_declaration(doc)
        for raw, symbol in zip(domain, problem.history_symbols):
            encoded = json.loads(symbol.split("x=", 1)[1])
            self.assertIs(type(raw), type(encoded))
            self.assertEqual(raw, encoded)
        check_compilation(doc, problem)

    def test_object_key_order_is_irrelevant_and_nested_types_are_exact(self):
        domain = [{"a": [False], "b": {"x": 0}},
                  {"a": [0], "b": {"x": 0}},
                  {"a": [False], "b": [["x", 0]]}]
        doc = declaration(domain, {"op": "eq", "args": [
            {"field": "x"}, {"const": {"b": {"x": 0}, "a": [False]}}]})
        problem = compile_declaration(doc)
        self.assertEqual((1, 0, 0), problem.atoms[0].transition[0])
        check_compilation(doc, problem)
        duplicate = declaration([{"a": 0, "b": 1}, {"b": 1, "a": 0}], True)
        with self.assertRaises(ValueError):
            compile_declaration(duplicate)

    def test_value_primitives_keep_object_and_array_domain_entries(self):
        domain = [{"a": False}, [["a", False]], {"a": 0}]
        doc = declaration(domain, True)
        doc["retention_atoms"] = [
            {"name": kind, "kind": kind, "initial": 0, "cost": 1,
             "values": domain, "value": {"field": "x"},
             **({"cap": 1} if kind == "histogram" else {})}
            for kind in ("last", "bitset", "histogram")]
        doc["monitor_updates"] = [
            {"name": "last", "kind": "last_equals", "initial": 0,
             "values": domain, "value": {"field": "x"}, "target": domain[0]},
            *[{"name": kind, "kind": kind, "initial": 0,
               "values": domain, "value": {"field": "x"},
               "required": [domain[0], copy.deepcopy(domain[0])]}
              for kind in ("bitset_any", "bitset_all")],
        ]
        problem = compile_declaration(doc)
        self.assertEqual((1, 2, 3), problem.atoms[0].transition[0])
        self.assertEqual((1, 2, 4), problem.atoms[1].transition[0])
        check_compilation(doc, problem)

    def test_reference_rejects_container_and_nested_scalar_record_mutations(self):
        doc = declaration([{"a": False}], {"const": False})
        problem = compile_declaration(doc)
        for bad_value in ([["a", False]], {"a": 0}):
            for side in ("history_records", "future_records"):
                with self.subTest(value=bad_value, side=side):
                    metadata = dict(problem.metadata)
                    metadata[side] = ({"x": bad_value},)
                    with self.assertRaises(AssertionError):
                        check_compilation(doc, replace(problem, metadata=metadata))

    def test_reference_detects_old_object_array_equality_transition(self):
        doc = declaration([{"a": False}], {"op": "eq", "args": [
            {"field": "x"}, {"const": [["a", False]]}]})
        problem = compile_declaration(doc)
        self.assertEqual((0,), problem.atoms[0].transition[0])
        bad_atom = replace(problem.atoms[0], transition=((1,), (1,)))
        with self.assertRaises(AssertionError):
            check_compilation(doc, replace(problem, atoms=(bad_atom,)))


if __name__ == "__main__":
    unittest.main()
