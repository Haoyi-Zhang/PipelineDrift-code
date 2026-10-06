# Declarative Drift Contracts

This standalone artifact implements **cost-aware retention-portfolio synthesis**
for bounded, deterministic, design-time monitor evolution. A declaration gives
finite historical/future record schemas, candidate summary atoms with positive
integer costs, explicit initial states, and a planned family of monitor updates.
The analyzer either returns a minimum-cost replay-safe portfolio, returns a
paired-history/common-future certificate for an unsafe selected portfolio, or
proves that the entire candidate catalogue is infeasible with a replayable
zero-separator certificate.

The implementation uses only the Python standard library. It performs no model
training or inference, network access, private-data access, GPU execution, or
production deployment.

## Supported release environment

The recorded release check was run on Linux with CPython 3.10 or newer, one
worker, at least 512 MiB available memory and 250 MiB free disk. The runner
applies a 3 GiB address-space limit and a 60-second child CPU limit. macOS,
Windows, PyPy, and other Python versions were not tested in that release;
no cross-platform release claim is made. A later local Windows check with
bundled CPython 3.12.14 passed 72 artifact tests, including six regressions for
recursively typed JSON containers. The repair keeps objects distinct from
arrays of key/value pairs, including in schema domains and finite-value
primitives. An owned finite replay retained the shipped catalogue, mutation,
migration and counter outcomes; separate language, generated-problem, cost and
source-projection checks also retained their scientific results. These local
checks did not run the Linux-only release wrapper or replace its measurements.

## Quick start

From the extracted `declarative-drift-contracts/` directory:

```sh
PYTHONDONTWRITEBYTECODE=1 \
python -m unittest discover -s tests -v

PYTHONDONTWRITEBYTECODE=1 \
python -m drift_contracts.portfolio_cli \
  declarations/threshold-family.json

PYTHONDONTWRITEBYTECODE=1 \
python -m drift_contracts.portfolio_cli \
  declarations/marginals-only-infeasible.json
```

The threshold declaration has joint optimum cost 2 versus per-update-union cost
5. The marginal-only declaration uses the same two-disagreement target as its
joint-summary control and remains infeasible even when all three marginal atoms
are retained.

## Complete release check

The output directory must not already exist:

```sh
PYTHONDONTWRITEBYTECODE=1 \
python tools/release_check.py \
  --output ../release-check
```

`release_check.py` invokes the complete deterministic reproduction and writes a
machine-readable environment/result report. The reproduction runs the unit and
CLI suite, declaration-language comparison, legacy 46,932-case regression,
48-point counter family, exact portfolio catalogues, named declarations and
mutations, fixed-seed random differential campaign, one-at-a-time cost
sensitivity, and the pinned TFX-schema projection. It then compares every
claim-critical deterministic record with the shipped record. Fresh timing and
peak-memory values are recorded but not equality criteria.

A successful run means that the shipped bounded calculations reproduced. It is
not a proof-assistant result, full TFX/TFDV integration, production validation,
or independent peer review.

The prepared `.github/workflows/scientific-checks.yml` runs this same complete
release path from a flat artifact-repository root on Ubuntu 24.04 and CPython
3.12. It retains the scientific failure gates, bounds the whole command to
12 minutes (plus a 10-second termination grace), limits each process to 3 GiB
address space, and uploads available raw output even on failure. Preparation of
this workflow does not constitute a hosted execution result.

## Reported bounded evidence

- 20,480 complete finite portfolio problems and 98,304 candidate masks;
- zero safety, optimizer, certificate, or complete-unary minimum-witness mismatch;
- 12 declarations: 11 initially feasible and one all-candidate infeasible;
- 571 one-cell monitor mutants: 188 invalidate the old optimum, 172 make the
  whole catalogue infeasible, 15 increase and 41 decrease feasible optimum cost;
- every mutant infeasibility claim independently checks the all-candidate mask
  and replays a zero-separator certificate;
- 1,272 compiler checks across transitions, outputs, explicit initial states,
  and empty histories, with no mismatch;
- 256 fixed-seed generated problems and 2,348 selected masks, with zero
  differential or certificate mismatch;
- 79 deterministic cost perturbations over the eleven feasible declarations;
  one changes the selected optimum mask and none invalidates a certificate;
- a pinned public TFX penguin schema projection of five required-presence
  constraints, compiled and independently certified within the narrow subset;
- the preserved 46,932-case single-summary regression, with no oracle mismatch.

These counts are exact for the shipped finite inputs. They are not estimates of
production prevalence, throughput, storage savings, or learned-model accuracy.

## Repository map

- `drift_contracts/portfolio_dsl.py` - strict parser and finite compiler;
- `drift_contracts/dsl_reference.py` - independent typed-set source semantics;
- `drift_contracts/limits.py` - pre-allocation state, transition, product, pair, pair-transition,
  and subset budgets;
- `drift_contracts/portfolio.py` - reachability, obstruction extraction, exact
  optimization, and shortest certificate production;
- `drift_contracts/portfolio_verify.py` - independent safety, optimality,
  representative-map, and unsafe-certificate checks;
- `declarations/` - 12 bounded pipeline-evolution declarations;
- `external/tfx-penguin/` - exact pinned public schema, source record, and
  Apache-2.0 license;
- `tools/random_differential.py` - fixed-seed generated finite inputs and oracle;
- `tools/cost_sensitivity.py` - deterministic one-at-a-time cost perturbations;
- `tools/tfx_projection.py` - narrow required-presence projection;
- `tools/reproduce.py` - full deterministic scientific rerun and comparison;
- `tools/release_check.py` - supported-environment wrapper and final report;
- `results/` - exact inputs, raw outcomes, certificates, and summaries;
- `claim_evidence_ledger.csv` - claim-to-proof/check/result mapping;
- `external_resources.csv` - source, license/access, and integration inventory.

## Trust boundary

The written theorems are not proof-assistant-checked. Producer and verifier use
different algorithms, and the reference interpreter uses an independent typed
set definition, but all code remains one artifact and one internal research
process. The public-schema projection is intentionally limited to five explicit
presence constraints. Human authors must review the mathematics, implementation,
source characterizations, authorship responsibilities, and current venue policy
before external use.

## License and disclosure

Project code and original documentation are under the MIT License in `LICENSE`.
The pinned TFX schema is redistributed under Apache License 2.0 with its source
record and license. Scholarly papers are cited but not redistributed.
