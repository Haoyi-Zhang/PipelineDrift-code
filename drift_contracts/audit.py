"""Exact migration admission and globally shortest paired-history witnesses.

Uses ordinary product reachability and distinguishability of finite automata.
This implementation is not a mechanized proof of the general theorems.
"""
from __future__ import annotations
from collections import deque
from functools import lru_cache
from itertools import combinations
from typing import Any
from .model import Contract


@lru_cache(maxsize=128)
def future_distances(future: tuple[tuple[int, ...], ...], output: tuple[int, ...]) -> tuple[int | None, ...]:
    """Distance to unequal verdicts, indexed by ordered target-state pairs."""
    n, a = len(future), len(future[0])
    reverse: list[list[int]] = [[] for _ in range(n*n)]
    for p in range(n):
        for q in range(n):
            for x in range(a):
                reverse[future[p][x]*n + future[q][x]].append(p*n + q)
    distances: list[int | None] = [None] * (n*n)
    queue: deque[int] = deque()
    for p in range(n):
        for q in range(n):
            if output[p] != output[q]:
                distances[p*n+q] = 0
                queue.append(p*n+q)
    while queue:
        dest = queue.popleft()
        d = distances[dest]
        assert d is not None
        for source in reverse[dest]:
            if distances[source] is None:
                distances[source] = d+1
                queue.append(source)
    return tuple(distances)


def _suffix(c: Contract, p: int, q: int, distances: tuple[int | None, ...]) -> tuple[int, ...]:
    n = len(c.history)
    d = distances[p*n+q]
    if d is None:
        raise ValueError("equivalent states have no distinguishing suffix")
    result = []
    while d:
        for x in range(len(c.future[0])):
            pp, qq = c.future[p][x], c.future[q][x]
            if distances[pp*n+qq] == d-1:
                result.append(x)
                p, q, d = pp, qq, d-1
                break
        else:
            raise AssertionError("inconsistent reverse distances")
    return tuple(result)


def _reachable(c: Contract):
    start = (c.initial_retain, c.initial_target)
    parents: dict[tuple[int, int], tuple[tuple[int, int], int] | None] = {start: None}
    depth = {start: 0}
    queue = deque([start])
    while queue:
        r, q = queue.popleft()
        for x in range(len(c.retain[0])):
            target = c.retain[r][x], c.history[q][x]
            if target not in parents:
                parents[target] = ((r, q), x)
                depth[target] = depth[r, q]+1
                queue.append(target)
    return parents, depth


def _prefix(parents, node: tuple[int, int]) -> tuple[int, ...]:
    word = []
    while parents[node] is not None:
        node, x = parents[node]
        word.append(x)
    return tuple(reversed(word))


def analyze(c: Contract) -> dict[str, Any]:
    parents, depth = _reachable(c)
    n = len(c.history)
    d = future_distances(c.future, c.output)
    fibers: dict[int, list[int]] = {}
    for r, q in sorted(parents):
        fibers.setdefault(r, []).append(q)
    best = None
    current_only = True
    state_equality = True
    for r, qs in fibers.items():
        if len(qs) > 1:
            state_equality = False
        if len({c.output[q] for q in qs}) > 1:
            current_only = False
        for p, q in combinations(qs, 2):
            tail_length = d[p*n+q]
            if tail_length is None:
                continue
            h1, h2 = _prefix(parents, (r, p)), _prefix(parents, (r, q))
            if (len(h2), h2) < (len(h1), h1):
                h1, h2, p, q = h2, h1, q, p
            tail = _suffix(c, p, q, d)
            cost = depth[r, p]+depth[r, q]+tail_length
            key = (cost, len(h1), h1, len(h2), h2, tail, r)
            if best is None or key < best[0]:
                best = (key, dict(history_left=list(h1), history_right=list(h2),
                                  suffix=list(tail), retained_state=r,
                                  target_left=p, target_right=q, cost=cost))
    answer: dict[str, Any] = {
        "admissible": best is None,
        "reachable_pairs": len(parents),
        "current_only_admissible": current_only,
        "state_equality_admissible": state_equality,
    }
    if best is not None:
        answer["certificate"] = {"kind": "collision", **best[1]}
        return answer
    mapping: list[int | None] = [None] * len(c.retain)
    for r, qs in fibers.items():
        mapping[r] = min(qs)
    answer["certificate"] = {
        "kind": "migration",
        "map": mapping,
        "reachable": [list(p) for p in sorted(parents)],
        "future_relation": [[p, q] for p in range(n) for q in range(n) if d[p*n+q] is None],
    }
    return answer
