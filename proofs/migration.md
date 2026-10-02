# Exact replay-equivalent migration: model and complete argument

These are written mathematical proofs, not proof-assistant-checked proofs.
The constructions apply classical finite-state distinguishability and product
reachability; they are not claimed as new automata-theoretic results. See
E. F. Moore, “Gedanken-Experiments on Sequential Machines,” *Automata Studies*,
1956, pp. 129–153, especially the state-distinguishability definitions and
Theorem 6. Our simple product bound is deliberately loose, not a tight bound
attributed to Moore.

## Model and quantifiers

Let H and F be nonempty finite alphabets. A retention machine has a finite
nonempty state set R, initial r0 and total transition rho: R x H -> R. A target
has a finite nonempty state set Q, initial q0, historic replay transition
eta: Q x H -> Q, future transition delta: Q x F -> Q and output o: Q -> {0,1}.
The two target transitions can differ. Their shared state space models the
interpretation of the update boundary, not two independently initialized
machines. Extension to words is denoted by a star and includes the empty word.

Every word in H* is a possible history; every word in F* is a possible common
future. There is one update boundary, placed after the whole historic word.
A migration m: R -> Q sees only the retained state, not the old raw data,
history length, wall clock, discarded outputs or a secret identifier. Such
information must be encoded in R to be available to m. All quantification is
exact and deterministic; there is no probability measure or approximate
notion of agreement.

A migration is replay-equivalent iff, for all h in H* and v in F*,

    o(delta*(m(rho*(r0,h)), v)) = o(delta*(eta*(q0,h), v)).             (1)

This compares the migrated target with the target replayed on the entire
historic input using eta, then continued using delta. It does not require the
old monitor's outputs to equal the new monitor's outputs. Resetting the target
is another policy and is not assumed equivalent to replay.

Write p ~ q iff their outputs agree after every future word v. Define
J = {(rho*(r0,h), eta*(q0,h)) : h in H*} and
B(r) = {q : (r,q) in J}. The latter is the fiber of reachable replay states
consistent with a retained state. Empty fibers impose no constraint.

## Lemma 1: future relation

The relation ~ is an equivalence relation because equality of the function
v -> o(delta*(q,v)) is reflexive, symmetric and transitive. It preserves
current outputs by choosing v empty. If p~q, then for any letter a and word w,
the outputs after aw agree, so delta(p,a)~delta(q,a). Conversely, any relation
E that preserves outputs and is closed under paired transitions is a subset
of ~: induction on the length of v preserves membership in E, so terminal
outputs agree. E need not itself be reflexive, symmetric or transitive for
this last implication.

## Theorem 1: exact admission criterion

A replay-equivalent migration exists iff every nonempty B(r) lies in one
~-equivalence class.

*Necessity.* Suppose m satisfies (1). Let p,q be in B(r), witnessed by histories
h1,h2. For every future v, applying (1) to both histories gives
outputs from p = outputs from m(r) = outputs from q. Thus p~q. This holds
for all pairs in the fiber. A failure of the condition therefore excludes
**every** deterministic migration based only on R, not merely a selected map.

*Sufficiency.* For each nonempty B(r), choose one element p_r and define
m(r)=p_r. Fill unreachable entries arbitrarily from the nonempty set Q. Any
history h ends in some (r,q) in J, so q and p_r belong to the same fiber and
are equivalent. Their outputs agree after every future v by the definition
of ~, establishing (1). There are finitely many fibers, so this choice can
be made constructively. The implementation uses the least numbered member.

## Theorem 2: finite collision witnesses and exact minimum cost

If no migration exists, there are h1,h2 in H* and v in F* such that their
retained states agree while the target outputs after v differ. Define the
cost as |h1|+|h2|+|v|. The common future is counted **once**, not twice. No
edit count, number of distinct symbols, raw rows or wall-clock latency is
minimized. Histories need not be the same length.

Let A(r,q) be the shortest historic word reaching (r,q), as a length rather
than a chosen string. Let D(p,q) be the shortest distinguishing future word,
or infinity if p~q. Then the minimum collision cost equals

    min over r and p,q in B(r), p != q:
        A(r,p) + A(r,q) + D(p,q),                                  (2)

where infinite terms are omitted. Rejection makes this set nonempty by
Theorem 1 and the definition of nonequivalence.

For any collision, its first history has length at least A(r,p), its second
at least A(r,q), and its suffix at least D(p,q). Thus its cost is at least
the minimum in (2). Conversely, choose a finite minimizing entry and shortest
words for its three terms. The histories end in the required same retained
state, and the common suffix distinguishes their replay states. They form
a collision attaining (2). The three word choices are independent because
all words over the declared alphabets are admissible; no unstated environment
constraint couples the two histories or excludes a future continuation.

