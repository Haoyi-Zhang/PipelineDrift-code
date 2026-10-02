# Exact retention portfolios for evolving finite monitors

## Definitions

Fix a finite historical alphabet `H` and future alphabet `F`.  A candidate
retention atom `i` is a total deterministic machine `A_i` over `H` with finite
state set `R_i` and initial state `r_i0`.  Each atom has a positive integer cost
`c_i`.  A planned monitor update `u` has a finite state set `Q_u`, initial state
`q_u0`, a historical transition on `H`, a future transition on `F`, and a binary
output.  Historical and future transitions share the target state set but may
interpret different record schemas.

For a history `h`, write `a_i(h)` for atom `i`'s state and `q_u(h)` for update
`u`'s replay state.  Target states `p` and `q` are future-equivalent, written
`p ~_u q`, exactly when every future word produces the same terminal output.
A selected portfolio `S` is *safe for u* when equal selected summaries imply
future-equivalent target states:

```
forall h,h'.  (forall i in S. a_i(h)=a_i(h'))  =>  q_u(h) ~_u q_u(h').
```

It is safe for a family of updates when it is safe for each member.  This is an
information-preservation claim.  It does not require target state identity and
does not claim statistical, accuracy, or deployment preservation.

For a history pair and update whose target states are not future-equivalent,
define its separator set

```
Delta_u(h,h') = { i | a_i(h) != a_i(h') }.
```

The finite obstruction family contains every such separator set.  If a zero
separator occurs, the inclusion-minimal obstruction basis is exactly
`{empty}`: every nonempty separator is a strict superset and cannot restore
feasibility.  Otherwise the basis keeps the inclusion-minimal nonempty sets.
A zero separator records a target-relevant distinction that no candidate atom
keeps.

## Theorem 1: safety is exact hitting

A portfolio `S` is safe for all planned updates if and only if it intersects
every separator set.  It suffices to intersect every member of the obstruction
basis.

### Proof

Assume `S` misses a separator `Delta_u(h,h')`.  Every selected atom then has the
same state after both histories, while the target states are not
future-equivalent.  Some common future word therefore yields different target
outputs, so `S` is unsafe.

Conversely, if `S` is unsafe, two histories have equal selected summaries but
future-distinguishable target states for some update.  Every selected atom has
equal states on the histories, so `S` is disjoint from their separator.  Thus a
missed separator exists.  When no zero separator exists, removing any separator that strictly contains
another does not change the portfolios that hit all separators: hitting the
smaller set also hits its superset.  Repeated removal yields the stated basis.
When a zero separator exists, the basis is `{empty}` and no portfolio can hit
it.

## Corollary 1: candidate-catalog feasibility

The candidate catalog admits some safe portfolio if and only if no zero
separator exists.  In particular, selecting every candidate is not a fallback
when a zero separator exists.

### Proof

A zero separator is disjoint from every portfolio.  If none exists, selecting
all candidates intersects every nonempty separator.

## Theorem 2: cost-optimal synthesis

For positive atom costs, a minimum-cost safe portfolio is exactly a
minimum-weight hitting set of the obstruction basis.  Ties in the reference
implementation are resolved by fewer atoms and then by the numeric atom mask.

### Proof

Theorem 1 makes the feasible portfolios and hitting sets identical.  Their
objectives are also identical because both sum the costs of the selected atoms.
The secondary order is deterministic and does not change minimum cost.

The implementation uses a greedy feasible solution as an upper bound and then
branches on an unhit obstruction.  A branch selects one atom from that
obstruction.  The lower bound sums the cheapest atom costs for a greedily
chosen collection of pairwise-disjoint remaining obstructions.  No atom can
hit two members of such a collection, so this is a valid lower bound.  A branch
is discarded only when its best possible primary cost is greater than the
incumbent, or an already reached identical remainder has a lexicographically
no-worse prefix.  Every feasible solution chooses an atom on each branched
obstruction and therefore appears in some non-pruned branch.  The returned
solution is optimal under the stated order.  Worst-case search remains
exponential, as expected for weighted hitting set.

## Theorem 3: shortest replay explanation

