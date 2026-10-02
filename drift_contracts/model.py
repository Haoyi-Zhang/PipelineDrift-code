"""Finite, deterministic history-retention and replay-target specifications.

No user-supplied code is evaluated. Transitions are explicit total tables.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Iterable


def _integer(value: Any, label: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{label} must be an integer, not a Boolean or string")
    return value


def _table(value: Any, label: str, width: int | None = None) -> tuple[tuple[int, ...], ...]:
    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= 128:
        raise ValueError(f"{label}: expected 1..128 rows")
    rows = []
    for i, row in enumerate(value):
        if not isinstance(row, (list, tuple)) or not 1 <= len(row) <= 8:
            raise ValueError(f"{label}[{i}]: expected 1..8 columns")
        if width is None:
            width = len(row)
        if len(row) != width:
            raise ValueError(f"{label}: nonrectangular table")
        rows.append(tuple(_integer(v, label) for v in row))
    return tuple(rows)


@dataclass(frozen=True)
class Contract:
    retain: tuple[tuple[int, ...], ...]
    history: tuple[tuple[int, ...], ...]
    future: tuple[tuple[int, ...], ...]
    output: tuple[int, ...]
    initial_retain: int = 0
    initial_target: int = 0

    def __post_init__(self) -> None:
        r = _table(self.retain, "retain")
        h = _table(self.history, "history", len(r[0]))
        f = _table(self.future, "future")
        if len(h) != len(f):
            raise ValueError("history and future must have the same target-state count")
        if not isinstance(self.output, (list, tuple)) or len(self.output) != len(h):
            raise ValueError("output: expected one verdict per target state")
        out = tuple(_integer(x, "output") for x in self.output)
        if any(x not in (0, 1) for x in out):
            raise ValueError("output verdicts must be 0 or 1")
        for table, n, name in [(r, len(r), "retain"), (h, len(h), "history"), (f, len(h), "future")]:
            if any(not 0 <= x < n for row in table for x in row):
                raise ValueError(f"{name}: state index out of range")
        for v, n, name in [(self.initial_retain, len(r), "initial_retain"),
                           (self.initial_target, len(h), "initial_target")]:
            if not 0 <= _integer(v, name) < n:
                raise ValueError(f"{name}: state index out of range")
        object.__setattr__(self, "retain", r)
        object.__setattr__(self, "history", h)
        object.__setattr__(self, "future", f)
        object.__setattr__(self, "output", out)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> 'Contract':
        if not isinstance(value, dict):
            raise ValueError("contract must be a JSON object")
        allowed = {"retain", "history", "future", "output", "initial_retain", "initial_target"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"unknown contract fields: {sorted(unknown)}")
        try:
            return cls(**value)
        except TypeError as exc:
            raise ValueError(f"invalid contract: {exc}") from exc

    def to_dict(self) -> dict[str, Any]:
        return {"retain": [list(x) for x in self.retain],
                "history": [list(x) for x in self.history],
                "future": [list(x) for x in self.future],
                "output": list(self.output),
                "initial_retain": self.initial_retain,
                "initial_target": self.initial_target}


def run(table: tuple[tuple[int, ...], ...], start: int, word: Iterable[int]) -> int:
    state = start
    for symbol in word:
        symbol = _integer(symbol, "input symbol")
        if not 0 <= symbol < len(table[0]):
            raise ValueError("input symbol outside alphabet")
        state = table[state][symbol]
    return state
