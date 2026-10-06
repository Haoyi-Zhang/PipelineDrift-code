"""Independent reference semantics for the bounded declaration language.

This module deliberately does not import the compiler's expression evaluator,
state enumerators, transition builders, or typed-key helper.  It reconstructs
all extensional cells from the JSON declaration and additionally checks each
explicit initial state and the empty-history endpoint.
"""
from __future__ import annotations

from itertools import product
import math
from typing import Any

from .portfolio_model import PortfolioProblem, run_table


def _freeze(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(x) for x in value)
    if isinstance(value, dict):
        if not all(type(k) is str for k in value):
            raise ValueError("object keys must be JSON strings")
        return {k: _freeze(v) for k, v in sorted(value.items())}
    if value is None or type(value) in (bool, int, str):
        return value
    raise ValueError(f"unsupported value {value!r}")


def _same_value(left: Any, right: Any) -> bool:
    """Independent exact-type equality used by eq/ne/in.

    This intentionally avoids the compiler's typed-key representation and
    Python container membership, so False/0 and True/1 cannot alias.
    """
    left = _freeze(left)
    right = _freeze(right)
    if type(left) is not type(right):
        return False
    if isinstance(left, tuple):
        return len(left) == len(right) and all(
            _same_value(a, b) for a, b in zip(left, right))
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _same_value(left[k], right[k]) for k in left)
    return left == right


def _index(values: tuple[Any, ...], value: Any) -> int:
    for i, candidate in enumerate(values):
        if _same_value(candidate, value):
            return i
    raise ValueError(f"value {value!r} outside declared domain")


def _eval(expr: Any, record: dict[str, Any]) -> Any:
    if expr is None or type(expr) in (bool, int, str) or isinstance(expr, list):
        return _freeze(expr)
    if not isinstance(expr, dict):
        raise ValueError("expression must be JSON-compatible")
    if set(expr) == {"field"}:
        field = expr["field"]
        if field not in record:
            raise ValueError(f"unknown field {field!r}")
        return record[field]
    if set(expr) == {"const"}:
        return _freeze(expr["const"])
    if set(expr) != {"op", "args"}:
        raise ValueError("operator expression must contain exactly op and args")
    op = expr["op"]
    values = [_eval(arg, record) for arg in expr["args"]]
    if op == "not":
        if len(values) != 1 or type(values[0]) is not bool:
            raise ValueError("not expects one Boolean")
        return not values[0]
    if op in {"and", "or"}:
        if not values or any(type(x) is not bool for x in values):
            raise ValueError(f"{op} expects Booleans")
        return all(values) if op == "and" else any(values)
    if op == "tuple":
        return tuple(values)
    if op == "in":
        if len(values) != 2 or not isinstance(values[1], tuple):
            raise ValueError("in expects a value and tuple")
        return any(_same_value(values[0], candidate) for candidate in values[1])
    if len(values) != 2:
        raise ValueError(f"{op} expects two arguments")
    left, right = values
    if op == "eq":
        return _same_value(left, right)
    if op == "ne":
        return not _same_value(left, right)
    if op == "lt":
        return left < right
    if op == "le":
        return left <= right
    if op == "gt":
        return left > right
    if op == "ge":
        return left >= right
    raise ValueError(f"unsupported operator {op!r}")


