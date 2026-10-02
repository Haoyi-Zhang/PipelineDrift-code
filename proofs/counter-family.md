# Saturated consecutive-low counters

## Fixed supplementary diagnostic before its execution

The historic retained counter is capped at k, and the replay target and its
future evolution are capped at t. Both read letters normal=0 and low=1, start
at zero, reset to zero on normal, and increment with saturation on low. The
target verdict is one exactly at its cap. No learned predictions are used.

**Proposition.** For integers k,t >= 1, exact replay-equivalent migration exists
iff t <= k. When t > k the minimum paired-history cost is k+t, counting the
common suffix once. When t <= k, the map s -> min(s,t) is valid.

**Proof.** If t <= k, after any history the target equals the retained state
truncated to t. This follows by induction: truncation commutes with reset and
saturating increment. Thus the proposed state map reconstructs the target and
all future outputs are identical.

If t > k, for every retained state r < k the replay target is exactly r: the
trailing low-run length is r. The only potentially conflicting fiber is r=k,
whose target states are k,k+1,...,t. Choose p<q in this fiber. The shortest
histories reaching them have lengths p and q, attained by all-low histories.
A distinguishing suffix cannot contain a normal letter before divergence,
since that resets both states to zero, making every later state equal. An
all-low suffix first distinguishes this pair after t-q letters. Its length is
therefore exactly t-q. Every such collision has cost at least
p+q+(t-q)=p+t>=k+t. Histories low^k and low^(k+1), followed by the common suffix
low^(t-k-1), attain k+t. Therefore migration is impossible and this cost is
minimal. The case q=t includes the empty suffix. This argument covers all
histories, not only those enumerated by a bounded test.

## Fixed check grid

For the supplementary diagnostic, include all 48 pairs k=1..6, t=1..8 in
lexicographic (k,t) order. Expected outcomes are 21 admissible and 27
inadmissible, with cost k+t for each rejection. Compare the implementation and
certificate verifier against the above closed-form result. This does not reuse
or fit an empirical data set. It is a parameter-sensitivity check of a proved
example family, separate from the original 46,932-table diagnostic.

The argument is an elementary property of finite counters, not an asserted
new lower bound for monitoring in general. It does not address sliding windows,
approximate statistics, resets accepted as a different policy, or clock input
that is not included in the retained state.
