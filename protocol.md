# Frozen evaluation protocol

## 1. Claim under test

For a bounded deterministic declaration, compile candidate retention atoms and
planned monitor updates to finite machines. Decide whether a selected atom set
preserves every update's replay behavior for all histories and all future
records; synthesize the minimum positive-cost safe set; and explain failure with
a replayable paired-history/common-future certificate. Evaluation checks this
finite implementation claim. It does not test production prevalence,
throughput, model accuracy, probabilistic drift detection, or user outcomes.

## 2. Surface semantics and failure policy

Each declaration layer has an explicit allowed-field set. Every atom and update
must declare an integer `initial` state in range; unknown or misspelled semantic
keys are rejected. Boolean values are not accepted as integer states or masks.
`eq`, `ne`, and `in` use the same exact typed equality, so `false` is distinct
from `0` and `true` from `1`. Repeated members in `required` are idempotent set
members; they are never added as numeric bit masks.

Every primitive checks record, state, and transition dimensions before table
allocation. Product-state, state-pair, pair-transition, and exhaustive-subset routines apply
separate budgets. Exceeding a budget is an analysis refusal and must not be
reported as safety, unsafety, infeasibility, or optimality.

The supported window is a suffix of Boolean predicate values only. The artifact
does not implement a general finite-domain `D^{<=w}` window.

## 3. Complete finite catalogues

### Unary complete catalogue

Use one historical and one future symbol, **three two-state unary atoms** with
costs one, two, and three, and one two-state update. Enumerate all atom tables,
historical target tables, future target tables, and binary output vectors:
`4^6 = 4,096` labeled catalogues. Check all eight masks: 32,768 judgments.

### Fixed binary two-state subspace

Use two historical and two future symbols, **two fixed-two-state atoms**, and one
two-state update. Enumerate all 16 tables for each atom and the historical target
and four predeclared future/output variants: `16^3 * 4 = 16,384` catalogues.
Check all four masks: 65,536 judgments. This is complete only for the stated
four-variant subspace.

For every problem/mask, compare separator hitting with the independently
implemented product-state safety checker. For every feasible catalogue, compare
the branch-and-bound optimum with exhaustive subset enumeration under
`(total cost, atom count, numeric mask)`. In the unary catalogue, direct bounded
word enumeration also checks globally minimum certificate length.

## 4. Named declarations and controls

The 12 declarations exercise schema rename/deletion, a label-field rename,
threshold families, class/slice coverage, missingness streaks, Boolean rolling
patterns, label disagreement, a fixed-target marginal/joint comparison, and a
weighted greedy trap. Eleven are initially feasible. The marginal-only
catalogue and the joint catalogue use the same two-disagreement target; the
latter changes only by adding one joint disagreement-count atom.

Baselines are: per-update exact optima followed by union, deterministic weighted
greedy, and the all-candidate mask. The all-candidate mask is an explicit
catalogue-feasibility test, not a presumed safe fallback.

## 5. Independent declaration check

`tools/check_language.py` compares the compiler with
`drift_contracts/dsl_reference.py`, which has its own expression evaluator,
typed set definition, state construction, transitions, and outputs. It checks
all atom transitions, monitor history/future transitions, output cells, every
explicit atom/update initial state, and the empty-history state/output. The
shipped report contains 528 atom transitions, 506 monitor transitions, 92
outputs, 73 initial states, and 73 empty-history checks: 1,272 checks total.

## 6. Mutation protocol

For each initially feasible declaration, mutate one update at a time. For each
historical or future transition cell, redirect the destination **once** to
`(old + 1) mod n`; in the shipped two-state updates this flips the destination.
For each output cell, flip the bit. Deduplicate by the complete extensional
representation `(initial, history table, future table, output vector)` for all
updates, not by mutation coordinates.

For every retained mutant, recompute safety, feasibility, and the exact optimum.
If the old optimum is unsafe, replay its certificate. If the whole catalogue is
reported infeasible, independently check the all-candidate mask and require a
replayable zero-separator certificate. Failure of the old optimum alone is not
catalogue-infeasibility evidence.

## 7. Additional fault-detection controls

### Fixed-seed generated problems

`tools/random_differential.py` uses seed `20260915` to generate 256 small finite
extensional problems. Exact inputs are written to
`results/random-differential/problems.jsonl`. All 2,348 selected masks are
compared with the independent safety checker, and every optimizer result is
compared with exhaustive safe-subset enumeration. This is deterministic fault
detection, not statistical generalization.

### Cost sensitivity

`tools/cost_sensitivity.py` applies every distinct one-at-a-time `cost-1` (when
positive) and `cost+1` perturbation to the eleven feasible declarations. It
checks 79 cost vectors, re-optimizes without changing semantics, and verifies
each optimum. The experiment documents policy sensitivity; it does not validate
any physical storage-cost model.

### Public TFX-schema projection

`tools/tfx_projection.py` consumes the exact pinned TFX penguin schema at commit
`cd99075bfad794a3ea9df49ee77f9c06578f895d`. It projects only the five feature
presence constraints with `min_fraction=1.0` and `min_count=1` to Boolean
batch-summary events. Exact source, license, generated declaration, mapping,
result, and certificate are shipped. No general protobuf, TFDV, TFX runtime, or
production-integration claim is made.

## 8. Certificate and CLI contract

An optimal certificate contains exactly the selected mask/names, cost,
mathematical inclusion-minimal obstruction basis, and reachable-fiber
representative maps. If any empty separator exists, that basis is exactly
`{empty}`; nonempty masks remain only as diagnostic witnesses, not basis members.

An unsafe certificate binds the selected mask, update, two histories, common
future, target endpoints, separator, and event cost. The verifier replays all
machines from explicit initial states. A CLI diagnosis that is scientifically
negative but has a valid certificate exits successfully. Any main or selected
certificate failure, internal mismatch, parse error, or resource refusal exits
nonzero.

## 9. Legacy regression

The preserved single-summary regression contains 46,932 total deterministic
specifications and a 48-point saturated-counter family. These are retained
regressions, not separate novelty claims.

## 10. Reproduction environment

The recorded supported path is Linux with CPython 3.10 or newer, one worker, no
network, no third-party Python package, at least 512 MiB available memory and
250 MiB free disk. The runner uses a 3 GiB address-space limit and a 60-second
child CPU limit. The historical Debian/CPython 3.13.5 release ran 66 tests;
the current Linux reproduction record lists 16 completed commands, 72 passed
tests, and 28 matched deterministic records. Its recorded wall time is
10.974 seconds, child CPU time is 10.547 seconds, and maximum child RSS is
42,068 KiB. Historical Debian measurements are retained separately.

The reported Windows/CPython 3.12.14 checks exercised the 72-test suite,
paper-side rendering tests, typed JSON operations, and finite result subsets.
They did not run the complete resource-limited Linux wrapper. The Linux path
above remains the documented complete reproduction procedure.

Run from the standalone root with a new output directory:

```bash
PYTHONDONTWRITEBYTECODE=1 \
python tools/release_check.py \
  --output ../release-check
```

Success means deterministic reproduction of the shipped bounded records. It is
not a mechanized general proof, production validation, or independent review.
