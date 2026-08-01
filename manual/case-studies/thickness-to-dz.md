# Assertion vs proof: thickness_to_dz and the plain-DO schema lemma

*Kernel pairs: Fortran `thickness_to_dz_3d`, loop nests 4 and 2
(`MOM6/src/core/MOM_interface_heights.F90`) ⇄ C++
`MOM::thickness_to_dz_3d_boussinesq_point` /
`MOM::thickness_to_dz_3d_nonboussinesq_point`
(`TIM/mom/cpp/mom_interface_heights_kernel.hpp`).*

The thickness-to-height conversions are the simplest arithmetic in the bank —
one multiplication, or two:

```fortran
dz(i,j,k) = GV%H_to_Z * h(i,j,k)                      ! Boussinesq branch
dz(i,j,k) = GV%H_to_RZ * h(i,j,k) * tv%SpV_avg(i,j,k) ! non-Boussinesq branch
```

They are in this manual because of their **loop form**. These are plain `do`
nests — not `do concurrent` — and when the kernel was first considered, the
pipeline *refused to bank it*, recording it as out of scope: extending
pointize to plain DO "would assert an iteration-independence the source
doesn't state, and that semantics decision is reserved for the user." That
refusal-by-default of a semantic question, not just of a syntax shape, is
the discipline working as intended.

## The decision, discharged by proof

When the decision came back — bank the plain-DO variants — it was discharged
in a way that left plain DO on *stronger* footing than `do concurrent`. The
design has two layers, and keeping them straight is the whole point:

**The Python side is a gate, not a justification.**
[`pointize`](../concepts/pointize.md) admits a plain nest only when it is
perfectly nested and every array reference is indexed exactly by the loop
indices — plus one check the plain path alone needs: every *write* must land
in the iteration's own array cell. An assignment to a scalar parameter
(`s = s + a(i)`) is an accumulator/reduction shape and refuses, as do
imperfect nests, strides, and duplicate indices. The gate guarantees the
setting of the lemma below applies; it does not itself justify any
reordering.

**The Lean side is the license.** A plain DO's honest semantics is a
*sequential fold* of per-point updates over an enumeration of the index box —
so that is exactly what the kernel-level theorems model (`foldSeq`). The
license to equate that with the pointwise map is a once-and-for-all schema
lemma, proved in `lean/groundline/Groundline/SeqSchema.lean`:

```lean
theorem foldSeq_eq_pointwiseMap (f : ι → σ → σ) (enum : List ι)
    (hnd : enum.Nodup) (hall : ∀ i, i ∈ enum) (s₀ : ι → σ) :
    foldSeq f s₀ enum = pointwiseMap f s₀
```

The proof is an induction over the enumeration with a frame argument
(`foldSeq_frame`: cells not in the enumeration are never written — under
no-duplicates, each iteration finds its own cell pristine and writes land in
disjoint cells, so the fold telescopes to the map). The lemma is fully
general — any point function `f : ι → σ → σ`, any state type — because once
pointize has produced `f`, point-locality is baked into `f`'s *type*; the
hypothesis is structural, never re-checked per kernel.

**The symmetry worth recording:** for `do concurrent`, the license for the
pointwise model is the source's independence *assertion*; plain DO now gets a
*proof* instead. The construct that promises nothing ends up with the
stronger warrant. Reductions and cross-iteration recurrences remain refused —
they are not point-local, and their sequential-vs-unordered question is real
mathematics [reserved for a future step](../limits.md).

## Component reads, and the fold in the theorems

These kernels also introduced derived-type component reads (pointize's
"rule B"): the loop-invariant scalar components `GV%H_to_Z` / `GV%H_to_RZ`
become synthesized scalar `in` parameters `h_to_z` / `h_to_rz` —
loop-invariance guaranteed by `intent(in)`, not assumed — and the component
array `tv%SpV_avg(i,j,k)` becomes `spv_avg`. In the kernel-level theorems the
mapping surfaces exactly as designed: `h_to_rz` is captured loop-invariantly,
`spv_avg` is fed per cell (`spv i`).

The Fortran side of each kernel theorem is the honest sequential fold; the
proof instantiates the schema lemma, then applies the point lemma cell-wise:

```lean
theorem thicknessToDzBouss_kernel_equiv {ι : Type*} [DecidableEq ι]
    (h : ι → ℝ) (h_to_z : ℝ) (dz₀ : ι → ℝ) (enum : List ι)
    (hnd : enum.Nodup) (hall : ∀ i, i ∈ enum) :
    thicknessToDzBoussLoopF h h_to_z dz₀ enum
      = thicknessToDzBoussLaunchC h h_to_z dz₀
```

A pleasing detail: `dz` is `intent(inout)`, and `foldSeq` gives cells outside
the enumeration their initial values — exactly Fortran's semantics for halo
cells outside the loop range. The honest model was also the accurate one.

Both point lemmas are **`rfl`** — both generated bodies are `h_to_z * h`
(respectively `h_to_rz * h * spv`, left-associated as in both sources), and
per the mature pattern there are no hand-written models at all: the lemmas
relate the two generated defs directly. The whole batch — these two kernels,
[the third](edge-thickness-upwind.md), the schema lemmas, and the extended
axioms audit — compiled on the first `lake build` attempt.

## The theorems and their audits

From the current build log — note the schema declarations reporting *strict
subsets* of the standard three (no classical reasoning in the structural
induction; the audit file documents that expectation):

```text
'Groundline.foldSeq' does not depend on any axioms
'Groundline.pointwiseMap' does not depend on any axioms
'Groundline.foldSeq_frame' depends on axioms: [propext]
'Groundline.foldSeq_apply_of_mem' depends on axioms: [propext]
'Groundline.foldSeq_eq_pointwiseMap' depends on axioms: [propext, Quot.sound]
'Groundline.GeneratedFtn.thickness_to_dz_3d_boussinesq' depends on axioms: [propext, Classical.choice, Quot.sound]
'Groundline.GeneratedCpp.thickness_to_dz_3d_boussinesq_point' depends on axioms: [propext, Classical.choice, Quot.sound]
'Groundline.thicknessToDzBouss_point_equiv' depends on axioms: [propext, Classical.choice, Quot.sound]
'Groundline.thicknessToDzBouss_kernel_equiv' depends on axioms: [propext, Classical.choice, Quot.sound]
'Groundline.GeneratedFtn.thickness_to_dz_3d_nonboussinesq' depends on axioms: [propext, Classical.choice, Quot.sound]
'Groundline.GeneratedCpp.thickness_to_dz_3d_nonboussinesq_point' depends on axioms: [propext, Classical.choice, Quot.sound]
'Groundline.thicknessToDzNonBouss_point_equiv' depends on axioms: [propext, Classical.choice, Quot.sound]
'Groundline.thicknessToDzNonBouss_kernel_equiv' depends on axioms: [propext, Classical.choice, Quot.sound]
```

Proof files: `lean/groundline/Groundline/SeqSchema.lean`, `Groundline/ThicknessToDz.lean`.
