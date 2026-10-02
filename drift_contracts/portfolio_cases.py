"""Deterministic bounded catalogues for portfolio validation."""
from __future__ import annotations
from itertools import product
from typing import Iterator

from .portfolio_model import MonitorUpdate, PortfolioProblem, RetentionAtom


def tables(states: int, alphabet: int) -> tuple[tuple[tuple[int, ...], ...], ...]:
    return tuple(tuple(tuple(values[row * alphabet:(row + 1) * alphabet])
                       for row in range(states))
                 for values in product(range(states), repeat=states * alphabet))


def outputs(states: int) -> tuple[tuple[int, ...], ...]:
    return tuple(tuple(values) for values in product((0, 1), repeat=states))


def unary_catalogue() -> Iterator[tuple[int, PortfolioProblem, tuple[int, ...]]]:
    """All 4,096 unary two-state problems with three candidate atoms.

    The returned encoding records the indices of three atom tables, one history
    table, one future table, and one output vector.
    """
    ts = tables(2, 1)
    outs = outputs(2)
    case_id = 0
    for a0, a1, a2, history, future, out in product(range(4), repeat=6):
        # The final dimension indexes outputs, also of cardinality four.
        atoms = tuple(RetentionAtom(f"a{i}", i + 1, ts[t])
                      for i, t in enumerate((a0, a1, a2)))
        update = MonitorUpdate("u0", ts[history], ts[future], outs[out])
        problem = PortfolioProblem(f"unary-{case_id:04d}", ("h",), ("f",),
                                   atoms, (update,))
        yield case_id, problem, (a0, a1, a2, history, future, out)
        case_id += 1


def binary_catalogue() -> Iterator[tuple[int, PortfolioProblem, tuple[int, ...]]]:
    """A complete 16,384-case binary subspace with four fixed target variants."""
    ts = tables(2, 2)
    outs = outputs(2)
    variants = (
        (0, 1),   # all transitions to 0, distinguishing output
        (6, 1),   # mixed reset/set behavior, distinguishing output
        (9, 2),   # complementary mixed behavior, reversed output
        (15, 3),  # all transitions to 1, constant output
    )
    case_id = 0
    for a0, a1, history, variant in product(range(16), range(16), range(16), range(4)):
        future, out = variants[variant]
        atoms = (RetentionAtom("a0", 1, ts[a0]), RetentionAtom("a1", 2, ts[a1]))
        update = MonitorUpdate("u0", ts[history], ts[future], outs[out])
        problem = PortfolioProblem(f"binary-{case_id:05d}", ("h0", "h1"),
                                   ("f0", "f1"), atoms, (update,))
        yield case_id, problem, (a0, a1, history, variant, future, out)
        case_id += 1
