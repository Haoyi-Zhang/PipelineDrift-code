"""Finite optional regression, also run explicitly by scientific CI.

No historical producer copy, private paths, timing or output writes. Literal
word enumeration is independent of graph BFS/reverse distances. Table fixtures
use a test-local recursively typed JSON relation, not compiler helpers.
"""
from __future__ import annotations

import copy
from dataclasses import asdict
import itertools
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from drift_contracts import portfolio as producer
from drift_contracts import portfolio_dsl as compiler
from drift_contracts.dsl_reference import check_compilation
from drift_contracts.portfolio_cases import unary_catalogue
from drift_contracts.portfolio_model import MonitorUpdate, PortfolioProblem, RetentionAtom
from drift_contracts.portfolio_verify import verify_optimal, verify_safe, verify_unsafe


def words(alphabet, bound):
    for length in range(bound):
        yield from itertools.product(range(alphabet), repeat=length)


def run(table, initial, word):
    state = initial
    for symbol in word:
        state = table[state][symbol]
    return state


def literal_analysis(problem):
    best, updates, counts = {}, [], []
    conflicts = 0
    for index, update in enumerate(problem.updates):
        bound = len(update.history)
        for atom in problem.atoms:
            bound *= len(atom.transition)
        # Simple-path bound is complete, including empty/nonzero initial states.
        endpoints = {}
        for word in words(len(problem.history_symbols), bound):
            state = tuple(run(atom.transition, atom.initial, word) for atom in problem.atoms)
            state += (run(update.history, update.initial, word),)
            if state not in endpoints:
                endpoints[state] = word
        states = sorted(endpoints)
        counts.append(len(states))
        masks = set()
        for left_index, left in enumerate(states):
            for right in states[left_index + 1:]:
                p, q = left[-1], right[-1]
                h1, h2 = endpoints[left], endpoints[right]
                if (len(h2), h2, right) < (len(h1), h1, left):
                    h1, h2, p, q = h2, h1, q, p
                suffix = next((word for word in words(len(problem.future_symbols), len(update.future)**2)
                               if update.output[run(update.future, p, word)] !=
                               update.output[run(update.future, q, word)]), None)
                if suffix is None:
                    continue
                conflicts += 1
                mask = sum(1 << i for i in range(len(problem.atoms)) if left[i] != right[i])
                masks.add(mask)
                witness = producer.Witness(index, h1, h2, suffix, mask, p, q)
                if mask not in best or witness.key() < best[mask].key():
                    best[mask] = witness
        updates.append(minimal(masks))
    basis = minimal(set(best))
    return producer.ConflictAnalysis(basis, {mask: best[mask] for mask in basis},
                                     best, tuple(updates), tuple(counts), conflicts)


def minimal(masks):
    return tuple(sorted((mask for mask in masks
                         if not any(other != mask and (other & mask) == other for other in masks)),
                        key=lambda mask: (mask.bit_count(), mask)))


def tie_problems():
    for initial in (0, 1):
        # Two input spellings converge; both orientation and equal-cost suffix
        # choices matter. Empty and nonempty separators coexist.
        yield PortfolioProblem(
            f"ties-{initial}", ("h0", "h1"), ("f0", "f1"),
            (RetentionAtom("remember", 1, ((0, 1), (1, 0)), initial),),
            (MonitorUpdate("u0", ((1, 1), (2, 0), (2, 2)),
                           ((1, 1), (2, 2), (2, 2)), (0, 0, 1)),
             MonitorUpdate("u1", ((1, 1), (2, 0), (2, 2)),
                           ((2, 1), (2, 2), (2, 2)), (0, 0, 1))),
        )


