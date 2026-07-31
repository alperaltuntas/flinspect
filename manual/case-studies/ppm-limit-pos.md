# The pilot: PPM_limit_pos

*Kernel pair: Fortran subroutine `PPM_limit_pos`
(`MOM6/src/core/MOM_continuity_PPM.F90`) ⇄ C++ `MOM::ppm_limit_pos_point`
(`TIM/mom/cpp/mom_continuity_ppm_kernel.hpp`).*

Track B did not start with tooling. It started with a timeboxed question:
**is this kind of proof cheap enough to be worth building anything for?** The
rule for the pilot was: hand-write the Lean models for one already-ported
kernel pair, prove the equivalence, and only if that succeeds design the
pipeline. `PPM_limit_pos` — a positivity-preserving limiter for the PPM
reconstruction, all piecewise-polynomial arithmetic and inequality guards —
was the friendliest candidate: a pure point function, no reductions, no masks.

## Hand-written models first

Two Lean definitions were written by eye, `ppmLimitPosF` from the Fortran and
`ppmLimitPosC` from the C++, with one discipline that shaped everything after:
**each model mirrors its own source's expression shapes.** The Fortran source
computes the limiter's denominator as `curv**2 + 3.0*dh**2`; the C++ port
spells it `(curv * curv) + (3.0_rt * (dh * dh))`. The models keep those shapes
— so the equivalence theorem absorbs *exactly* the algebraic deltas a human
transcriber introduced, and nothing else.

The point lemma turned out to be about five lines, and compiled on the first
attempt:

```lean
theorem ppmLimitPos_point_equiv (h_in h_L h_R h_min : ℝ) :
    ppmLimitPosC h_L h_R h_in h_min = ppmLimitPosF h_in h_L h_R h_min := by
  unfold ppmLimitPosC ppmLimitPosF
  have hsq : ∀ c d : ℝ, c * c + 3 * (d * d) = c ^ 2 + 3 * d ^ 2 := by
    intro c d; ring
  simp only [hsq]
```

One `ring`-provable bridge identity, then rewrite. On top of it,
`ppmLimitPos_kernel_equiv` lifts pointwise agreement to whole arrays: both
`do concurrent (k,j,i)` and `amrex::ParallelFor(box)` are modeled as a
pointwise map over an abstract index type ι, and the arrays-as-functions
equality follows from the point lemma. The pilot's verdict: for kernels in
the TIM point-function style, the point lemma is near-mechanical.

## The honest caveat — and the printer that removed it

The pilot's own record flagged its weakness: the models were **hand-written**,
so source fidelity rested on human eyes — precisely the trust the project
exists to eliminate. The next step built the deterministic printer
(dump → [kernel IR](../concepts/kernel-ir.md) → Lean) and pointed it at the
*production* MOM6 with-sema dump — the real compiler artifact of the real
source, not a fixture. The extractor consumed `MOM_continuity_PPM.o_ptree`
unmodified, dropped the grid struct and the six index-range arguments during
[pointization](../concepts/pointize.md), and emitted
`TrackB.Generated.ppm_limit_pos`.

Then the question that makes or breaks the whole approach: is the generated
def the same function as the hand-written one? In Lean, not by eye:

```lean
theorem generated_ppm_limit_pos_fidelity :
    TrackB.Generated.ppm_limit_pos = TrackB.ppmLimitPosF := rfl
```

## Why `rfl` is the strongest possible statement

`rfl` proves an equality by *definitional equality*: Lean's kernel checks
that the two sides reduce to the same term by unfolding definitions alone —
no case analysis, no algebra, no proof search. There is nothing to inspect
and nothing that could hide a discrepancy: if the printer had drifted from
the hand model by so much as a swapped operand that mattered, an extra guard,
a wrong literal, `rfl` would not typecheck. "The machine-generated model and
the human-written model are **the same mathematical object**" is the
strongest no-drift statement the logic offers, and the printer earned it on
its first production kernel.

(What `rfl` tolerates is exactly the notation level: the printer's preserved
source parentheses, and `curv > 0` versus `0 < curv` — Lean's `>` *is* `<`
flipped, by definition.)

With fidelity checked, transitivity closes the chain —
`generated_matches_cpp`: the generated-from-dump Fortran model equals the C++
port. Later, when the [clang side landed](../concepts/two-irs.md), the same
pattern repeated from the other direction:
`generated_cpp_ppm_limit_pos_fidelity` (also `rfl`) and the fully-mechanical
chain theorem `generated_cpp_matches_generated_fortran_pos` — both endpoints
machine-produced, every link machine-checked. The hand-written models were
demoted from load-bearing links to verified references, kept as
human-readable anchors.

## The theorems and their audits

From the current build log (`#print axioms`, via `Pilot/AxiomsAudit.lean`):

```text
'TrackB.ppmLimitPos_point_equiv' depends on axioms: [propext, Classical.choice, Quot.sound]
'TrackB.ppmLimitPos_kernel_equiv' depends on axioms: [propext, Classical.choice, Quot.sound]
'TrackB.Generated.ppm_limit_pos' depends on axioms: [propext, Classical.choice, Quot.sound]
'generated_ppm_limit_pos_fidelity' depends on axioms: [propext, Classical.choice, Quot.sound]
'generated_matches_cpp' depends on axioms: [propext, Classical.choice, Quot.sound]
'TrackB.GeneratedCpp.ppm_limit_pos_point' depends on axioms: [propext, Classical.choice, Quot.sound]
'generated_cpp_ppm_limit_pos_fidelity' depends on axioms: [propext, Classical.choice, Quot.sound]
'generated_cpp_matches_generated_fortran_pos' depends on axioms: [propext, Classical.choice, Quot.sound]
```

Exactly Lean/Mathlib's three standard axioms, no `sorryAx` — see
[the trusted base](../concepts/trusted-base.md). Proof files:
`lean/pilot/Pilot/PpmLimitPos.lean`, `Pilot/Fidelity.lean`,
`Pilot/FidelityCpp.lean`.
