"""Compiler for the bounded declarative monitoring and retention language.

The JSON surface language describes finite categorical record schemas,
retention atoms, and monitor updates whose historical and future predicates may
use different schemas.  Compilation enumerates finite record alphabets and emits
the extensional tables consumed by the exact portfolio analysis.  Every object
layer has an explicit field schema, every machine has an explicit initial-state
index, and all dimensions are checked before allocation.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import json
import math
from pathlib import Path
from typing import Any, Callable

from .limits import (MAX_MACHINE_STATES, MAX_RECORDS, checked_product,
                     require_machine_budget)
from .portfolio_model import MonitorUpdate, PortfolioProblem, RetentionAtom


Json = Any
Record = dict[str, Any]


def _freeze(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, dict):
        if any(type(key) is not str for key in value):
            raise ValueError("JSON object keys must be strings")
        # Canonical key order must not erase the object/array distinction.
        # An object is not the array of its key/value pairs.
        return {key: _freeze(value[key]) for key in sorted(value)}
    if value is None or type(value) in (bool, int, str):
        return value
    raise ValueError(f"unsupported JSON value {value!r}")


def _typed_key(value: Any) -> tuple[str, str]:
    frozen = _freeze(value)
    return (type(frozen).__name__, repr(frozen))


def _expect_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _expect_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    return value


def _check_fields(obj: dict[str, Any], *, allowed: set[str], required: set[str], name: str) -> None:
    unknown = set(obj) - allowed
    missing = required - set(obj)
    if unknown:
        raise ValueError(f"{name} has unknown field(s): {', '.join(sorted(unknown))}")
    if missing:
        raise ValueError(f"{name} is missing field(s): {', '.join(sorted(missing))}")


def _explicit_initial(spec: dict[str, Any], state_count: int, name: str) -> int:
    value = spec.get("initial")
    if type(value) is not int:
        raise ValueError(f"{name}.initial must be an explicit integer state index")
    if not 0 <= value < state_count:
        raise ValueError(f"{name}.initial outside state range")
    return value


def _enumerate_schema(value: Any, name: str) -> tuple[tuple[str, ...], tuple[Record, ...]]:
    schema = _expect_mapping(value, name)
    _check_fields(schema, allowed={"fields"}, required={"fields"}, name=name)
    fields_obj = _expect_mapping(schema["fields"], f"{name}.fields")
    if not fields_obj:
        raise ValueError(f"{name}.fields must be nonempty")
    fields = tuple(fields_obj)
    if any(not isinstance(field, str) or not field for field in fields):
        raise ValueError(f"{name} field names must be nonempty strings")
    domains: list[tuple[Any, ...]] = []
    count = 1
    for field in fields:
        values = _expect_list(fields_obj[field], f"{name}.fields.{field}")
        if not values:
            raise ValueError(f"domain for {field} must be nonempty")
        frozen = tuple(_freeze(item) for item in values)
        if len({_typed_key(item) for item in frozen}) != len(frozen):
            raise ValueError(f"domain for {field} contains duplicate values")
        domains.append(frozen)
        if count > MAX_RECORDS // len(frozen):
            raise ValueError(f"{name} expands above {MAX_RECORDS} records")
        count *= len(frozen)
    records = tuple(dict(zip(fields, values)) for values in product(*domains))
    return fields, records


def _eval(expr: Any, record: Record) -> Any:
    if expr is None or type(expr) in (bool, int, str) or isinstance(expr, list):
        return _freeze(expr)
    obj = _expect_mapping(expr, "expression")
    if set(obj) == {"field"}:
        field = obj["field"]
        if not isinstance(field, str) or field not in record:
            raise ValueError(f"unknown field {field!r}")
        return record[field]
    if set(obj) == {"const"}:
        return _freeze(obj["const"])
    _check_fields(obj, allowed={"op", "args"}, required={"op", "args"}, name="operator expression")
    op = obj["op"]
    args = obj["args"]
    if not isinstance(op, str) or not isinstance(args, list):
        raise ValueError("operator expression requires string op and array args")
    values = [_eval(arg, record) for arg in args]
    if op == "not":
        if len(values) != 1 or type(values[0]) is not bool:
            raise ValueError("operator 'not' expects one Boolean argument")
        return not values[0]
    if op in {"and", "or"}:
        if not values or any(type(value) is not bool for value in values):
            raise ValueError(f"operator {op!r} expects Boolean arguments")
        return all(values) if op == "and" else any(values)
    if op == "tuple":
        return tuple(values)
    if op == "in":
        if len(values) != 2 or not isinstance(values[1], tuple):
            raise ValueError("operator 'in' expects a value and an explicit finite array")
        needle = _typed_key(values[0])
        return any(needle == _typed_key(candidate) for candidate in values[1])
    if len(values) != 2:
        raise ValueError(f"operator {op!r} expects two arguments")
    left, right = values
    if op == "eq":
        return _typed_key(left) == _typed_key(right)
    if op == "ne":
        return _typed_key(left) != _typed_key(right)
    if op == "lt":
        return left < right
    if op == "le":
        return left <= right
    if op == "gt":
        return left > right
    if op == "ge":
        return left >= right
    raise ValueError(f"unsupported operator {op!r}")


def _bools(expr: Any, records: tuple[Record, ...], name: str) -> tuple[bool, ...]:
    values: list[bool] = []
    for record in records:
        value = _eval(expr, record)
        if type(value) is not bool:
            raise ValueError(f"{name} must evaluate to a Boolean")
        values.append(value)
    return tuple(values)


def _values(expr: Any, records: tuple[Record, ...]) -> tuple[Any, ...]:
    return tuple(_eval(expr, record) for record in records)


def _bits_for_states(count: int) -> int:
    return max(1, math.ceil(math.log2(count)))


def _cost(spec: dict[str, Any], states: int) -> int:
    value = spec.get("cost")
    if value is None or value == "state_bits":
        return _bits_for_states(states)
    if type(value) is not int or value <= 0:
        raise ValueError("cost must be a positive integer or 'state_bits'")
    return value


def _table(states: tuple[Any, ...], records: tuple[Any, ...],
           step: Callable[[Any, Any], Any], name: str) -> tuple[tuple[int, ...], ...]:
    require_machine_budget(len(states), len(records), tables=1, name=name)
    index = {_typed_key(state): i for i, state in enumerate(states)}
    if len(index) != len(states):
        raise ValueError(f"{name} has duplicate states")
    rows: list[tuple[int, ...]] = []
    for state in states:
        row: list[int] = []
        for record in records:
            nxt = step(state, record)
            key = _typed_key(nxt)
            if key not in index:
                raise ValueError(f"{name} transition escaped its state space: {nxt!r}")
            row.append(index[key])
        rows.append(tuple(row))
    return tuple(rows)


def _window_state_count(width: int) -> int:
    if type(width) is not int or not 1 <= width <= 10:
        raise ValueError("window width must be in 1..10")
    return (1 << (width + 1)) - 1


def _window_states(width: int) -> tuple[tuple[bool, ...], ...]:
    count = _window_state_count(width)
    if count > MAX_MACHINE_STATES:
        raise ValueError(f"window expands above {MAX_MACHINE_STATES} states")
    states: list[tuple[bool, ...]] = [()]
    for length in range(1, width + 1):
        states.extend(tuple(bits) for bits in product((False, True), repeat=length))
    return tuple(states)


def _value_domain(spec: dict[str, Any], key: str = "values") -> tuple[Any, ...]:
    values = tuple(_freeze(item) for item in _expect_list(spec.get(key), key))
    if not values or len({_typed_key(item) for item in values}) != len(values):
        raise ValueError(f"{key} must be a nonempty duplicate-free array")
    return values


_ATOM_COMMON = {"name", "kind", "initial", "cost", "description"}
_ATOM_REQUIRED = {"name", "kind", "initial"}
_ATOM_ALLOWED: dict[str, set[str]] = {
    "seen": _ATOM_COMMON | {"predicate"},
    "count": _ATOM_COMMON | {"cap", "predicate"},
    "run": _ATOM_COMMON | {"cap", "predicate"},
    "last": _ATOM_COMMON | {"value", "values"},
    "bitset": _ATOM_COMMON | {"value", "values"},
    "histogram": _ATOM_COMMON | {"cap", "value", "values"},
    "window": _ATOM_COMMON | {"width", "predicate"},
}
_ATOM_KIND_REQUIRED: dict[str, set[str]] = {
    "seen": {"predicate"},
    "count": {"cap", "predicate"},
    "run": {"cap", "predicate"},
    "last": {"value", "values"},
    "bitset": {"value", "values"},
    "histogram": {"cap", "value", "values"},
    "window": {"width", "predicate"},
}


def _compile_atom(spec_value: Any, records: tuple[Record, ...]) -> RetentionAtom:
    spec = _expect_mapping(spec_value, "retention atom")
    name = spec.get("name")
    kind = spec.get("kind")
    if not isinstance(name, str) or not name or not isinstance(kind, str):
        raise ValueError("retention atom requires nonempty name and kind")
    if kind not in _ATOM_ALLOWED:
        raise ValueError(f"unsupported retention kind {kind!r}")
    _check_fields(spec, allowed=_ATOM_ALLOWED[kind],
                  required=_ATOM_REQUIRED | _ATOM_KIND_REQUIRED[kind],
                  name=f"retention atom {name}")
    description = spec.get("description", "")
    if not isinstance(description, str):
        raise ValueError("description must be a string")

    if kind in {"seen", "count", "run"}:
        cap = 1 if kind == "seen" else spec["cap"]
        if type(cap) is not int or cap < 1:
            raise ValueError(f"{kind} cap must be a positive integer")
        state_count = cap + 1
        require_machine_budget(state_count, len(records), tables=1, name=f"atom {name}")
        truth = _bools(spec["predicate"], records, f"atom {name} predicate")
        states = tuple(range(state_count))
        if kind in {"seen", "count"}:
            table = tuple(tuple(min(cap, state + int(truth[x])) for x in range(len(records)))
                          for state in states)
        else:
            table = tuple(tuple(min(cap, state + 1) if truth[x] else 0
                                for x in range(len(records))) for state in states)
    elif kind == "last":
        values = _value_domain(spec)
        state_count = len(values) + 1
        require_machine_budget(state_count, len(records), tables=1, name=f"atom {name}")
        observed = _values(spec["value"], records)
        lookup = {_typed_key(value): i + 1 for i, value in enumerate(values)}
        if any(_typed_key(value) not in lookup for value in observed):
            raise ValueError(f"atom {name} observes a value outside values")
        states = tuple(range(state_count))
        table = tuple(tuple(lookup[_typed_key(observed[x])] for x in range(len(records)))
                      for _ in states)
    elif kind == "bitset":
        values = _value_domain(spec)
        if len(values) > 12:
            raise ValueError("bitset supports at most 12 declared values")
        state_count = 1 << len(values)
        require_machine_budget(state_count, len(records), tables=1, name=f"atom {name}")
        observed = _values(spec["value"], records)
        lookup = {_typed_key(value): i for i, value in enumerate(values)}
        if any(_typed_key(value) not in lookup for value in observed):
            raise ValueError(f"atom {name} observes a value outside values")
        states = tuple(range(state_count))
        table = tuple(tuple(state | (1 << lookup[_typed_key(observed[x])])
                            for x in range(len(records))) for state in states)
    elif kind == "histogram":
        values = _value_domain(spec)
        cap = spec["cap"]
        if type(cap) is not int or not 1 <= cap <= 15:
            raise ValueError("histogram cap must be in 1..15")
        state_count = checked_product([cap + 1] * len(values), MAX_MACHINE_STATES,
                                      f"atom {name} histogram states")
        require_machine_budget(state_count, len(records), tables=1, name=f"atom {name}")
        observed = _values(spec["value"], records)
        lookup = {_typed_key(value): i for i, value in enumerate(values)}
        if any(_typed_key(value) not in lookup for value in observed):
            raise ValueError(f"atom {name} observes a value outside values")
        states = tuple(product(range(cap + 1), repeat=len(values)))
        observed_indices = tuple(lookup[_typed_key(value)] for value in observed)

        def hist_step(state: tuple[int, ...], idx: int) -> tuple[int, ...]:
            result = list(state)
            result[idx] = min(cap, result[idx] + 1)
            return tuple(result)

        table = _table(states, observed_indices, hist_step, f"atom {name}")
    elif kind == "window":
        width = spec["width"]
        state_count = _window_state_count(width)
        require_machine_budget(state_count, len(records), tables=1, name=f"atom {name}")
        states = _window_states(width)
        truth = _bools(spec["predicate"], records, f"atom {name} predicate")

        def window_step(state: tuple[bool, ...], value: bool) -> tuple[bool, ...]:
            return (state + (value,))[-width:]

        table = _table(states, truth, window_step, f"atom {name}")
    else:  # pragma: no cover - guarded by field schema
        raise AssertionError(kind)
    initial = _explicit_initial(spec, len(states), f"retention atom {name}")
    return RetentionAtom(name=name, cost=_cost(spec, len(states)), transition=table,
                         initial=initial, description=description)


@dataclass(frozen=True)
class _MonitorMachine:
    states: tuple[Any, ...]
    history: tuple[tuple[int, ...], ...]
    future: tuple[tuple[int, ...], ...]
    output: tuple[int, ...]
    initial: int


_MONITOR_COMMON = {"name", "kind", "initial", "description"}
_MONITOR_ALLOWED: dict[str, set[str]] = {
    "seen": _MONITOR_COMMON | {"predicate", "history_predicate", "future_predicate"},
    "count_threshold": _MONITOR_COMMON | {"threshold", "predicate", "history_predicate", "future_predicate"},
    "run_threshold": _MONITOR_COMMON | {"threshold", "predicate", "history_predicate", "future_predicate"},
    "last_equals": _MONITOR_COMMON | {"values", "target", "value", "history_value", "future_value"},
    "bitset_any": _MONITOR_COMMON | {"values", "required", "value", "history_value", "future_value"},
    "bitset_all": _MONITOR_COMMON | {"values", "required", "value", "history_value", "future_value"},
    "window_pattern": _MONITOR_COMMON | {"pattern", "predicate", "history_predicate", "future_predicate"},
}


def _dual_expression(spec: dict[str, Any], base: str, historical: str, future: str,
                     name: str) -> tuple[Any, Any]:
    has_base = base in spec
    has_h = historical in spec
    has_f = future in spec
    if has_base and not has_h and not has_f:
        return spec[base], spec[base]
    if not has_base and has_h and has_f:
        return spec[historical], spec[future]
    raise ValueError(
        f"{name} must declare either {base!r} or both {historical!r} and {future!r}")


def _compile_monitor_machine(spec: dict[str, Any], history_records: tuple[Record, ...],
                             future_records: tuple[Record, ...], name: str) -> _MonitorMachine:
    kind = spec.get("kind")
    if not isinstance(kind, str):
        raise ValueError(f"update {name} requires a kind")
    if kind not in _MONITOR_ALLOWED:
        raise ValueError(f"unsupported monitor kind {kind!r}")
    required = {"name", "kind", "initial"}
    if kind in {"count_threshold", "run_threshold"}:
        required.add("threshold")
    if kind == "last_equals":
        required |= {"values", "target"}
    if kind in {"bitset_any", "bitset_all"}:
        required |= {"values", "required"}
    if kind == "window_pattern":
        required.add("pattern")
    _check_fields(spec, allowed=_MONITOR_ALLOWED[kind], required=required,
                  name=f"monitor update {name}")

    predicate_kind = kind in {"seen", "count_threshold", "run_threshold", "window_pattern"}
    if predicate_kind:
        hp, fp = _dual_expression(spec, "predicate", "history_predicate", "future_predicate",
                                  f"monitor update {name}")
        hv = fv = None
    else:
        hv, fv = _dual_expression(spec, "value", "history_value", "future_value",
                                  f"monitor update {name}")
        hp = fp = None

    if kind in {"seen", "count_threshold", "run_threshold"}:
        threshold = 1 if kind == "seen" else spec["threshold"]
        if type(threshold) is not int or threshold < 1:
            raise ValueError(f"update {name} threshold must be positive")
        state_count = threshold + 1
        require_machine_budget(state_count, max(len(history_records), len(future_records)),
                               tables=2, name=f"update {name}")
        states = tuple(range(state_count))
        hb = _bools(hp, history_records, f"update {name} historical predicate")
        fb = _bools(fp, future_records, f"update {name} future predicate")
        if kind in {"seen", "count_threshold"}:
            history = tuple(tuple(min(threshold, state + int(hb[x]))
                                  for x in range(len(history_records))) for state in states)
            future = tuple(tuple(min(threshold, state + int(fb[x]))
                                 for x in range(len(future_records))) for state in states)
        else:
            history = tuple(tuple(min(threshold, state + 1) if hb[x] else 0
                                  for x in range(len(history_records))) for state in states)
            future = tuple(tuple(min(threshold, state + 1) if fb[x] else 0
                                 for x in range(len(future_records))) for state in states)
        output = tuple(int(state >= threshold) for state in states)
    elif kind == "last_equals":
        values = _value_domain(spec)
        target = _freeze(spec["target"])
        lookup = {_typed_key(value): i + 1 for i, value in enumerate(values)}
        if _typed_key(target) not in lookup:
            raise ValueError(f"update {name} target is outside values")
        state_count = len(values) + 1
        require_machine_budget(state_count, max(len(history_records), len(future_records)),
                               tables=2, name=f"update {name}")
        hvalues = _values(hv, history_records)
        fvalues = _values(fv, future_records)
        if any(_typed_key(value) not in lookup for value in hvalues + fvalues):
            raise ValueError(f"update {name} observes a value outside values")
        states = tuple(range(state_count))
        history = tuple(tuple(lookup[_typed_key(hvalues[x])]
                              for x in range(len(history_records))) for _ in states)
        future = tuple(tuple(lookup[_typed_key(fvalues[x])]
                             for x in range(len(future_records))) for _ in states)
        output = tuple(int(state == lookup[_typed_key(target)]) for state in states)
    elif kind in {"bitset_any", "bitset_all"}:
        values = _value_domain(spec)
        if len(values) > 12:
            raise ValueError("bitset monitor supports at most 12 declared values")
        state_count = 1 << len(values)
        require_machine_budget(state_count, max(len(history_records), len(future_records)),
                               tables=2, name=f"update {name}")
        required_values = tuple(_freeze(item) for item in _expect_list(spec["required"], "required"))
        lookup = {_typed_key(value): i for i, value in enumerate(values)}
        if not required_values or any(_typed_key(value) not in lookup for value in required_values):
            raise ValueError(f"update {name} required values must be in values")
        hvalues = _values(hv, history_records)
        fvalues = _values(fv, future_records)
        if any(_typed_key(value) not in lookup for value in hvalues + fvalues):
            raise ValueError(f"update {name} observes a value outside values")
        states = tuple(range(state_count))
        history = tuple(tuple(state | (1 << lookup[_typed_key(hvalues[x])])
                              for x in range(len(history_records))) for state in states)
        future = tuple(tuple(state | (1 << lookup[_typed_key(fvalues[x])])
                             for x in range(len(future_records))) for state in states)
        # Required values denote a mathematical set: duplicates are idempotent.
        required_mask = 0
        for value in required_values:
            required_mask |= 1 << lookup[_typed_key(value)]
        if kind == "bitset_any":
            output = tuple(int(bool(state & required_mask)) for state in states)
        else:
            output = tuple(int((state & required_mask) == required_mask) for state in states)
    elif kind == "window_pattern":
        pattern_raw = _expect_list(spec["pattern"], "pattern")
        if not pattern_raw or any(type(value) is not bool for value in pattern_raw):
            raise ValueError("window pattern must be a nonempty Boolean array")
        pattern = tuple(pattern_raw)
        width = len(pattern)
        state_count = _window_state_count(width)
        require_machine_budget(state_count, max(len(history_records), len(future_records)),
                               tables=2, name=f"update {name}")
        states = _window_states(width)

        def window_step(state: tuple[bool, ...], value: bool) -> tuple[bool, ...]:
            return (state + (value,))[-width:]

        def make_table(expr: Any, records: tuple[Record, ...], table_name: str):
            truth = []
            for record in records:
                value = _eval(expr, record)
                if type(value) is not bool:
                    raise ValueError(f"update {name} predicate must be Boolean")
                truth.append(value)
            return _table(states, tuple(truth), window_step, table_name)

        history = make_table(hp, history_records, f"update {name} history")
        future = make_table(fp, future_records, f"update {name} future")
        output = tuple(int(state == pattern) for state in states)
    else:  # pragma: no cover - guarded by field schema
        raise AssertionError(kind)
    initial = _explicit_initial(spec, len(states), f"monitor update {name}")
    return _MonitorMachine(states, history, future, output, initial)


def _symbol(prefix: str, index: int, fields: tuple[str, ...], record: Record) -> str:
    values = ",".join(f"{field}={json.dumps(record[field], separators=(',', ':'))}"
                      for field in fields)
    return f"{prefix}{index}:{values}"


def compile_declaration(value: Any) -> PortfolioProblem:
    """Compile one JSON-compatible declaration to an extensional problem."""
    doc = _expect_mapping(value, "declaration")
    _check_fields(
        doc,
        allowed={"name", "metadata", "history_schema", "future_schema",
                 "retention_atoms", "monitor_updates"},
        required={"name", "history_schema", "future_schema", "retention_atoms", "monitor_updates"},
        name="declaration",
    )
    name = doc["name"]
    if not isinstance(name, str) or not name:
        raise ValueError("declaration requires a nonempty name")
    hfields, history_records = _enumerate_schema(doc["history_schema"], "history_schema")
    ffields, future_records = _enumerate_schema(doc["future_schema"], "future_schema")
    atom_specs = _expect_list(doc["retention_atoms"], "retention_atoms")
    update_specs = _expect_list(doc["monitor_updates"], "monitor_updates")
    if not atom_specs or not update_specs:
        raise ValueError("declaration requires retention_atoms and monitor_updates")
    atoms = tuple(_compile_atom(spec, history_records) for spec in atom_specs)
    updates: list[MonitorUpdate] = []
    for value in update_specs:
        spec = _expect_mapping(value, "monitor update")
        update_name = spec.get("name")
        if not isinstance(update_name, str) or not update_name:
            raise ValueError("monitor update requires a nonempty name")
        machine = _compile_monitor_machine(spec, history_records, future_records, update_name)
        description = spec.get("description", "")
        if not isinstance(description, str):
            raise ValueError("description must be a string")
        updates.append(MonitorUpdate(update_name, machine.history, machine.future,
                                     machine.output, initial=machine.initial,
                                     description=description))
    history_symbols = tuple(_symbol("h", i, hfields, record)
                            for i, record in enumerate(history_records))
    future_symbols = tuple(_symbol("f", i, ffields, record)
                           for i, record in enumerate(future_records))
    metadata_value = doc.get("metadata", {})
    metadata = dict(_expect_mapping(metadata_value, "metadata"))
    metadata.update({
        "language": "declarative-drift-contracts",
        "history_fields": list(hfields),
        "future_fields": list(ffields),
        "history_records": history_records,
        "future_records": future_records,
        "source_declaration": doc,
    })
    return PortfolioProblem(name, history_symbols, future_symbols, atoms,
                            tuple(updates), metadata)


def load_declaration(path: str | Path) -> PortfolioProblem:
    with Path(path).open("r", encoding="utf-8") as handle:
        return compile_declaration(json.load(handle))


def declaration_fingerprint(value: Any) -> str:
    """Stable semantic text for result records (not a cryptographic manifest)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