For a fixed unsafe portfolio `S`, the producer returns a certificate minimizing

```
|h_left| + |h_right| + |future|
```

among all paired histories with equal selected summaries and a common future
that produces unequal target outputs.

### Proof

For each update, breadth-first search explores the reachable product of every
candidate atom and the target monitor.  It stores a shortest historical word
to each reachable product state.  Every history ends at one of these states,
and replacing it by the stored word preserves every atom state and the target
state without increasing length.

Reverse multi-source breadth-first search on target-state pairs starts from
pairs with unequal current output.  Its distance is the shortest common future
length that distinguishes each pair; unreachable pairs in this reverse search
are future-equivalent.  Consequently, for every pair of reachable product
states, the sum of the two stored prefix distances and the pair distance is the
minimum certificate cost for those endpoints.  The producer examines every
unordered endpoint pair whose separator misses `S` and chooses the globally
smallest cost, with deterministic lexical tie-breaking.  Replacing any claimed
certificate by its endpoints cannot beat this construction, so the selected
certificate is globally minimum.

The independent verifier establishes replay validity, binds the selected
portfolio mask, and recomputes event cost.  It deliberately does not claim
minimum by certificate shape alone.  Minimum cost is additionally checked by
direct word enumeration in the complete unary catalogue.

## Proposition: positive certificates are independently checkable

For a safe selected portfolio, a certificate can list the inclusion-minimal
obstruction basis and, for each update, one target-state representative for
every reachable selected-summary fiber.  Recomputing the basis establishes the
portfolio's hitting obligations; recomputing reachable fibers and future
equivalence establishes that every listed representative is continuation-
equivalent to all target states in its fiber.  Exhaustive enumeration of all
candidate subsets establishes the deterministic cost/cardinality/mask optimum
for the bounded instance.

The delivered verifier performs those computations without importing the
producer's conflict-basis constructor or branch-and-bound optimizer.  It also
requires an exact certificate field set and exact integer types, so Boolean
values cannot exploit Python's integer-subclass behavior.  This is an
independent executable check of the finite object, not a proof-assistant
formalization of the general theorems.

## Theorem 4: compiler trace preservation

For each supported declaration primitive (`seen`, saturated `count`, saturated
`run`, `last`, finite `bitset`, saturated `histogram`, and bounded Boolean
predicate-suffix `window`), the
compiled transition table reaches the same abstract state as direct evaluation
of that primitive on every finite record trace.  The same holds for monitor
updates across their historical and future schemas.

### Proof

Compilation enumerates the finite schema records and the primitive's complete
finite state space.  For every state and record it stores exactly the primitive
one-step update: Boolean disjunction for `seen`, capped addition for `count`,
capped reset/increment for `run`, replacement for `last`, bit insertion for
`bitset`, one capped component increment for `histogram`, and append/truncate
for `window`.  The monitor forms use the same state operations and derive their
binary output from the declared threshold, value, set, or pattern.

The empty trace starts in the same declared initial state.  If the compiled and
direct states agree after a trace, the table entry for the next enumerated
record is, by construction, the direct one-step result.  Induction on trace
length proves equality.  Historical and future expressions are separately
evaluated over their respective finite schemas, so the induction continues
across the migration boundary.

## Algorithmic scope

For update `u`, let `M_u` be the number of reachable states in the product of
all candidate atoms and the update, `q_u` its target state count, `a=|H|`,
`b=|F|`, and `k` the number of atoms.  Each historical product edge advances
all `k` atom states and the target, so reachability costs `O(a M_u (k+1))`
primitive updates.  Target-pair future distances cost `O(b q_u^2)`; explicit
endpoint-pair separator construction costs `O(k M_u^2)` before basis
minimization.  Reconstructing two historical prefixes and one future suffix is
linear in their emitted length, while deterministic ties can compare words
lexicographically up to that length.  Exhaustive bounded verification may
inspect `2^k` subsets, and obstruction minimization and exact hitting-set search
remain exponential in their finite inputs.  The present implementation is
intended for bounded schemas and candidate catalogues, not unbounded logs or
large symbolic state spaces.  These limits are explicit guards, not performance
claims.