def _records(schema: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    fields = tuple(schema["fields"])
    domains = [tuple(_freeze(v) for v in schema["fields"][field]) for field in fields]
    return tuple(dict(zip(fields, values)) for values in product(*domains))


def _window_states(width: int) -> tuple[tuple[bool, ...], ...]:
    result: list[tuple[bool, ...]] = [()]
    for length in range(1, width + 1):
        result.extend(tuple(bits) for bits in product((False, True), repeat=length))
    return tuple(result)


def _table(states: tuple[Any, ...], records: tuple[dict[str, Any], ...], step) -> tuple[tuple[int, ...], ...]:
    def state_index(value: Any) -> int:
        for i, state in enumerate(states):
            if _same_value(state, value):
                return i
        raise ValueError(f"state {value!r} outside reference state space")

    return tuple(tuple(state_index(step(state, record)) for record in records)
                 for state in states)


def _initial(spec: dict[str, Any], states: tuple[Any, ...]) -> int:
    value = spec["initial"]
    if type(value) is not int or not 0 <= value < len(states):
        raise ValueError("invalid explicit initial index")
    return value


def _atom(spec: dict[str, Any], records: tuple[dict[str, Any], ...]):
    kind = spec["kind"]
    if kind in {"seen", "count", "run"}:
        cap = 1 if kind == "seen" else spec["cap"]
        states = tuple(range(cap + 1))
        truth = tuple(_eval(spec["predicate"], r) for r in records)
        if any(type(value) is not bool for value in truth):
            raise ValueError("predicate must be Boolean")
        if kind in {"seen", "count"}:
            table = tuple(tuple(min(cap, s + int(truth[x])) for x in range(len(records))) for s in states)
        else:
            table = tuple(tuple(min(cap, s + 1) if truth[x] else 0 for x in range(len(records))) for s in states)
    elif kind == "last":
        values = tuple(_freeze(v) for v in spec["values"])
        states = tuple(range(len(values) + 1))
        observed = tuple(_eval(spec["value"], r) for r in records)
        table = tuple(tuple(_index(values, observed[x]) + 1 for x in range(len(records))) for _ in states)
    elif kind == "bitset":
        values = tuple(_freeze(v) for v in spec["values"])
        states = tuple(range(1 << len(values)))
        observed = tuple(_eval(spec["value"], r) for r in records)
        table = tuple(tuple(s | (1 << _index(values, observed[x])) for x in range(len(records))) for s in states)
    elif kind == "histogram":
        values = tuple(_freeze(v) for v in spec["values"])
        cap = spec["cap"]
        states = tuple(product(range(cap + 1), repeat=len(values)))

        def step(state, record):
            nxt = list(state)
            i = _index(values, _eval(spec["value"], record))
            nxt[i] = min(cap, nxt[i] + 1)
            return tuple(nxt)

        table = _table(states, records, step)
    elif kind == "window":
        width = spec["width"]
        states = _window_states(width)

        def step(state, record):
            value = _eval(spec["predicate"], record)
            if type(value) is not bool:
                raise ValueError("window predicate must be Boolean")
            return (state + (value,))[-width:]

        table = _table(states, records, step)
    else:
        raise ValueError(f"unsupported retention kind {kind!r}")
    default_cost = max(1, math.ceil(math.log2(len(states))))
    expected_cost = default_cost if spec.get("cost") in (None, "state_bits") else spec["cost"]
    return table, expected_cost, _initial(spec, states)


def _dual(spec: dict[str, Any], base: str, historical: str, future: str):
    if base in spec:
        return spec[base], spec[base]
    return spec[historical], spec[future]


def _monitor(spec: dict[str, Any], history_records, future_records):
    kind = spec["kind"]
    if kind in {"seen", "count_threshold", "run_threshold", "window_pattern"}:
        hp, fp = _dual(spec, "predicate", "history_predicate", "future_predicate")
        hv = fv = None
    else:
        hv, fv = _dual(spec, "value", "history_value", "future_value")
        hp = fp = None
    if kind in {"seen", "count_threshold", "run_threshold"}:
        threshold = 1 if kind == "seen" else spec["threshold"]
        states = tuple(range(threshold + 1))
        hb = tuple(_eval(hp, r) for r in history_records)
        fb = tuple(_eval(fp, r) for r in future_records)
        if any(type(value) is not bool for value in hb + fb):
            raise ValueError("monitor predicate must be Boolean")
        if kind in {"seen", "count_threshold"}:
            history = tuple(tuple(min(threshold, s + int(hb[x])) for x in range(len(history_records))) for s in states)
            future = tuple(tuple(min(threshold, s + int(fb[x])) for x in range(len(future_records))) for s in states)
        else:
            history = tuple(tuple(min(threshold, s + 1) if hb[x] else 0 for x in range(len(history_records))) for s in states)
            future = tuple(tuple(min(threshold, s + 1) if fb[x] else 0 for x in range(len(future_records))) for s in states)
        output = tuple(int(s >= threshold) for s in states)
    elif kind == "last_equals":
        values = tuple(_freeze(v) for v in spec["values"])
        states = tuple(range(len(values) + 1))
        hvals = tuple(_eval(hv, r) for r in history_records)
        fvals = tuple(_eval(fv, r) for r in future_records)
        history = tuple(tuple(_index(values, hvals[x]) + 1 for x in range(len(history_records))) for _ in states)
        future = tuple(tuple(_index(values, fvals[x]) + 1 for x in range(len(future_records))) for _ in states)
        target = _index(values, _freeze(spec["target"])) + 1
        output = tuple(int(s == target) for s in states)
    elif kind in {"bitset_any", "bitset_all"}:
        values = tuple(_freeze(v) for v in spec["values"])
        states = tuple(range(1 << len(values)))
        hvals = tuple(_eval(hv, r) for r in history_records)
        fvals = tuple(_eval(fv, r) for r in future_records)
        history = tuple(tuple(s | (1 << _index(values, hvals[x])) for x in range(len(history_records))) for s in states)
        future = tuple(tuple(s | (1 << _index(values, fvals[x])) for x in range(len(future_records))) for s in states)
        required_indices = {_index(values, _freeze(v)) for v in spec["required"]}
        required_mask = 0
        for index in required_indices:
            required_mask |= 1 << index
        if kind == "bitset_any":
            output = tuple(int(bool(s & required_mask)) for s in states)
        else:
            output = tuple(int((s & required_mask) == required_mask) for s in states)
    elif kind == "window_pattern":
        pattern = tuple(spec["pattern"])
        width = len(pattern)
        states = _window_states(width)

        def make_step(expr):
            def step(state, record):
                value = _eval(expr, record)
                if type(value) is not bool:
                    raise ValueError("window predicate must be Boolean")
                return (state + (value,))[-width:]
            return step

        history = _table(states, history_records, make_step(hp))
        future = _table(states, future_records, make_step(fp))
        output = tuple(int(s == pattern) for s in states)
    else:
        raise ValueError(f"unsupported monitor kind {kind!r}")
    return history, future, output, _initial(spec, states)


def check_compilation(document: dict[str, Any], problem: PortfolioProblem) -> dict[str, int]:
    """Recompute transitions, outputs, explicit initials, and empty histories."""
    history_records = _records(document["history_schema"])
    future_records = _records(document["future_schema"])
    if not _same_value(tuple(problem.metadata["history_records"]), history_records):
        raise AssertionError("history record enumeration mismatch")
    if not _same_value(tuple(problem.metadata["future_records"]), future_records):
        raise AssertionError("future record enumeration mismatch")
    if len(document["retention_atoms"]) != len(problem.atoms):
        raise AssertionError("retention atom count mismatch")
    if len(document["monitor_updates"]) != len(problem.updates):
        raise AssertionError("monitor update count mismatch")
    atom_cells = monitor_cells = output_cells = 0
    initial_checks = empty_history_checks = 0
    for spec, atom in zip(document["retention_atoms"], problem.atoms):
        expected, cost, initial = _atom(spec, history_records)
        if expected != atom.transition or cost != atom.cost or spec["name"] != atom.name:
            raise AssertionError(f"retention semantics mismatch for {spec['name']}")
        if atom.initial != initial:
            raise AssertionError(f"retention initial mismatch for {spec['name']}")
        if run_table(atom.transition, atom.initial, ()) != initial:
            raise AssertionError(f"retention empty-history mismatch for {spec['name']}")
        initial_checks += 1
        empty_history_checks += 1
        atom_cells += sum(len(row) for row in expected)
    for spec, update in zip(document["monitor_updates"], problem.updates):
        history, future, output, initial = _monitor(spec, history_records, future_records)
        if history != update.history or future != update.future or output != update.output or spec["name"] != update.name:
            raise AssertionError(f"monitor semantics mismatch for {spec['name']}")
        if update.initial != initial:
            raise AssertionError(f"monitor initial mismatch for {spec['name']}")
        if run_table(update.history, update.initial, ()) != initial:
            raise AssertionError(f"monitor empty-history mismatch for {spec['name']}")
        if update.output[run_table(update.history, update.initial, ())] != output[initial]:
            raise AssertionError(f"monitor empty-history output mismatch for {spec['name']}")
        initial_checks += 1
        empty_history_checks += 1
        monitor_cells += sum(len(row) for row in history) + sum(len(row) for row in future)
        output_cells += len(output)
    return {
        "history_records": len(history_records),
        "future_records": len(future_records),
        "retention_atoms": len(problem.atoms),
        "monitor_updates": len(problem.updates),
        "retention_transition_cells": atom_cells,
        "monitor_transition_cells": monitor_cells,
        "monitor_output_cells": output_cells,
        "initial_states_checked": initial_checks,
        "empty_histories_checked": empty_history_checks,
    }
