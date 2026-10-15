# Declarative Drift Contracts

This artifact synthesizes minimum-cost replay-safe retention portfolios for
bounded, deterministic, design-time monitor evolution. Inputs declare finite
historical/future schemas, positive-cost summary atoms, explicit initial states
and planned monitor updates. Results include a checked optimum, an unsafe
paired-history/common-future certificate, or an all-candidate infeasibility
certificate. It uses only the Python standard library and needs no network,
training, GPU or private data.

## Environment and quick start

Run from the artifact root with CPython 3.10 or newer; no installation is needed:

```sh
python -B -m unittest discover -s tests -v
python -B -m drift_contracts.portfolio_cli declarations/threshold-family.json
python -B -m drift_contracts.portfolio_cli declarations/marginals-only-infeasible.json
python -B tests/regression_shortcuts.py -v
```

The threshold example has joint optimum cost 2 versus per-update-union cost 5.
The marginal-only declaration is infeasible even with all three atoms. A negative
diagnosis exits successfully when its certificate verifies; parse errors,
resource refusals and failed evidence exit nonzero. CLI output is JSON on stdout.
The explicit shortcut regression is separate from the retained 72-test receipt;
it checks lexical ties, typed histogram/window fixtures and rejection/cap cases.

The complete release wrapper is validated on Linux/CPython, one worker, with at
least 512 MiB available memory and 250 MiB free disk. It imposes a 3 GiB address
space and a 60-second child CPU limit. Windows/CPython 3.12.14 passed the 72-test
suite and selected finite checks, but not the Linux resource-limited wrapper.
macOS and PyPy have no recorded release validation. See `protocol.md` for exact
semantics, budgets and environment scope.

## Reproduction and retained results

On Linux, choose a nonexistent output directory outside the artifact:

```sh
python -B tools/release_check.py --output ../release-check
```

The wrapper runs `tools/reproduce.py`: unit/CLI tests, declaration-language
checks, the legacy 46,932 cases, counter family, finite portfolio catalogues,
named declarations/mutations, fixed-seed differential cases, cost sensitivity
and the pinned TFX-schema projection. It compares claim-critical deterministic
records with `results/`; timing and peak-memory observations may differ. It
does not overwrite the retained inputs or results.

`results/` retains raw inputs, CSV outcomes, certificates and summaries;
`results/current/` retains a later complete reproduction with its command logs.
Both are provenance-bearing records, not interchangeable timing observations.
`protocol.md` defines the finite denominators and negative controls;
`resource-accounting.md` describes the historical measurements.
`.github/workflows/scientific-checks.yml` runs the Linux release path and the
separate shortcut regression, retaining available outputs even after failure.

## Inputs and implementation

- `declarations/`: 12 bounded pipeline-evolution inputs (11 initially feasible).
- `drift_contracts/portfolio_dsl.py` and `dsl_reference.py`: strict finite compiler
  and separately implemented typed-set source semantics.
- `drift_contracts/portfolio.py` and `portfolio_verify.py`: analysis, optimization,
  certificate production and checking; `limits.py` enforces allocation budgets.
- `examples/` and `python -B -m drift_contracts CASE.json`: preserved single-summary
  interface used by the legacy regressions.
- `tools/`: campaign drivers, result reconciliation and source projection.
- `proofs/`, `language.md`: mathematical arguments and declaration semantics.
- `claim_evidence_ledger.csv`, `external_resources.csv`, `source-notes.md`:
  claim/result links, provenance and integration boundaries.

The TFX example consumes only five required-presence constraints from the pinned
public penguin schema in `external/tfx-penguin/`. Its source, license, projection
map, generated declaration and certificate are retained. It is not a TFX/TFDV
runtime integration or a raw-batch adapter.

## Conditions and license

The bounded written theorems are not proof-assistant-checked. Producer, verifier
and reference interpreter use different algorithms within one artifact and
research process. Finite reproduction is not production validation, independent
peer review, a throughput claim or a result about learned-model accuracy.

Project code and original documentation use the MIT `LICENSE`. The pinned TFX
schema retains its Apache-2.0 license and source record. Scholarly papers are
cited, not redistributed.
