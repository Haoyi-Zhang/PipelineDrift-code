"""Explicit finite-analysis budgets shared by compiler, analyzer, and verifier.

The limits are part of the supported bounded interface.  They are checked from
integer dimensions before constructing transition tables, product graphs, state
pairs, or exhaustive subset ranges.  Hitting a limit is an analysis refusal,
not a safety or infeasibility result.
"""
from __future__ import annotations

MAX_MACHINE_STATES = 4_096
MAX_RECORDS = 4_096
MAX_TRANSITION_CELLS = 1_000_000
MAX_PRODUCT_STATES = 100_000
MAX_STATE_PAIRS = 1_000_000
MAX_PAIR_TRANSITION_CELLS = 2_000_000
MAX_PORTFOLIO_SUBSETS = 1_048_576  # 2**20


class AnalysisLimitError(ValueError):
    """A configured finite-analysis budget would be exceeded."""


def _exact_nonnegative(value: int, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def checked_product(factors: tuple[int, ...] | list[int], limit: int, name: str) -> int:
    """Multiply dimensions without constructing the represented object."""
    total = 1
    for index, factor in enumerate(factors):
        _exact_nonnegative(factor, f"{name} factor {index}")
        if factor == 0:
            return 0
        if total > limit // factor:
            raise AnalysisLimitError(f"{name} exceeds configured limit {limit}")
        total *= factor
    return total


def require_machine_budget(state_count: int, symbol_count: int, *, tables: int, name: str) -> int:
    _exact_nonnegative(state_count, f"{name} state count")
    _exact_nonnegative(symbol_count, f"{name} symbol count")
    _exact_nonnegative(tables, f"{name} table count")
    if state_count < 1 or state_count > MAX_MACHINE_STATES:
        raise AnalysisLimitError(f"{name} must have 1..{MAX_MACHINE_STATES} states")
    cells = checked_product(
        [state_count, symbol_count, tables], MAX_TRANSITION_CELLS,
        f"{name} transition cells")
    return cells


def require_product_budget(state_counts: tuple[int, ...] | list[int], name: str) -> int:
    total = checked_product(state_counts, MAX_PRODUCT_STATES, f"{name} product states")
    if total < 1:
        raise ValueError(f"{name} product must be nonempty")
    return total


def require_pair_budget(state_count: int, name: str, *, ordered: bool = False) -> int:
    _exact_nonnegative(state_count, f"{name} state count")
    pairs = state_count * state_count if ordered else state_count * max(0, state_count - 1) // 2
    if pairs > MAX_STATE_PAIRS:
        raise AnalysisLimitError(f"{name} state pairs exceed configured limit {MAX_STATE_PAIRS}")
    return pairs




def require_pair_transition_budget(state_count: int, symbol_count: int, name: str) -> int:
    """Bound explicit work over ordered state pairs and input symbols."""
    _exact_nonnegative(state_count, f"{name} state count")
    _exact_nonnegative(symbol_count, f"{name} symbol count")
    require_pair_budget(state_count, name, ordered=True)
    return checked_product(
        [state_count, state_count, symbol_count],
        MAX_PAIR_TRANSITION_CELLS,
        f"{name} pair-transition cells",
    )

def require_subset_budget(atom_count: int, name: str = "portfolio") -> int:
    _exact_nonnegative(atom_count, f"{name} atom count")
    # Avoid constructing or iterating a range whose size exceeds the contract.
    if atom_count >= MAX_PORTFOLIO_SUBSETS.bit_length():
        raise AnalysisLimitError(
            f"{name} exhaustive subsets exceed configured limit {MAX_PORTFOLIO_SUBSETS}")
    subsets = 1 << atom_count
    if subsets > MAX_PORTFOLIO_SUBSETS:
        raise AnalysisLimitError(
            f"{name} exhaustive subsets exceed configured limit {MAX_PORTFOLIO_SUBSETS}")
    return subsets
