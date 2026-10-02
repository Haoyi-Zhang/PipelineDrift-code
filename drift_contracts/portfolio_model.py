"""Finite retention-portfolio model for evolving monitors.

The model is deliberately extensional: declarations are compiled to total
transition tables before analysis.  This keeps the semantic core independent
of the surface language and makes certificates replayable with only Python's
standard library.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any, Iterable


def _check_table(table: Any, name: str) -> tuple[tuple[int, ...], ...]:
    if not isinstance(table, (list, tuple)) or not table:
        raise ValueError(f"{name} must be a nonempty transition table")
    rows: list[tuple[int, ...]] = []
    width: int | None = None
    n = len(table)
    for row in table:
        if not isinstance(row, (list, tuple)) or not row:
            raise ValueError(f"{name} rows must be nonempty")
        if width is None:
            width = len(row)
        elif len(row) != width:
            raise ValueError(f"{name} rows must have equal width")
        converted: list[int] = []
        for value in row:
            if type(value) is not int or not 0 <= value < n:
                raise ValueError(f"{name} destination outside state range")
            converted.append(value)
        rows.append(tuple(converted))
    return tuple(rows)


def run_table(table: tuple[tuple[int, ...], ...], initial: int,
              word: Iterable[int]) -> int:
    if type(initial) is not int or not 0 <= initial < len(table):
        raise ValueError("initial state outside range")
    state = initial
    width = len(table[0])
    for symbol in word:
        if type(symbol) is not int or not 0 <= symbol < width:
            raise ValueError("input symbol outside alphabet")
        state = table[state][symbol]
    return state


@dataclass(frozen=True)
class RetentionAtom:
    name: str
    cost: int
    transition: tuple[tuple[int, ...], ...]
    initial: int = 0
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("atom name must be nonempty")
        if type(self.cost) is not int or self.cost <= 0:
            raise ValueError("atom cost must be a positive integer")
        table = _check_table(self.transition, f"atom {self.name}")
        object.__setattr__(self, "transition", table)
        if type(self.initial) is not int or not 0 <= self.initial < len(table):
            raise ValueError("atom initial state outside range")
        if not isinstance(self.description, str):
            raise ValueError("atom description must be a string")


@dataclass(frozen=True)
class MonitorUpdate:
    name: str
    history: tuple[tuple[int, ...], ...]
    future: tuple[tuple[int, ...], ...]
    output: tuple[int, ...]
    initial: int = 0
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("update name must be nonempty")
        history = _check_table(self.history, f"update {self.name} history")
        future = _check_table(self.future, f"update {self.name} future")
        if len(history) != len(future):
            raise ValueError("history and future tables must share target states")
        object.__setattr__(self, "history", history)
        object.__setattr__(self, "future", future)
        if not isinstance(self.output, (list, tuple)) or len(self.output) != len(history):
            raise ValueError("output vector must match target state count")
        output = tuple(self.output)
        if any(type(value) is not int or value not in (0, 1) for value in output):
            raise ValueError("outputs must be binary integers")
        object.__setattr__(self, "output", output)
        if type(self.initial) is not int or not 0 <= self.initial < len(history):
            raise ValueError("update initial state outside range")
        if not isinstance(self.description, str):
            raise ValueError("update description must be a string")


@dataclass(frozen=True)
class PortfolioProblem:
    name: str
    history_symbols: tuple[str, ...]
    future_symbols: tuple[str, ...]
    atoms: tuple[RetentionAtom, ...]
    updates: tuple[MonitorUpdate, ...]
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("problem name must be nonempty")
        hs = tuple(self.history_symbols)
        fs = tuple(self.future_symbols)
        atoms = tuple(self.atoms)
        updates = tuple(self.updates)
        if not hs or not fs:
            raise ValueError("history and future alphabets must be nonempty")
        if any(not isinstance(symbol, str) or not symbol for symbol in hs + fs):
            raise ValueError("alphabet symbols must be nonempty strings")
        if len(set(hs)) != len(hs) or len(set(fs)) != len(fs):
            raise ValueError("symbol names must be unique within each alphabet")
        if not atoms or not updates:
            raise ValueError("a portfolio problem needs atoms and updates")
        if len({atom.name for atom in atoms}) != len(atoms):
            raise ValueError("atom names must be unique")
        if len({update.name for update in updates}) != len(updates):
            raise ValueError("update names must be unique")
        for atom in atoms:
            if len(atom.transition[0]) != len(hs):
                raise ValueError(f"atom {atom.name} has wrong history alphabet")
        for update in updates:
            if len(update.history[0]) != len(hs):
                raise ValueError(f"update {update.name} has wrong history alphabet")
            if len(update.future[0]) != len(fs):
                raise ValueError(f"update {update.name} has wrong future alphabet")
        if self.metadata is not None and not isinstance(self.metadata, Mapping):
            raise ValueError("metadata must be a mapping")
        object.__setattr__(self, "history_symbols", hs)
        object.__setattr__(self, "future_symbols", fs)
        object.__setattr__(self, "atoms", atoms)
        object.__setattr__(self, "updates", updates)
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    @property
    def all_mask(self) -> int:
        return (1 << len(self.atoms)) - 1

    def cost(self, mask: int) -> int:
        if type(mask) is not int or mask < 0 or mask & ~self.all_mask:
            raise ValueError("portfolio mask outside candidate range")
        return sum(atom.cost for i, atom in enumerate(self.atoms) if mask >> i & 1)

    def selected_names(self, mask: int) -> list[str]:
        self.cost(mask)
        return [atom.name for i, atom in enumerate(self.atoms) if mask >> i & 1]
