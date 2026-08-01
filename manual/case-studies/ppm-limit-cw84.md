# The control-flow join: PPM_limit_CW84 — and the bug the audit caught

*Kernel pair: Fortran subroutine `PPM_limit_CW84`
(`MOM6/src/core/MOM_continuity_PPM.F90`) ⇄ C++ `MOM::ppm_limit_cw84_point`
(`TIM/mom/cpp/mom_continuity_ppm_kernel.hpp`).*

The second kernel banked, and the one that earned its keep twice: it forced
the pipeline's hardest semantic decision, and auditing that decision against
its specification uncovered a real latent bug in the extractor. This is the
"why machine-checking pays" story, told with the bug left in.

## The kernel that wouldn't functionalize

CW84 — the Colella–Woodward 1984 monotonicity limiter — ends its loop body
with two *sequential* guarded assignments:

```fortran
if ( FunFac >  RLdiff2 ) h_L(i,j,k) = 3. * h_i - 2. * h_R(i,j,k)
if ( FunFac < -RLdiff2 ) h_R(i,j,k) = 3. * h_i - 2. * h_L(i,j,k)
```

The second guard's right-hand side reads `h_L` — which the first statement
**may have just updated**. Until then, [functionalize](../concepts/functionalize.md)
refused any statement following an `if`; CW84 required deciding what a
control-flow join *means* functionally. The decision, deliberately
conservative: support exactly one shape (single-branch `if`, branch bodies
assigning only to output variables), merge per variable into inline
conditionals —

```text
state'[h_l] = Cond(FunFac > RLdiff2, 3*h_i - 2*h_r, h_l)
```

— and run the remaining statements against the *merged* state, so the second
guard's `h_l` read observes the first `if`'s conditional value. Sequential
semantics, as in the source. Every other join shape refuses, with the refusals
pinned by tests. Two smaller constructs rode along (Fortran's one-line logical
IF statement, and unary minus with its cross-language precedence subtlety),
each with its own fixtures.

## The bug: aliases silently unthreaded

Banking a semantics this delicate warranted a line-by-line audit of the
implementation against its specification — and the audit found a bug **older
than the join itself**. The state-substitution helper skipped substituting
when an output's current symbolic value was a plain variable. The intent was
to skip the trivial identity case (`state[h_l] = Var(h_l)` — substituting is
a no-op anyway). But the condition couldn't tell the identity from an
**alias**: after `b = a`, the state maps `b` to the plain variable `a`, the
skip fired, and a later read of `b` would silently keep referring to the
*input* `b` — a wrong model, the exact failure mode the whole design exists
to prevent.

No banked kernel hit it. But the join machinery made it reachable, so it was
fixed (substitution is now unconditional — the docstring records why) and
pinned by a regression test
(`test_sequential_alias_read_threads_current_value`). Regenerating the
committed models confirmed the fix changed nothing for existing kernels.

The morals: a wrong model *cannot* be caught by the proof it feeds —
the theorem would verify perfectly against the wrong function. What caught
this was the discipline *around* the proofs: audit trusted-base code when its
reach grows, refuse what you haven't audited. And plausible-looking
shortcuts in trusted-base code (skip when it "must be" a no-op) are exactly
where wrong models come from.

## The proof: absorbing a representation delta

CW84 also matured the proof pattern: **no hand-written Fortran model**. The
point lemma is proved directly against the generated def — the printer's
output moved onto the trusted path instead of being checked by eye against a
second transcription. Only the C++ model was hand-written (later itself
superseded by the generated `GeneratedCpp.ppm_limit_cw84_point`), mirroring
its source's sequential mutations as a `let h_L' := …; let h_R' := … h_L' …`
chain.

The expression shapes are identical across the two sources; what the proof
absorbs is purely the **control-flow representation delta**: functionalize
carries the join as inline `Cond`s inside the result tuple, the sequential
model as chained `let`s — and `(a, if c then x else y)` versus
`if c then (a, x) else (a, y)` is a propositional, not definitional,
equality. Two lines close it:

```lean
theorem ppmLimitCw84_point_equiv (h_L h_R h_in : ℝ) :
    ppmLimitCw84C h_L h_R h_in
      = Generated.ppm_limit_cw84 h_in h_L h_R := by
  simp only [ppmLimitCw84C, Generated.ppm_limit_cw84]
  split_ifs <;> rfl
```

Split on the (syntactically shared) guards; every case closes by `rfl`. One
tactic lesson worth passing on: plain `unfold` leaves the ifs buried under
binders where `split_ifs` cannot see them — unfolding via `simp only`
zeta-reduces the `let`s first. The same two-line pattern later closed the
C++-side fidelity theorem, which absorbs the same delta from the other
direction. The kernel-level theorem reuses the first kernel's `pointwise` schema
(CW84 takes no scalar argument, so the schema's scalar slot is filled with a
dummy `0` on both sides).

## The theorems and their audits

From the current build log:

```text
'Groundline.GeneratedFtn.ppm_limit_cw84' depends on axioms: [propext, Classical.choice, Quot.sound]
'Groundline.ppmLimitCw84_point_equiv' depends on axioms: [propext, Classical.choice, Quot.sound]
'Groundline.ppmLimitCw84_kernel_equiv' depends on axioms: [propext, Classical.choice, Quot.sound]
'Groundline.GeneratedCpp.ppm_limit_cw84_point' depends on axioms: [propext, Classical.choice, Quot.sound]
'generated_cpp_ppm_limit_cw84_fidelity' depends on axioms: [propext, Classical.choice, Quot.sound]
'generated_cpp_matches_generated_fortran_cw84' depends on axioms: [propext, Classical.choice, Quot.sound]
```

Proof files: `lean/groundline/Groundline/PpmLimitCw84.lean`, `Groundline/FidelityCpp.lean`.
The generated defs — including the merged-`Cond` result tuples, wide and
honest — are in `Groundline/GeneratedFtn.lean` and `Groundline/GeneratedCpp.lean`.