Reachability is computed in R x Q under (rho,eta), with at most |R||Q| nodes.
Every reachable joint state has a simple shortest path, hence a history of
length at most |R||Q|-1. A distinguishing future is a path in Q x Q to a pair
with unequal outputs; a shortest path is simple, hence has length at most
|Q|^2-1. Thus a collision exists within these independent bounds and a
minimum collision has cost at most 2(|R||Q|-1)+|Q|^2-1. These are safe graph
bounds, not sharp lower bounds or claims of optimal automata minimization.

## Lemma 2: search implementation

Forward breadth-first search from (r0,q0) computes J, shortest distances and
one parent edge per discovered pair. Since every edge has unit cost and a
node is enqueued only on first discovery, induction over queue depth proves
the recorded depth equals A.

For future pairs, make a reverse adjacency list for each edge
(p,q) -> (delta(p,a),delta(q,a)). Seed reverse breadth-first search with
all unequal-output pairs at distance zero. Every future word is exactly a
path in this graph. The distance found is consequently D; pairs not reached
are precisely equivalent pairs. To reconstruct a suffix of distance d>0,
choose a symbol whose successor distance is d-1. Such a symbol exists on a
shortest path. Repeating this reaches distance zero and yields length d.

The program enumerates all unordered distinct pairs inside each reachable
fiber. Ordered pair distances are symmetric, so this loses no minimum.
It reconstructs shortest words and selects the lowest cost, with deterministic
length/lexicographic tie-breaking. Theorem 2 proves the cost claim. Minimality
is not inferred from successful certificate verification.

For n=|Q|, r=|R|, a=|H| and b=|F|, the graph-distance and candidate-length
computations require O(arn+bn^2+rn^2) unit-cost operations. The present program
also reconstructs words for every distinguishable candidate to choose a
lexicographic tie. For C such candidates, a conservative additional bound is
O(C(rn+bn^2)); this overhead is not suppressed in implementation claims.
Working graph storage is O(arn+bn^2+rn+n^2), with transition tables and
certificates included in that conservative bound. A bounded cache stores at
most 128 future distance vectors, multiplying the corresponding n^2 bound
by a fixed implementation constant. There is no demonstrated incremental
update or large-instance scalability guarantee.

## Theorem 3: certificates checked without the search algorithm

A positive certificate contains a map, a set Jc of joint states, and a
relation E on target states. The checker requires:

1. The initial pair belongs to Jc and Jc is closed under every historic letter.
2. For each (r,q) in Jc, m(r) is a valid state and (m(r),q) belongs to E.
3. Every pair in E has equal output and its successors under every future
   letter also belong to E.

Induction on historic words gives J subset Jc from condition 1. Lemma 1
implies E subset ~ from condition 3. Condition 2 therefore gives (1) for
all histories. Listing additional joint states is sound if all obligations
still pass. Unreachable map entries can be null: they are absent from the
actual domain used by any history and can be extended arbitrarily. They
cannot be null for an r mentioned in Jc.

Conversely, if a migration exists, use Jc=J and E=~ with that migration.
Every condition holds, so the positive certificate format is complete for
existence. The format is not restricted to this maximal relation: a smaller
closed relation containing all required pairs is equally sound.

For a negative certificate, the checker replays h1,h2 and v directly, checks
that the two retained states coincide, checks the target-state annotations,
checks unequal terminal outputs, and recomputes the stated event cost.
These checks imply a collision, which excludes migration by Theorem 1.
Theorem 2 guarantees that the producer can emit such a certificate whenever
migration does not exist. The negative checker intentionally makes **no
minimality claim**: a longer valid collision is still a valid certificate.

Index ranges, table totality, matrix dimensions, initial states, verdict
values and certificate fields are checked before semantic use. Boolean JSON
values are not accepted as integer indices. These parser checks and the
mathematical argument are not a verified compiler from an external pipeline
schema.

## Exact oracle bounds and independence

The small oracle uses its own table-execution loop, enumerates every historic
word through |R||Q|-1, every future word through |Q|^2-1, and every function
R -> Q. It compares finite future signatures for each reachable historic pair.
The reachability bound covers every possible historic joint state, and the
future bound distinguishes every nonequivalent target pair. Therefore a map
passing the bounded comparisons satisfies (1), and any valid map passes.
Enumerating every map yields a decision independent of the producer's fiber
criterion. Independently enumerating history pairs and suffix lengths yields
(2) by Theorem 2's bounds. This oracle is algorithmically separate, not an
independent researcher or proof assistant. Shared model mistakes can still
survive agreement.

The oracle rejects a call when explicit word/map limits would be exceeded.
A refused oracle call is not a pass. The full table diagnostic is confined to
sizes meeting those limits. The counter-family diagnostic instead uses the
separately proved closed-form proposition in counter-family.md.
