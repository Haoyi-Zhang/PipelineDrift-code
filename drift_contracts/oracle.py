"""Small exact oracle: enumerate words and all state-migration functions.

No graph-search, reachability, equivalence, or certificate-search imports.
Its explicit exponential limits prevent an accidental large run.
"""
from __future__ import annotations
from itertools import product
from .model import Contract


def words(alphabet: int, bound: int):
    for length in range(bound+1):
        yield from product(range(alphabet), repeat=length)


def _run(table, state, word):
    for letter in word:
        state = table[state][letter]
    return state


def oracle(c: Contract) -> dict:
    nr, nq = len(c.retain), len(c.history)
    ah, af = len(c.retain[0]), len(c.future[0])
    hb, fb = nr*nq-1, nq*nq-1
    hw_count = sum(ah**k for k in range(hb+1))
    fw_count = sum(af**k for k in range(fb+1))
    if hw_count > 4096 or fw_count > 4096 or nq**nr > 4096 or hw_count**2*fw_count > 4_000_000:
        raise ValueError("oracle's explicit enumeration envelope exceeded")
    hw, fw = tuple(words(ah, hb)), tuple(words(af, fb))
    observations = [[c.output[_run(c.future, q, w)] for w in fw] for q in range(nq)]
    hp = [(w, _run(c.retain, c.initial_retain, w), _run(c.history, c.initial_target, w)) for w in hw]
    maps = 0
    for mapping in product(range(nq), repeat=nr):
        if all(observations[mapping[r]] == observations[q] for _, r, q in hp):
            maps += 1
    # Exhaustive words, rather than shortest paths, independently check minimal cost.
    distinguishing = {}
    for p in range(nq):
        for q in range(nq):
            differing = [len(w) for k, w in enumerate(fw) if observations[p][k] != observations[q][k]]
            distinguishing[p, q] = min(differing) if differing else None
    minimum = None
    for i, (u, r, p) in enumerate(hp):
        for v, s, q in hp[i+1:]:
            distance = distinguishing[p, q]
            if r == s and distance is not None:
                cost = len(u)+len(v)+distance
                minimum = cost if minimum is None else min(minimum, cost)
    return {"admissible": bool(maps), "migration_maps": maps,
            "minimum_cost": minimum, "history_words": len(hw), "future_words": len(fw)}
