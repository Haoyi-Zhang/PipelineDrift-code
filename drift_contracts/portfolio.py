"""Exact conflict-basis construction and retention-portfolio synthesis."""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from itertools import combinations
from typing import Any

from .limits import (require_pair_budget, require_pair_transition_budget,
                     require_product_budget, require_subset_budget)
from .portfolio_model import PortfolioProblem


@dataclass(frozen=True)
class Witness:
    update: int
    history_left: tuple[int, ...]
    history_right: tuple[int, ...]
    suffix: tuple[int, ...]
    separator_mask: int
    target_left: int
    target_right: int

    @property
    def cost(self) -> int:
        return len(self.history_left) + len(self.history_right) + len(self.suffix)

    def key(self) -> tuple[Any, ...]:
        return (self.cost, self.update, len(self.history_left), self.history_left,
                len(self.history_right), self.history_right, self.suffix,
                self.separator_mask, self.target_left, self.target_right)

    def as_dict(self, problem: PortfolioProblem) -> dict[str, Any]:
        return {
            "update": problem.updates[self.update].name,
            "history_left": [problem.history_symbols[x] for x in self.history_left],
            "history_right": [problem.history_symbols[x] for x in self.history_right],
            "suffix": [problem.future_symbols[x] for x in self.suffix],
            "separator_atoms": problem.selected_names(self.separator_mask),
            "separator_mask": self.separator_mask,
            "target_left": self.target_left,
            "target_right": self.target_right,
            "cost": self.cost,
        }


@dataclass(frozen=True)
class ConflictAnalysis:
    obligations: tuple[int, ...]
    witnesses: dict[int, Witness]
    all_witnesses: dict[int, Witness]
    update_obligations: tuple[tuple[int, ...], ...]
    reachable_signatures: tuple[int, ...]
    conflict_pairs: int

    @property
    def feasible(self) -> bool:
        return 0 not in self.all_witnesses


@lru_cache(maxsize=512)
def _future_distances(future: tuple[tuple[int, ...], ...],
                      output: tuple[int, ...]) -> tuple[int | None, ...]:
    n = len(future)
    a = len(future[0])
    require_pair_transition_budget(n, a, "future-equivalence")
    reverse: list[list[int]] = [[] for _ in range(n * n)]
    for p in range(n):
        for q in range(n):
            for x in range(a):
                reverse[future[p][x] * n + future[q][x]].append(p * n + q)
    distances: list[int | None] = [None] * (n * n)
    queue: deque[int] = deque()
    for p in range(n):
        for q in range(n):
            if output[p] != output[q]:
                distances[p * n + q] = 0
                queue.append(p * n + q)
    while queue:
        target = queue.popleft()
        d = distances[target]
        assert d is not None
        for source in reverse[target]:
            if distances[source] is None:
                distances[source] = d + 1
                queue.append(source)
    return tuple(distances)


def _suffix(update, p: int, q: int, distances: tuple[int | None, ...]) -> tuple[int, ...]:
    n = len(update.history)
    d = distances[p * n + q]
    if d is None:
        raise ValueError("equivalent states have no distinguishing suffix")
    word: list[int] = []
    while d:
        for x in range(len(update.future[0])):
            pp = update.future[p][x]
            qq = update.future[q][x]
            if distances[pp * n + qq] == d - 1:
                word.append(x)
                p, q, d = pp, qq, d - 1
                break
        else:  # pragma: no cover - guarded by reverse BFS invariant
            raise AssertionError("future-distance relation is inconsistent")
    return tuple(word)


def _reachable(problem: PortfolioProblem, update_index: int):
    update = problem.updates[update_index]
    require_product_budget(
        [len(atom.transition) for atom in problem.atoms] + [len(update.history)],
        f"update {update.name} reachable product",
    )
    start = tuple(atom.initial for atom in problem.atoms) + (update.initial,)
    parents: dict[tuple[int, ...], tuple[tuple[int, ...], int] | None] = {start: None}
    depth = {start: 0}
    queue: deque[tuple[int, ...]] = deque([start])
    while queue:
        state = queue.popleft()
        atom_states = state[:-1]
        q = state[-1]
        for x in range(len(problem.history_symbols)):
            nxt = tuple(atom.transition[s][x]
                        for atom, s in zip(problem.atoms, atom_states))
            nxt += (update.history[q][x],)
            if nxt not in parents:
                parents[nxt] = (state, x)
                depth[nxt] = depth[state] + 1
                queue.append(nxt)
    return parents, depth


