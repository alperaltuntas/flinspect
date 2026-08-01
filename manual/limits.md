# Limits & roadmap

The rest of this manual documents what runs today; this page is the
inventory of what does not — and what each missing piece would take.
Everything below is **roadmap**: none of it is implemented, and none of it
should be cited as a capability.

## The frontier: reductions and k-recurrences

The current method rests on **point-locality**: every banked kernel computes
each output cell from that cell's inputs alone, so both iteration licenses —
`do concurrent`'s assertion and the plain-DO
[schema lemma](concepts/pointize.md) — reduce a loop to a pointwise map. The
kernels just past that boundary are the ones the pipeline refuses today:

- **k-recurrences** — `find_dz_for_eta`'s hydrostatic pressure accumulation,
  `p(i,j,K+1) = p(i,j,K) + GV%g_Earth*GV%H_to_RZ*h(i,j,k)`: iteration `k+1`
  reads what iteration `k` wrote. The boundary is marked with a committed
  refusal fixture
  ([case study](case-studies/edge-thickness-upwind.md#the-boundary-marked-with-a-refusal-fixture)).
- **reductions** — scalar accumulators (`s = s + a(i)`), refused by the
  plain-DO write gate as not point-local.

What a future step would need:

- a **model shape** that keeps the sequential structure instead of erasing
  it — for a k-recurrence, a fold over the k-enumeration *is* the honest
  model on both sides, and the equivalence theorem becomes an **induction**
  over that enumeration rather than an instantiation of a ∀-schema;
- a matching **extraction rule** — pointize over the parallel indices (i, j)
  only, leaving the recurrence dimension as an explicit fold; a new gate must
  check which subscripts carry offsets and in which dimension;
- for reductions, additionally a decision about **operation order**: over ℝ
  the fold order is provably irrelevant (associativity/commutativity), which
  is exactly the reals-first division of labor — but the schema lemma for
  "any duplicate-free enumeration gives the same sum" still has to be proved
  once;
- the sequential-vs-unordered question these shapes pose is real mathematics,
  and it was deliberately **reserved** rather than hand-waved when plain DO
  was admitted.

## Masks and per-cell guards

Many kernels in the case-study code base guard their arithmetic per cell
(`if (G%mask2dT(i,j) > 0.) …`) or branch on wet/dry state. A masked point kernel is still point-local,
so the iteration schemas should extend — but the mask array enters the model
as a per-cell input with its own rule-B-like story (a component array of the
grid type, read at exactly the loop indices), and the generated defs grow a
guard shape the printer and the by-eye audit must handle. Unstarted; refused
today by the array-index gate (the mask subscripts `(i,j)` don't match a
3-D nest's indices).

## More C++ surface

The clang frontend admits exactly what the existing kernels need. Real
future kernels will bring at least: `pow` calls (today only `abs` passes the
callee gate), ternary conditional expressions (`?:` — the natural C++
spelling of what functionalize's `Cond` already models), and `amrex::min`/
`amrex::max` (the printer is already able to spell `min`/`max`). Each enters
by the [subset-extension workflow](howto/extend-subset.md) when a kernel
demands it — fixture first, refusal edges pinned.

One larger item in the same category: **C++ loop extraction**. Today the
clang frontend accepts only per-point functions, so a Fortran loop can only
be compared against a C++ point function (under the explicit
`pointize = true` license). Extracting a C++ `for` nest and pointizing it
the same way would allow loop-vs-loop comparisons — a natural next step,
not started.

## Scope boundaries that are permanent, not roadmap

Worth restating, so the roadmap above isn't misread as "everything,
eventually":

- equivalence stays **over ℝ** — floating-point identity is the regression
  and ensemble machinery's job, by design
  ([what the theorems mean](index.md#what-the-theorems-mean-and-deliberately-do-not));
- the theorems cover **kernels**, not the surrounding driver code, MPI
  choreography, or I/O;
- the translator will keep **refusing** rather than approximating; the
  subset grows construct by construct with fixtures, or not at all.

## The other half of the vision

The kernel track certifies each port; the **relational track** is meant to decide
*which* kernels are provable in isolation and to gate the porting frontier in
CI — the two compose into one gate: every ported kernel carries a checked
theorem *and* no forbidden structural edge appears. The relational track's
query/CI layer is not built yet; see [The relational track](relational.md)
for what exists today.
