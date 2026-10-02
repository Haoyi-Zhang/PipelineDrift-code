# Benchmark overfitting and generalization boundary

## Scope

The artifact trains no predictive model and estimates no parameter from a
training set. Conventional model overfitting, held-out accuracy, calibration,
and train/test leakage are therefore not evaluation concepts for this work. The
relevant risks are hand-crafted benchmark bias, common implementation faults,
tuning examples to an expected answer, and extrapolating bounded finite checks
to unrestricted production systems.

## Implemented controls and exact assets

All items below are executable and have shipped inputs and results. None is a
claim of statistical representativeness.

1. **Fixed-seed differential problems.** `tools/random_differential.py` uses
   seed `20260915` to generate 256 small extensional finite problems. Exact
   inputs are in `results/random-differential/problems.jsonl`; per-problem
   outcomes are in `cases.csv`; `summary.json` reports 2,348 checked portfolios,
   zero safety disagreement, zero optimizer disagreement, and zero certificate
   failure. The generator is deterministic so a disagreement is a reproducible
   fault, not a sample to average away.
2. **Independent finite checks.** The producer is compared with the separately
   implemented product-state safety checker and exhaustive subset oracle. The
   language reference interpreter uses its own typed-set equality definition and
   detects the historical Python `False == 0` / `True == 1` aliasing mutation.
3. **Mutation and tampering checks.** The named-declaration campaign applies one
   cyclic transition redirection or one output flip per update cell, deduplicates
   by the full extensional update table, and independently validates every
   certificate. A claim that the whole catalogue is infeasible additionally
   requires the all-candidate mask to fail and a replayable zero-separator
   certificate.
4. **Cost sensitivity.** `tools/cost_sensitivity.py` applies 79 deterministic
   one-at-a-time integer cost perturbations to the eleven initially feasible
   declarations. Inputs and outcomes are in `results/cost-sensitivity/`. One
   perturbation changes the selected optimum mask; 34 change the numeric optimum
   cost; no optimality certificate fails. These data show that costs are a
   policy input, not measured universal storage prices.
5. **Public-source projection.** `tools/tfx_projection.py` consumes the pinned
   TFX penguin schema in `external/tfx-penguin/` and projects only its five
   `min_fraction=1.0`, `min_count=1` presence constraints into Boolean finite
   batch-summary events. The exact generated declaration, mapping, result, and
   certificate are in `results/tfx-projection/`. This is a provenance check for
   a narrow subset, not a general TFDV protobuf parser or TFX runtime adapter.
6. **Negative controls.** The marginal-only declaration retains every supplied
   marginal summary yet remains infeasible for the same two-disagreement target
   used by the joint-summary control. Current-output-only and literal-state
   controls exercise opposite errors in the legacy finite regression.

## What these controls do not establish

They do not establish a population-level generalization rate, production
throughput, industrial representativeness, complete TFX/TFDV compatibility,
real storage savings, or a probability distribution over software changes. The
finite catalogues, random problems, and mutations are all fault-detection
instruments for the stated deterministic semantics.

## Reproduction

From the standalone artifact root, run:

```bash
PYTHONDONTWRITEBYTECODE=1 \
python tools/release_check.py \
  --output ../release-check
```

The output directory must not already exist. The checked release path is Linux
with CPython 3.10 or newer, one worker, at least 512 MiB available memory and
250 MiB free disk, and no network or third-party Python package. macOS, Windows,
PyPy, and other Python versions were not tested by the recorded release run.