def same_json(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(same_json(a, b) for a, b in zip(left, right))
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(same_json(left[k], right[k]) for k in left)
    return left == right


def prepared_document():
    domain = [False, 0, True, 1, {"a": False}, [["a", False]]]
    hp = {"op": "eq", "args": [{"field": "x"}, {"const": domain[5]}]}
    fp = {"op": "eq", "args": [{"field": "y"}, {"const": domain[4]}]}
    return {
        "name": "prepared-nested", "history_schema": {"fields": {"x": domain}},
        "future_schema": {"fields": {"y": list(reversed(copy.deepcopy(domain)))}},
        "retention_atoms": [
            {"name": "hist", "kind": "histogram", "initial": 3, "cap": 1,
             "cost": 3, "value": {"field": "x"}, "values": copy.deepcopy(domain)},
            {"name": "window", "kind": "window", "initial": 2, "width": 2,
             "cost": 2, "predicate": hp}],
        "monitor_updates": [{"name": "pattern", "kind": "window_pattern", "initial": 4,
                             "pattern": [True, False], "history_predicate": hp, "future_predicate": fp}],
    }


def rejection_records():
    base = prepared_document()
    docs = []
    doc = copy.deepcopy(base); doc["retention_atoms"][1]["predicate"] = 0; docs.append(doc)
    doc = copy.deepcopy(base); doc["monitor_updates"][0]["history_predicate"] = 0; docs.append(doc)
    doc = copy.deepcopy(base); doc["monitor_updates"][0]["future_predicate"] = 0; docs.append(doc)
    doc = copy.deepcopy(base); doc["retention_atoms"][0]["values"] = [False]; docs.append(doc)
    for initial in (-1, True, 64):
        doc = copy.deepcopy(base); doc["retention_atoms"][0]["initial"] = initial; docs.append(doc)
    doc = copy.deepcopy(base); doc["retention_atoms"][0]["cap"] = 0; docs.append(doc)
    doc = copy.deepcopy(base); doc["retention_atoms"][0]["cap"] = 15; docs.append(doc)
    doc = copy.deepcopy(base); doc["retention_atoms"][1]["width"] = 11; docs.append(doc)
    # Preserve the first Boolean error before a later record's relational error.
    doc = copy.deepcopy(base)
    doc["history_schema"]["fields"]["x"] = [0, "later-type-error"]
    doc["retention_atoms"] = [{"name": "a", "kind": "seen", "initial": 0, "predicate": False}]
    doc["monitor_updates"][0]["history_predicate"] = {
        "op": "tuple", "args": [{"op": "lt", "args": [{"field": "x"}, 1]}]}
    docs.append(doc)
    result = []
    for index, document in enumerate(docs):
        try:
            compiler.compile_declaration(document)
        except (ValueError, TypeError) as error:
            result.append([index, type(error).__name__, str(error)])
        else:
            raise AssertionError(f"invalid declaration accepted: {index}")
    problem = compiler.compile_declaration(base)
    for field, value, operation in (
        ("MAX_PRODUCT_STATES", 1, lambda: producer.build_conflict_analysis(problem)),
        ("MAX_STATE_PAIRS", 1, lambda: producer.build_conflict_analysis(problem)),
        ("MAX_PAIR_TRANSITION_CELLS", 1, lambda: producer.build_conflict_analysis(problem)),
        ("MAX_TRANSITION_CELLS", 1, lambda: compiler.compile_declaration(base)),
    ):
        producer._future_distances.cache_clear()
        with patch("drift_contracts.limits." + field, value):
            try:
                operation()
            except ValueError as error:
                result.append([field, type(error).__name__, str(error)])
            else:
                raise AssertionError(f"cap not enforced: {field}")
    producer._future_distances.cache_clear()
    return result


def record(problem):
    analysis = producer.build_conflict_analysis(problem)
    optimum = producer.optimize_portfolio(problem, analysis)
    selected = [producer.analyze_selected(problem, analysis, mask) for mask in range(problem.all_mask + 1)]
    checks = []
    for entry in selected:
        mask = entry["selected_mask"]
        if entry["safe"] != verify_safe(problem, mask):
            raise AssertionError("safety mismatch")
        checks.append(True if entry["safe"] else verify_unsafe(problem, entry["certificate"]))
    certificate = None
    if optimum["feasible"]:
        certificate = producer.make_optimal_certificate(problem, analysis, optimum["selected_mask"])
        if not verify_optimal(problem, certificate):
            raise AssertionError("optimal certificate rejected")
    if not all(checks):
        raise AssertionError("unsafe certificate rejected")
    return {"problem": asdict(problem), "analysis": asdict(analysis), "optimum": optimum,
            "selected": selected, "certificate": certificate,
            "greedy": producer.greedy_portfolio(problem, analysis),
            "union": producer.independent_union_baseline(problem, analysis), "checks": checks}


def snapshot():
    return {
        "unary": [record(problem) for _, problem, _ in unary_catalogue()],
        "ties": [record(problem) for problem in tie_problems()],
        "named": [record(compiler.load_declaration(path)) for path in sorted((ROOT / "declarations").glob("*.json"))],
        "prepared": asdict(compiler.compile_declaration(prepared_document())),
        "rejections": rejection_records(),
    }


class ShortcutRegression(unittest.TestCase):
    def test_literal_complete_unary_and_ties(self):
        count = 0
        for _, problem, _ in unary_catalogue():
            self.assertEqual(producer.build_conflict_analysis(problem), literal_analysis(problem))
            count += 1
        self.assertEqual(count, 4096)
        for problem in tie_problems():
            analysis = producer.build_conflict_analysis(problem)
            self.assertEqual(analysis, literal_analysis(problem))
            self.assertIn(0, analysis.all_witnesses)
            self.assertIn(1, analysis.all_witnesses)

    def test_prepared_tables_against_literal_typed_reference(self):
        doc = prepared_document()
        actual = compiler.compile_declaration(doc)
        domain = doc["history_schema"]["fields"]["x"]
        bins = tuple(itertools.product(range(2), repeat=len(domain)))
        expected_hist = []
        for state in bins:
            row = []
            for value in domain:
                index = next(i for i, member in enumerate(domain) if same_json(member, value))
                target = list(state); target[index] = 1
                row.append(bins.index(tuple(target)))
            expected_hist.append(tuple(row))
        windows = tuple(words(2, 3))
        def table(values, target):
            return tuple(tuple(windows.index((state + (int(same_json(value, target)),))[-2:])
                               for value in values) for state in windows)
        self.assertEqual(actual.atoms[0].transition, tuple(expected_hist))
        self.assertEqual(actual.atoms[1].transition, table(domain, domain[5]))
        self.assertEqual(actual.updates[0].history, table(domain, domain[5]))
        self.assertEqual(actual.updates[0].future, table(list(reversed(domain)), domain[4]))
        self.assertEqual(actual.updates[0].output, tuple(int(state == (1, 0)) for state in windows))
        self.assertEqual([atom.initial for atom in actual.atoms], [3, 2])
        self.assertEqual(actual.updates[0].initial, 4)
        check_compilation(doc, actual)
        with (ROOT / "results" / "portfolio" / "example-certificates.json").open(encoding="utf-8") as source:
            retained = json.load(source)
        for path in sorted((ROOT / "declarations").glob("*.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            problem = compiler.compile_declaration(document)
            check_compilation(document, problem)
            current = record(problem)
            certificate = current["certificate"] or current["selected"][-1]["certificate"]
            self.assertEqual(certificate, retained[problem.name])

    def test_negative_order_caps_and_certificate_bindings(self):
        records = rejection_records()
        self.assertEqual(len(records), 15)
        self.assertEqual(records[10][1:], ["ValueError", "update pattern predicate must be Boolean"])
        problem = compiler.load_declaration(ROOT / "declarations" / "threshold-family.json")
        analysis = producer.build_conflict_analysis(problem)
        certificate = producer.make_unsafe_certificate(problem, 0, producer.shortest_failure(0, analysis))
        self.assertTrue(verify_unsafe(problem, certificate))
        for field, value in (("cost", certificate["cost"] + 1), ("selected_mask", True),
                             ("separator_mask", certificate["separator_mask"] ^ 1)):
            altered = dict(certificate); altered[field] = value
            self.assertFalse(verify_unsafe(problem, altered))


if __name__ == "__main__":
    unittest.main()
