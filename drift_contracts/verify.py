"""Certificate checking without importing the search procedure or its cache."""
from __future__ import annotations
from typing import Any
from .model import Contract, run


def _pairs(value: Any, n: int, m: int) -> set[tuple[int, int]]:
    if not isinstance(value, list):
        raise ValueError("relation must be a list")
    ans = set()
    for item in value:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError("relation entry must have two states")
        p, q = item
        if type(p) is not int or type(q) is not int or not 0 <= p < n or not 0 <= q < m:
            raise ValueError("relation state out of range")
        ans.add((p, q))
    if len(ans) != len(value):
        raise ValueError("duplicate relation entries")
    return ans


def verify(c: Contract, certificate: dict[str, Any]) -> bool:
    """Returns False for malformed or false certificates.

    Collision validity is checked; minimality is a separate algorithmic claim.
    """
    try:
        if not isinstance(certificate, dict):
            return False
        kind = certificate.get("kind")
        if kind == "collision":
            required = {"kind", "history_left", "history_right", "suffix", "retained_state",
                        "target_left", "target_right", "cost"}
            if set(certificate) != required:
                return False
            a, b, tail = (certificate[k] for k in ("history_left", "history_right", "suffix"))
            if any(not isinstance(w, list) for w in (a, b, tail)):
                return False
            r1, r2 = run(c.retain, c.initial_retain, a), run(c.retain, c.initial_retain, b)
            p, q = run(c.history, c.initial_target, a), run(c.history, c.initial_target, b)
            fields = [certificate[k] for k in ("retained_state", "target_left", "target_right", "cost")]
            if any(type(x) is not int for x in fields):
                return False
            if (r1, p, q, len(a)+len(b)+len(tail)) != tuple(fields) or r1 != r2:
                return False
            return c.output[run(c.future, p, tail)] != c.output[run(c.future, q, tail)]
        if kind != "migration" or set(certificate) != {"kind", "map", "reachable", "future_relation"}:
            return False
        nr, nq = len(c.retain), len(c.history)
        mapping = certificate["map"]
        if not isinstance(mapping, list) or len(mapping) != nr:
            return False
        if any(q is not None and (type(q) is not int or not 0 <= q < nq) for q in mapping):
            return False
        reach = _pairs(certificate["reachable"], nr, nq)
        relation = _pairs(certificate["future_relation"], nq, nq)
        if (c.initial_retain, c.initial_target) not in reach:
            return False
        for r, q in reach:
            if mapping[r] is None or (mapping[r], q) not in relation:
                return False
            for x in range(len(c.retain[0])):
                if (c.retain[r][x], c.history[q][x]) not in reach:
                    return False
        for p, q in relation:
            if c.output[p] != c.output[q]:
                return False
            for x in range(len(c.future[0])):
                if (c.future[p][x], c.future[q][x]) not in relation:
                    return False
        return True
    except (ValueError, TypeError, KeyError, IndexError):
        return False
