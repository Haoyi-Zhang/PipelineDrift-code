"""Search-independent verification for portfolio certificates.

This module intentionally does not import the conflict-basis constructor or the
optimizer.  It directly explores finite reachable products, recomputes future
equivalence and obstruction bases, validates migration representatives, and
enumerates candidate subsets for bounded optimality certificates.
"""
from __future__ import annotations
from collections import deque
from itertools import combinations
from typing import Any

from .limits import (AnalysisLimitError, require_pair_budget,
                     require_pair_transition_budget, require_product_budget,
                     require_subset_budget)
from .portfolio_model import PortfolioProblem, run_table


def _symbol_word(names: tuple[str, ...], value: Any) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise ValueError("word must be a list")
    index = {name: i for i, name in enumerate(names)}
    if len(index) != len(names):
        raise ValueError("duplicate alphabet symbol")
    result: list[int] = []
    for name in value:
        if not isinstance(name, str) or name not in index:
            raise ValueError("unknown word symbol")
        result.append(index[name])
    return tuple(result)


def verify_unsafe(problem: PortfolioProblem, certificate: dict[str, Any]) -> bool:
    """Replay a self-contained unsafe-portfolio certificate."""
    try:
        if not isinstance(certificate, dict) or certificate.get("kind") != "unsafe_portfolio":
            return False
        required = {"kind", "selected_mask", "update", "history_left", "history_right",
                    "suffix", "separator_atoms", "separator_mask", "target_left",
                    "target_right", "cost"}
        if set(certificate) != required:
            return False
        selected_mask = certificate["selected_mask"]
        if type(selected_mask) is not int:
            return False
        problem.cost(selected_mask)
        if certificate["update"] not in {u.name for u in problem.updates}:
            return False
        update = next(u for u in problem.updates if u.name == certificate["update"])
        left = _symbol_word(problem.history_symbols, certificate["history_left"])
        right = _symbol_word(problem.history_symbols, certificate["history_right"])
        suffix = _symbol_word(problem.future_symbols, certificate["suffix"])
        separator = 0
        for i, atom in enumerate(problem.atoms):
            p = run_table(atom.transition, atom.initial, left)
            q = run_table(atom.transition, atom.initial, right)
            if p != q:
                separator |= 1 << i
            if selected_mask >> i & 1 and p != q:
                return False
        if type(certificate["separator_mask"]) is not int or separator != certificate["separator_mask"]:
            return False
        if certificate["separator_atoms"] != problem.selected_names(separator):
            return False
        target_left = certificate["target_left"]
        target_right = certificate["target_right"]
        if (type(target_left) is not int or type(target_right) is not int or
                not 0 <= target_left < len(update.history) or
                not 0 <= target_right < len(update.history)):
            return False
        p = run_table(update.history, update.initial, left)
        q = run_table(update.history, update.initial, right)
        if (p, q) != (target_left, target_right):
            return False
        if type(certificate["cost"]) is not int or certificate["cost"] != len(left) + len(right) + len(suffix):
            return False
        p2 = run_table(update.future, p, suffix)
        q2 = run_table(update.future, q, suffix)
        return update.output[p2] != update.output[q2]
    except (ValueError, TypeError, KeyError, StopIteration, IndexError):
        return False


def _future_equivalent(update) -> set[tuple[int, int]]:
    require_pair_transition_budget(
        len(update.history), len(update.future[0]),
        f"update {update.name} future equivalence")
    relation = {(p, q) for p in range(len(update.history))
                         for q in range(len(update.history))
                         if update.output[p] == update.output[q]}
    changed = True
    while changed:
        changed = False
        remove = []
        for p, q in relation:
            if any((update.future[p][x], update.future[q][x]) not in relation
                   for x in range(len(update.future[0]))):
                remove.append((p, q))
        if remove:
            relation.difference_update(remove)
            changed = True
    return relation


def _reachable(problem: PortfolioProblem, update_index: int,
               atom_indices: tuple[int, ...]) -> set[tuple[int, ...]]:
    update = problem.updates[update_index]
    require_product_budget(
        [len(problem.atoms[i].transition) for i in atom_indices] + [len(update.history)],
        f"update {update.name} verifier product",
    )
    start = tuple(problem.atoms[i].initial for i in atom_indices) + (update.initial,)
    queue = deque([start])
    reachable = {start}
    while queue:
        state = queue.popleft()
        atom_states, q = state[:-1], state[-1]
        for x in range(len(problem.history_symbols)):
            nxt = tuple(problem.atoms[i].transition[s][x]
                        for i, s in zip(atom_indices, atom_states))
            nxt += (update.history[q][x],)
            if nxt not in reachable:
                reachable.add(nxt)
                queue.append(nxt)
    return reachable


