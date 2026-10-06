# Source and novelty notes

## Historical project lineage

Overton provides the motivating software-system setting: machine-learned
products expose schemas, supervision, slices, and monitoring as declarations
that evolve with the product.  Its paper does **not** prove that a retained
summary can initialize an arbitrary later monitor, formulate a minimum-cost
retention portfolio, or produce replay certificates.  This project reuses the
problem setting and vocabulary at a high level, not Overton code, data, or a
claimed collaboration.

## Strongest close work

DynSRV directly studies dynamically updated stream properties and makes missing
history a first-class concern.  Its definitions and theorem characterize when
dynamic updates can avoid deferred values under three history-storage policies.
Therefore this project does not claim to discover that monitor updates can need
past information.  The retained delta is narrower: before deployment, choose a
minimum-cost subset from an explicitly declared finite catalogue of summary
machines for a *family* of planned updates; identify a zero-separator catalogue
failure; and emit a shortest replay certificate for an unsafe selection.

Carwehl et al. adapt runtime-verification components when requirements change,
with attention to current observer state and pending events.  Adaptive runtime
verification changes monitoring configuration under resource/context shifts.
Retroactive monitoring evaluates new or parameterized properties against stored
history or indexes.  These are direct neighbors but use different retained
information, timing, or objectives.  Multi-property temporal monitoring shares
work across simultaneous properties and supplies an optimization analogy, not a
retention result.

## Mathematical foundations stated as foundations

Future equivalence and distinguishing continuations are classical sequential-
machine ideas associated with Moore/Myhill/Nerode and automata minimization.
Weighted hitting set and greedy set-cover behavior are classical.  The paper's
novelty claim is not these ingredients individually.  It is the software-
engineering formulation and composition: finite pipeline declarations compile
to summary/update machines; history-pair distinctions become a costed retention
contract across an update family; positive, infeasible, and unsafe outcomes all
carry independently checkable evidence.

## What is legitimately claimed

- exact finite theorems under total deterministic bounded semantics;
- a compiler for seven finite summary primitives and seven monitor forms;
- an exact optimizer and replay-certificate producer/checker;
- complete bounded finite cross-checks and a deterministic standalone artifact;
- behavior of the 12 shipped declarations, 571 defined mutations, 256 fixed-seed generated problems, and 79 one-at-a-time cost perturbations;
- one narrow, source-pinned projection of five TFX schema presence constraints to Boolean batch-summary events.

## What is not claimed

- production prevalence, adoption, usability, scale, or storage savings;
- full TFDV protobuf parsing, TFX runtime integration, or production deployment;
- semantic inference for arbitrary field renames, label-function revisions, or business concepts;
- unbounded, probabilistic, nondeterministic, approximate, or distributed
  monitor completeness;
- preservation of model accuracy, fairness, privacy, or statistical drift
  metrics;
- novelty of state distinguishability, hitting set, dynamic monitoring, or
  retroactive replay in isolation;
- independent peer review, proof-assistant verification, or acceptance by TSE.

## Public-source projection boundary

The artifact consumes one exact public file: the TFX penguin user-provided
schema pinned to commit `cd99075bfad794a3ea9df49ee77f9c06578f895d`.
Only five features with both `min_fraction=1.0` and `min_count=1` are projected.
Each source constraint becomes one Boolean event field that is true exactly
when the batch is nonempty and every example contains the feature, one
ever-missing retention atom, and one
ever-missing monitor. The source file, Apache-2.0 license, source locator, local
digest, projection map, generated declaration, result, and certificate are
shipped under `external/tfx-penguin/` and `results/tfx-projection/`. This is a
provenance-preserving front-end example, not a claim that the compiler accepts
TFDV protobufs or executes TFX.
The caller must supply that Boolean batch abstraction; no raw-batch adapter is
provided. Presence counts examples containing a feature, not the total number
of scalar values inside a possibly multivalued feature.

The declaration named `label-field-rename` is intentionally narrower: it changes
only a field name and keeps the finite predicates truth-table equivalent. It is
not evidence for a changed label-function rule. The marginal/joint control holds
the same two-disagreement target fixed and changes only the retained catalogue.

## Calibration record

`calibration-matrix.csv` contains 22 paper-level records: 12 TSE papers, five
influential/foundational works, and five adjacent-venue papers.  Each record
states the problem, organizing principle, argument style, practical connection,
evaluation breadth, artifact strength, narrative sequence, bibliography and
figure/table roles, and the precise reuse boundary.  The matrix records
structural/technical reading; it is not a citation-count or award claim and is
not evidence of exhaustive literature coverage.

The manuscript bibliography contains 68 cited works and no uncited entries.
`bibliography-verification.csv` records one metadata locator and verification
basis for every entry.  The LaTeX build runs `tools/check_references.py`, which
checks citation completeness, minimum count, DOI syntax and uniqueness, ledger
coverage, exact 12/5/5 calibration counts, and placeholder absence.  These are
offline consistency checks; they supplement rather than replace inspection of
publisher, proceedings, archive, or bibliographic-catalog records.

All scholarly locators, access status, and integration modes are listed in
`external_resources.csv`.  Full texts are not redistributed.