def _prefix(parents, state: tuple[int, ...]) -> tuple[int, ...]:
    word: list[int] = []
    while parents[state] is not None:
        state, symbol = parents[state]  # type: ignore[misc]
        word.append(symbol)
    return tuple(reversed(word))


def build_conflict_analysis(problem: PortfolioProblem) -> ConflictAnalysis:
    """Build the exact finite obstruction hypergraph.

    Each obligation is a bit mask of atoms that distinguish a pair of reachable
    histories whose target states are distinguishable by a common future.  A
    portfolio is safe exactly when it intersects every nonzero obligation.
    """
    best_by_mask: dict[int, Witness] = {}
    per_update_masks: list[set[int]] = []
    reachable_counts: list[int] = []
    conflict_pairs = 0
    for u_index, update in enumerate(problem.updates):
        parents, _ = _reachable(problem, u_index)
        states = sorted(parents)
        require_pair_budget(len(states), f"update {update.name} reachable")
        reachable_counts.append(len(states))
        n = len(update.history)
        distances = _future_distances(update.future, update.output)
        prefixes = {state: _prefix(parents, state) for state in states}
        update_masks: set[int] = set()
        for left, right in combinations(states, 2):
            p, q = left[-1], right[-1]
            distance = distances[p * n + q]
            if distance is None:
                continue
            conflict_pairs += 1
            mask = 0
            for i, (a, b) in enumerate(zip(left[:-1], right[:-1])):
                if a != b:
                    mask |= 1 << i
            h1, h2 = prefixes[left], prefixes[right]
            pp, qq = p, q
            if (len(h2), h2, right) < (len(h1), h1, left):
                h1, h2, pp, qq = h2, h1, q, p
            update_masks.add(mask)
            previous = best_by_mask.get(mask)
            # Event cost is the primary Witness.key component. Equal-cost
            # candidates still require the complete lexical comparison.
            if previous is not None and len(h1) + len(h2) + distance > previous.cost:
                continue
            witness = Witness(u_index, h1, h2, _suffix(update, pp, qq, distances),
                              mask, pp, qq)
            if previous is None or witness.key() < previous.key():
                best_by_mask[mask] = witness
        if 0 in update_masks:
            # The inclusion-minimal family is exactly {empty}: every nonempty
            # separator is a strict superset and therefore redundant.
            per_update_masks.append((0,))
        else:
            ordered_update = sorted(update_masks,
                                    key=lambda mask: (mask.bit_count(), mask))
            update_basis: list[int] = []
            for mask in ordered_update:
                if not any((smaller & mask) == smaller for smaller in update_basis):
                    update_basis.append(mask)
            per_update_masks.append(tuple(update_basis))

    # If an empty separator exists, the mathematical inclusion-minimal basis is
    # exactly {empty}.  Nonzero separators remain in all_witnesses for shortest
    # selected-portfolio diagnostics, but are not mislabeled as basis members.
    if 0 in best_by_mask:
        obligations = (0,)
    else:
        ordered = sorted(best_by_mask, key=lambda mask: (mask.bit_count(), mask))
        basis: list[int] = []
        for mask in ordered:
            if not any((smaller & mask) == smaller for smaller in basis):
                basis.append(mask)
        obligations = tuple(basis)
    return ConflictAnalysis(tuple(obligations),
                            {mask: best_by_mask[mask] for mask in obligations},
                            best_by_mask, tuple(per_update_masks),
                            tuple(reachable_counts), conflict_pairs)


def is_safe(mask: int, analysis: ConflictAnalysis) -> bool:
    return analysis.feasible and all(mask & obligation for obligation in analysis.obligations)


def shortest_failure(mask: int, analysis: ConflictAnalysis) -> Witness | None:
    candidates = [w for sep, w in analysis.all_witnesses.items() if not (mask & sep)]
    return min(candidates, key=Witness.key) if candidates else None