def _obstruction_basis(problem: PortfolioProblem) -> list[int]:
    """Recompute the exact inclusion-minimal separator family independently."""
    masks: set[int] = set()
    all_indices = tuple(range(len(problem.atoms)))
    for update_index, update in enumerate(problem.updates):
        reachable = sorted(_reachable(problem, update_index, all_indices))
        require_pair_budget(len(reachable), f"update {update.name} verifier reachable")
        relation = _future_equivalent(update)
        for left, right in combinations(reachable, 2):
            if (left[-1], right[-1]) in relation:
                continue
            mask = 0
            for i, (p, q) in enumerate(zip(left[:-1], right[:-1])):
                if p != q:
                    mask |= 1 << i
            masks.add(mask)
    if 0 in masks:
        return [0]
    ordered = sorted(masks, key=lambda mask: (mask.bit_count(), mask))
    basis: list[int] = []
    for mask in ordered:
        if not any((smaller & mask) == smaller for smaller in basis):
            basis.append(mask)
    return basis


def verify_safe(problem: PortfolioProblem, selected_mask: int) -> bool:
    try:
        problem.cost(selected_mask)
        selected = tuple(i for i in range(len(problem.atoms)) if selected_mask >> i & 1)
        for update_index, update in enumerate(problem.updates):
            reachable = _reachable(problem, update_index, selected)
            relation = _future_equivalent(update)
            groups: dict[tuple[int, ...], list[int]] = {}
            for state in reachable:
                groups.setdefault(state[:-1], []).append(state[-1])
            for qs in groups.values():
                for p, q in combinations(qs, 2):
                    if (p, q) not in relation:
                        return False
        return True
    except AnalysisLimitError:
        raise
    except (ValueError, TypeError, IndexError):
        return False


def _verify_representatives(problem: PortfolioProblem, selected_mask: int,
                            value: Any) -> bool:
    if not isinstance(value, list) or len(value) != len(problem.updates):
        return False
    selected = tuple(i for i in range(len(problem.atoms)) if selected_mask >> i & 1)
    for update_index, (update, entry) in enumerate(zip(problem.updates, value)):
        if not isinstance(entry, dict) or set(entry) != {"update", "fibers"}:
            return False
        if entry["update"] != update.name or not isinstance(entry["fibers"], list):
            return False
        reachable = _reachable(problem, update_index, selected)
        groups: dict[tuple[int, ...], set[int]] = {}
        for state in reachable:
            groups.setdefault(state[:-1], set()).add(state[-1])
        expected_summaries = sorted(groups)
        fibers = entry["fibers"]
        if len(fibers) != len(expected_summaries):
            return False
        relation = _future_equivalent(update)
        seen: set[tuple[int, ...]] = set()
        for expected, fiber in zip(expected_summaries, fibers):
            if not isinstance(fiber, dict) or set(fiber) != {"summary_state", "target_state"}:
                return False
            raw_summary = fiber["summary_state"]
            if not isinstance(raw_summary, list) or any(type(x) is not int for x in raw_summary):
                return False
            summary = tuple(raw_summary)
            if summary != expected or summary in seen:
                return False
            seen.add(summary)
            representative = fiber["target_state"]
            if type(representative) is not int or representative not in groups[summary]:
                return False
            if any((representative, q) not in relation for q in groups[summary]):
                return False
    return True


def verify_optimal(problem: PortfolioProblem, certificate: dict[str, Any]) -> bool:
    try:
        if not isinstance(certificate, dict) or set(certificate) != {
            "kind", "selected_mask", "selected_atoms", "cost",
            "obstruction_basis", "representatives"}:
            return False
        if certificate["kind"] != "optimal_portfolio":
            return False
        mask = certificate["selected_mask"]
        if type(mask) is not int or certificate["selected_atoms"] != problem.selected_names(mask):
            return False
        cost = problem.cost(mask)
        if type(certificate["cost"]) is not int or certificate["cost"] != cost:
            return False
        basis = certificate["obstruction_basis"]
        if (not isinstance(basis, list) or
                any(type(value) is not int for value in basis) or
                basis != _obstruction_basis(problem)):
            return False
        if not verify_safe(problem, mask):
            return False
        if not _verify_representatives(problem, mask, certificate["representatives"]):
            return False
        # Exact bounded oracle. This is intentionally independent of branch-and-bound.
        require_subset_budget(len(problem.atoms), "optimal-certificate verifier")
        chosen_key = (cost, mask.bit_count(), mask)
        for other in range(1 << len(problem.atoms)):
            other_key = (problem.cost(other), other.bit_count(), other)
            if other_key < chosen_key and verify_safe(problem, other):
                return False
        return True
    except AnalysisLimitError:
        raise
    except (ValueError, TypeError, KeyError):
        return False
