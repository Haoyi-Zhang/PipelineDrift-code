# Declarative finite contract language

A declaration is a JSON object with exactly `name`, optional `metadata`,
`history_schema`, `future_schema`, `retention_atoms`, and `monitor_updates`.
Schemas have exactly one `fields` object. Each declaration layer, atom kind,
monitor kind, and expression form has a closed field allow-list; unknown or
misspelled keys are rejected rather than ignored.

The compiler enumerates finite record alphabets and emits total extensional
machines. It performs dimension checks before constructing records, states,
transition tables, products, state pairs, subsets, or witness-search objects.
A resource-limit refusal is a tool failure and does not mean safe, unsafe,
feasible, infeasible, or optimal.

## Exact typed values and expressions

An expression is a JSON scalar/list constant, `{ "field": NAME }`,
`{ "const": VALUE }`, or `{ "op": OP, "args": [...] }`. Supported operators
are `eq`, `ne`, `lt`, `le`, `gt`, `ge`, `and`, `or`, `not`, `in`, and `tuple`.
Predicates must evaluate to JSON Booleans on every enumerated record.

`eq`, `ne`, and `in` use the same exact typed-value relation. In particular,
JSON `false`/`true` are distinct from integer `0`/`1`, despite Python host
language equality. Arrays compare componentwise with this same relation;
objects compare by their string-key sets and corresponding typed values,
independently of key order. An object is distinct from an array of its key/value
pairs, including when nested. Membership and `required` arrays have mathematical set
semantics: duplicates are idempotent. The independent reference interpreter
implements this relation separately and includes a regression mutation that
restores Python's Boolean/integer aliasing.

## Explicit initial states and empty history

Every retention atom and monitor update must contain an explicit integer
`initial` state index. Boolean values, omitted values, negative values, and
indices outside the compiled state range are rejected. The compiler never
silently substitutes state zero. The language check independently compares each
compiled initial state and the resulting empty-history state/output.

## Retention atoms

- `seen`: one bit recording whether a Boolean predicate has occurred.
- `count`: a Boolean-predicate count saturated at a positive `cap`.
- `run`: the current consecutive Boolean-predicate run, saturated at `cap`.
- `last`: an explicit unset state plus the last value from a finite domain.
- `bitset`: the mathematical set of observed values from a finite domain.
- `histogram`: one saturated counter per declared finite value.
- `window`: the Boolean predicate suffix up to a width in `1..10`.

The delivered `window` is not a general suffix over an arbitrary value domain.
Its state space is the set of Boolean words of length at most the declared
width. Costs default to the minimum fixed-width bits for the compiled state
count, or a declaration can supply a positive integer policy cost. Costs are
additive across selected atoms; they are not automatically bytes or latency.

## Monitor updates

`seen`, `count_threshold`, `run_threshold`, `last_equals`, `bitset_any`,
`bitset_all`, and `window_pattern` use corresponding finite state operations.
An update declares either one expression used on both sides of the boundary or
both historical and future expressions. This supports explicit field-name or
finite-record-representation mappings; it does not infer business equivalence or
learned labeling-rule equivalence.

The shipped case `label-field-rename` changes only `old_label` to `label`; its
pre/post predicates have identical finite truth tables. The paired
`marginals-only-infeasible` and `joint-marginals` cases hold the same
two-disagreement target fixed and differ only by the added joint disagreement
counter.

## Finite guards

The shared configured limits are:

- at most 4,096 states per explicit machine;
- at most 4,096 enumerated records per schema;
- at most 1,000,000 transition cells per checked machine/table group;
- at most 100,000 full product states;
- at most 1,000,000 checked ordered or unordered state pairs;
- at most 2,000,000 pair-transition cells in future-equivalence search;
- at most 1,048,576 candidate subsets for exhaustive validation.

State formulas are checked arithmetically before allocation for all primitive
and monitor branches, including `count`, `run`, `histogram`, and `window`.
Tests exercise refusal with dimensions that exceed these limits without
materializing the oversized objects.

## Non-claims

The language has no unbounded integer, timestamp, probabilistic,
nondeterministic, learned-model, SQL-runtime, protobuf-runtime, or external
service semantics. Compilation does not infer that two external fields or
predicates mean the same thing. The guarantee is limited to the explicit finite
declaration accepted by the compiler.