def greedy_portfolio(problem: PortfolioProblem, analysis: ConflictAnalysis,
                     obligations: tuple[int, ...] | None = None) -> int | None:
    if not analysis.feasible:
        return None
    remaining = set(obligations if obligations is not None else analysis.obligations)
    selected = 0
    while remaining:
        choices: list[tuple[Fraction, int, int, str]] = []
        for i, atom in enumerate(problem.atoms):
            bit = 1 << i
            if selected & bit:
                continue
            covered = sum(1 for obligation in remaining if obligation & bit)
            if covered:
                choices.append((Fraction(atom.cost, covered), atom.cost, i, atom.name))
        if not choices:
            return None
        _, _, i, _ = min(choices)
        selected |= 1 << i
        remaining = {obligation for obligation in remaining if not (selected & obligation)}
    return selected


def _packing_lower_bound(problem: PortfolioProblem, remaining: list[int]) -> int:
    """Valid weighted lower bound from greedily chosen disjoint obligations."""
    chosen: list[int] = []
    total = 0
    # Larger minimum costs first tends to tighten the bound, but any disjoint
    # collection is valid because no one atom can hit two disjoint masks.
    ranked = sorted(remaining,
                    key=lambda m: (min(problem.atoms[i].cost for i in range(len(problem.atoms))
                                      if m >> i & 1), -m.bit_count(), m),
                    reverse=True)
    union = 0
    for obligation in ranked:
        if obligation & union:
            continue
        chosen.append(obligation)
        union |= obligation
        total += min(problem.atoms[i].cost for i in range(len(problem.atoms))
                     if obligation >> i & 1)
    return total


def optimize_portfolio(problem: PortfolioProblem, analysis: ConflictAnalysis,
                       obligations: tuple[int, ...] | None = None) -> dict[str, Any]:
    """Exact positive-cost branch-and-bound weighted hitting set."""
    require_subset_budget(len(problem.atoms), "portfolio optimizer")
    if not analysis.feasible:
        return {"feasible": False, "selected_mask": None, "cost": None,
                "nodes": 0, "pruned": 0}
    obs = tuple(sorted(set(obligations if obligations is not None else analysis.obligations)))
    if not obs:
        return {"feasible": True, "selected_mask": 0, "cost": 0,
                "nodes": 1, "pruned": 0}
    greedy = greedy_portfolio(problem, analysis, obs)
    if greedy is None:
        return {"feasible": False, "selected_mask": None, "cost": None,
                "nodes": 0, "pruned": 0}
    best_mask = greedy
    best_cost = problem.cost(greedy)
    nodes = 0
    pruned = 0
    seen_prefix: dict[tuple[int, ...], tuple[int, int, int]] = {}

    def search(selected: int, cost: int, remaining: tuple[int, ...]) -> None:
        nonlocal best_mask, best_cost, nodes, pruned
        nodes += 1
        remaining = tuple(o for o in remaining if not (selected & o))
        if not remaining:
            key = (cost, selected.bit_count(), selected)
            best_key = (best_cost, best_mask.bit_count(), best_mask)
            if key < best_key:
                best_mask, best_cost = selected, cost
            return
        if cost >= best_cost:
            pruned += 1
            return
        state_key = tuple(sorted(remaining))
        prefix_key = (cost, selected.bit_count(), selected)
        previous = seen_prefix.get(state_key)
        if previous is not None and previous <= prefix_key:
            pruned += 1
            return
        seen_prefix[state_key] = prefix_key
        lower = _packing_lower_bound(problem, list(remaining))
        if cost + lower > best_cost:
            pruned += 1
            return
        obligation = min(remaining,
                         key=lambda o: (sum(1 for i in range(len(problem.atoms))
                                            if o >> i & 1), o))
        candidates = [i for i in range(len(problem.atoms)) if obligation >> i & 1]
        candidates.sort(key=lambda i: (
            Fraction(problem.atoms[i].cost, sum(1 for o in remaining if o >> i & 1)),
            problem.atoms[i].cost, -sum(1 for o in remaining if o >> i & 1),
            problem.atoms[i].name))
        for i in candidates:
            bit = 1 << i
            if selected & bit:
                continue
            search(selected | bit, cost + problem.atoms[i].cost, remaining)

    search(0, 0, obs)
    return {"feasible": True, "selected_mask": best_mask, "cost": best_cost,
            "nodes": nodes, "pruned": pruned}


