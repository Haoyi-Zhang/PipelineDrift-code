"""Deterministic case selection and original, source-inspired finite examples."""
from __future__ import annotations
from itertools import product
from .model import Contract


def decode_table(n: int, alphabet: int, code: int):
    digits = [(code // (n**i)) % n for i in range(n*alphabet)]
    return tuple(tuple(digits[r*alphabet:(r+1)*alphabet]) for r in range(n))


def parameters():
    """All unary R<=2,Q<=3 and all binary R<=2,Q<=2 specifications."""
    case = 0
    for alphabet, target_counts in [(1, (1, 2, 3)), (2, (1, 2))]:
        for nr in (1, 2):
            for nq in target_counts:
                for rc in range(nr**(nr*alphabet)):
                    for hc in range(nq**(nq*alphabet)):
                        for fc in range(nq**(nq*alphabet)):
                            for oc in range(2**nq):
                                yield case, alphabet, nr, nq, rc, hc, fc, oc
                                case += 1


def from_parameters(row):
    _, alphabet, nr, nq, rc, hc, fc, oc = row
    return Contract(decode_table(nr, alphabet, rc), decode_table(nq, alphabet, hc),
                    decode_table(nq, alphabet, fc), tuple((oc >> q) & 1 for q in range(nq)))


def named_examples():
    # '0' and '1' are finite input cells, not learned predictions.
    examples = []
    def add(identifier, description, c, expected, symbols, source, extra=None):
        data = dict(case=identifier, description=description, input_cells=symbols,
                    motivation_source=source, provenance="Original constructed finite example; not an upstream bug or workload.",
                    expected_admissible=expected, contract=c.to_dict())
        if extra:
            data.update(extra)
        examples.append(data)
    s = ((1, 2), (1, 2), (1, 2))
    add("case-a", "A lossless schema rename retains the last finite quality bin.",
        Contract(s, s, s, (0, 0, 1)), True, ["normal", "low"], "Overton, Section 2.1")
    add("case-b", "Deleting the field used by the last-batch missingness contract loses exact replay information.",
        Contract(((1,1),(1,1)), ((0,1),(0,1)), ((0,1),(0,1)), (0,1)), False,
        ["present", "missing"], "Data Validation for Machine Learning, schema constraints")
    batches = [[[1,1],[-1,-1]], [[1,-1],[-1,1]]]
    marginals = [[[sum(row[j] == label for row in batch) for label in (-1,0,1)]
                  for j in (0,1)] for batch in batches]
    conflicts = [sum(a != 0 and b != 0 and a != b for a,b in batch) for batch in batches]
    assert marginals[0] == marginals[1] and conflicts == [0,2]
    add("case-c", "Identical per-label-function marginals do not determine joint disagreement.",
        Contract(((1,1),(1,1)), ((0,1),(0,1)), ((0,1),(0,1)), (0,1)), False,
        ["aligned batch", "disagreeing batch"], "Overton, Section 2.2 (conflicting supervision)",
        {"raw_batches": batches, "per_function_histograms": marginals, "disagreement_counts": conflicts,
         "label_alphabet": {"negative": -1, "abstain": 0, "positive": 1}})
    add("case-d", "Historical states have equal current verdicts, but changed future observations distinguish them.",
        Contract(((1,1),(1,1)), ((0,1),(0,1),(0,1)), ((0,0),(2,1),(2,2)), (0,0,1)),
        False, ["cell zero", "cell one"], "Constructed two-epoch negative control")
    add("case-e", "Distinct replay states with identical future behavior need not be stored separately.",
        Contract(((1,1),(1,1)), ((0,1),(0,1),(0,1)), ((2,0),(2,0),(2,2)), (0,0,1)),
        True, ["cell zero", "cell one"], "Constructed state-equality negative control")
    def streak(cap):
        return tuple((0, min(s+1, cap)) for s in range(cap+1))
    add("case-f", "Increasing a consecutive-low threshold beyond an old saturated counter is not exactly recoverable.",
        Contract(streak(2), streak(3), streak(3), (0,0,0,1)), False,
        ["normal", "low"], "Constructed bounded temporal drift predicate")
    add("case-g", "A more detailed retained counter supports the lower-threshold replay target.",
        Contract(streak(3), streak(2), streak(2), (0,0,1)), True,
        ["normal", "low"], "Constructed bounded temporal drift predicate")
    add("case-h", "An exact migration exists, but resetting every migrated state to the initial state is incorrect.",
        Contract(streak(2), streak(2), streak(2), (0,0,1)), True,
        ["normal", "low"], "Carwehl et al., Section III-E (state continuity motivation)",
        {"deliberately_incorrect_reset_map": [0,0,0], "reset_counterexample_history": [1],
         "reset_counterexample_suffix": [1]})
    return examples
