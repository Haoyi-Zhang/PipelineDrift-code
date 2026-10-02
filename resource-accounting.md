# Resource accounting

## Checked environment and release preflight

The final prepackage release check used one worker on Debian GNU/Linux 13 (trixie),
CPython 3.13.5, with 0 bytes observed swap. Immediately before the
run it recorded 5,143,695,360 bytes available memory and 31,886,786,560 bytes
free disk. The wrapper requires Linux, CPython 3.10 or newer, at least 512 MiB
available memory, and at least 250 MiB free disk. It uses no network or
third-party Python package. macOS, Windows, PyPy, and other Python versions were
not checked and are not claimed supported.

The scientific runner sets a 3 GiB address-space limit, a 60-second child CPU
limit, and one-CPU affinity where the host exposes that interface. These are
bounded-run safeguards, not sandbox-security guarantees. A budget refusal is a
failed analysis and is never interpreted as safety, unsafety, feasibility, or
optimality.

## Regenerated portfolio campaign

`results/portfolio/summary.json` records:

- 20,480 finite catalogue problems and 98,304 portfolio masks;
- 7.240079079 CPU seconds and 7.241376879 wall seconds;
- 96,040 KiB maximum recorded process peak RSS;
- zero safety, optimizer, certificate, minimum-witness, or mutant
  catalogue-infeasibility-evidence disagreement.

The named campaign also contains 12 declarations, 571 one-cell monitor mutants,
256 fixed-seed generated problems, 2,348 generated-problem masks, and 79
one-at-a-time cost perturbations. The language report contains 1,272 transition,
output, initial-state, and empty-history checks. These counts support the finite
correctness claims; timings do not.

## Preserved single-summary regression

The eight legacy chunks cover 46,932 cases. Their recorded inner regions sum to
2.577352622 CPU seconds and 2.596182846 wall seconds, with 93,992 KiB maximum
process peak RSS. The 48-case saturated-counter grid recorded 0.000910101 CPU
seconds. These measurements exclude editing, source acquisition, TeX build, and
packaging and are not represented as whole-project resource use.

## Complete prepackage release check

`results/release-check.json` and `results/reproduction.json` record:

- 66 unit and command-line tests;
- 1,272 language checks;
- 46,932 legacy cases and 48 counter-family cases;
- 20,480 portfolio problems and 98,304 masks;
- 12 declarations and 571 mutations;
- 256 fixed-seed generated problems and 2,348 masks;
- 79 cost perturbations and one five-field TFX schema projection;
- 28 deterministic scientific-record comparisons;
- 32.264298760 seconds wrapper elapsed time;
- 31.464728750 seconds scientific-runner elapsed time;
- 31.022448 child CPU seconds;
- 101,152 KiB parent and 109,356 KiB maximum child peak RSS.

Fresh extraction runs are expected to report different timing, free-space,
available-memory, and RSS observations. Equality is required only for the
scientific records explicitly listed by `tools/reproduce.py`. These measurements
show closure for the shipped bounded campaign; they do not establish large-scale
throughput or industrial scalability.