def oracle_optimize(problem: PortfolioProblem, analysis: ConflictAnalysis,
                    obligations: tuple[int, ...] | None = None) -> tuple[int, int] | None:
    """Independent subset oracle used only for bounded validation."""
    require_subset_budget(len(problem.atoms), "portfolio oracle")
    if not analysis.feasible:
        return None
    obs = obligations if obligations is not None else analysis.obligations
    best: tuple[int, int, int] | None = None
    for mask in range(1 << len(problem.atoms)):
        if all(mask & obligation for obligation in obs):
            item = (problem.cost(mask), mask.bit_count(), mask)
            if best is None or item < best:
                best = item
    return None if best is None else (best[2], best[0])


def independent_union_baseline(problem: PortfolioProblem,
                               analysis: ConflictAnalysis) -> int | None:
    """Optimize each update separately and union the chosen atoms."""
    if not analysis.feasible:
        return None
    union = 0
    for u in range(len(problem.updates)):
        obs = analysis.update_obligations[u]
        if 0 in obs:
            return None
        result = optimize_portfolio(problem, analysis, obs)
        if not result["feasible"]:
            return None
        union |= int(result["selected_mask"])
    return union



def _representative_maps(problem: PortfolioProblem, selected_mask: int) -> list[dict[str, Any]]:
    """Construct deterministic migration representatives for a safe portfolio.

    Each entry lists every reachable selected-summary tuple for one update and a
    target state reached in that fiber.  Unreachable tuples are intentionally
    omitted: they impose no migration obligation at the boundary.
    """
    problem.cost(selected_mask)
    selected = [i for i in range(len(problem.atoms)) if selected_mask >> i & 1]
    result: list[dict[str, Any]] = []
    for update_index, update in enumerate(problem.updates):
        parents, _ = _reachable(problem, update_index)
        fibers: dict[tuple[int, ...], set[int]] = {}
        for state in parents:
            summary = tuple(state[i] for i in selected)
            fibers.setdefault(summary, set()).add(state[-1])
        entries = []
        for summary in sorted(fibers):
            entries.append({
                "summary_state": list(summary),
                "target_state": min(fibers[summary]),
            })
        result.append({"update": update.name, "fibers": entries})
    return result


def make_optimal_certificate(problem: PortfolioProblem, analysis: ConflictAnalysis,
                             selected_mask: int) -> dict[str, Any]:
    """Build a self-contained positive certificate for an optimality checker."""
    if not is_safe(selected_mask, analysis):
        raise ValueError("cannot certify an unsafe portfolio as optimal")
    return {
        "kind": "optimal_portfolio",
        "selected_mask": selected_mask,
        "selected_atoms": problem.selected_names(selected_mask),
        "cost": problem.cost(selected_mask),
        "obstruction_basis": list(analysis.obligations),
        "representatives": _representative_maps(problem, selected_mask),
    }


def make_unsafe_certificate(problem: PortfolioProblem, selected_mask: int,
                            witness: Witness) -> dict[str, Any]:
    """Build a self-contained replay certificate for one selected portfolio."""
    problem.cost(selected_mask)
    return {
        "kind": "unsafe_portfolio",
        "selected_mask": selected_mask,
        **witness.as_dict(problem),
    }

def analyze_selected(problem: PortfolioProblem, analysis: ConflictAnalysis,
                     mask: int) -> dict[str, Any]:
    problem.cost(mask)
    safe = is_safe(mask, analysis)
    answer: dict[str, Any] = {
        "selected_mask": mask,
        "selected_atoms": problem.selected_names(mask),
        "cost": problem.cost(mask),
        "safe": safe,
    }
    if not safe:
        witness = shortest_failure(mask, analysis)
        if witness is not None:
            answer["certificate"] = make_unsafe_certificate(problem, mask, witness)
    return answer
