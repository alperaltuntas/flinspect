import Groundline.PpmLimitPos
import Groundline.GeneratedFtn

set_option linter.style.header false

/-!
# The second kernel: PPM_limit_CW84 equivalence

Kernel pair:
  Fortran:  subroutine PPM_limit_CW84        MOM6/src/core/MOM_continuity_PPM.F90
  C++:      MOM::ppm_limit_cw84_point        TIM/mom/cpp/mom_continuity_ppm_kernel.hpp

Unlike the first kernel (`PpmLimitPos.lean`), there is NO hand-written Fortran model
here — the mature pattern is to prove the point lemma directly
against the GENERATED model (`Groundline.GeneratedFtn.ppm_limit_cw84`, emitted by the
deterministic printer from the production with-sema dump), so the printer's
output is on the trusted path rather than checked against a second
transcription by eye.

Only the C++ side is hand-written, mirroring its own source's shapes: the
`h_i = h_in` copy, the locals RLdiff/RLmean/FunFac/RLdiff2, and — the part
that makes this kernel worth banking — the two *sequential* guarded
assignments at the end. The second guard's RHS reads `h_L`, which the first
may have just updated; functionally that is the `let h_L' := ...; let h_R' :=
... h_L' ...` chain below, and on the generated side it is the merged
`Cond` state threaded by `functionalize`.
-/

namespace Groundline

noncomputable section

/-! ## The C++ point model -/

/-- Model of C++ `MOM::ppm_limit_cw84_point` (mom_continuity_ppm_kernel.hpp).

Source:
```
Real h_i = h_in;
if ( ( h_R - h_i ) * ( h_i - h_L ) <= 0.0_rt ) {
    h_L = h_i;
    h_R = h_i;
} else {
    Real const RLdiff  = h_R - h_L;
    Real const RLmean  = 0.5_rt * ( h_R + h_L );
    Real const FunFac  = 6.0_rt * RLdiff * ( h_i - RLmean );
    Real const RLdiff2 = RLdiff * RLdiff;

    if ( FunFac >  RLdiff2 ) h_L = 3.0_rt * h_i - 2.0_rt * h_R;
    if ( FunFac < -RLdiff2 ) h_R = 3.0_rt * h_i - 2.0_rt * h_L;
}
```
Argument order follows the C++ parameter list (h_L, h_R, h_in). The two
trailing guarded assignments are sequential mutations: the second reads the
possibly-updated `h_L`, hence `h_L'` in `h_R'`'s definition. -/
def ppmLimitCw84C (h_L h_R h_in : ℝ) : ℝ × ℝ :=
  let h_i := h_in
  if (h_R - h_i) * (h_i - h_L) ≤ 0 then
    (h_i, h_i)
  else
    let RLdiff := h_R - h_L
    let RLmean := 0.5 * (h_R + h_L)
    let FunFac := 6 * RLdiff * (h_i - RLmean)
    let RLdiff2 := RLdiff * RLdiff
    let h_L' := if FunFac > RLdiff2 then 3 * h_i - 2 * h_R else h_L
    let h_R' := if FunFac < -RLdiff2 then 3 * h_i - 2 * h_L' else h_R
    (h_L', h_R')

/-! ## The point lemma (directly against the generated model) -/

/-- **Point lemma:** the C++ port computes the same function over ℝ as the
model generated from the Fortran dump. The expression shapes are identical
across the two sources; what the proof absorbs is the *control-flow
representation* delta — the generated side carries the join as inline `Cond`s
(if-expressions inside the result tuple), the C++ model as sequential `let`s —
so a case split on the (shared) guards closes every branch by `rfl`. -/
theorem ppmLimitCw84_point_equiv (h_L h_R h_in : ℝ) :
    ppmLimitCw84C h_L h_R h_in
      = GeneratedFtn.ppm_limit_cw84 h_in h_L h_R := by
  -- `simp only` with the def names unfolds them AND zeta-reduces the `let`s
  -- (plain `unfold` leaves the ifs buried under `have` binders, where
  -- `split_ifs` cannot see them).
  simp only [ppmLimitCw84C, GeneratedFtn.ppm_limit_cw84]
  split_ifs <;> rfl

/-! ## The iteration schema -/

/-- The Fortran `do concurrent (k,j,i)` nest over the whole box, modeled with
the GENERATED point function. CW84 takes no scalar argument, so `pointwise`'s
scalar slot is filled with a dummy `0` (ignored by the lambda) on both sides. -/
def ppmLimitCw84LoopF {ι : Type*} (h_in h_L h_R : ι → ℝ) :
    (ι → ℝ) × (ι → ℝ) :=
  pointwise (fun a b c _ => GeneratedFtn.ppm_limit_cw84 a b c) h_in h_L h_R 0

/-- The AMReX `ParallelFor` launch over the whole box (the C++ point function
takes (h_L, h_R, h_in), so adapt the argument order). -/
def ppmLimitCw84LaunchC {ι : Type*} (h_in h_L h_R : ι → ℝ) :
    (ι → ℝ) × (ι → ℝ) :=
  pointwise (fun a b c _ => ppmLimitCw84C b c a) h_in h_L h_R 0

/-- **Kernel equivalence:** the ported AMReX launch and the legacy Fortran
loop nest produce identical output arrays on every box, for all inputs. -/
theorem ppmLimitCw84_kernel_equiv {ι : Type*} (h_in h_L h_R : ι → ℝ) :
    ppmLimitCw84LaunchC h_in h_L h_R = ppmLimitCw84LoopF h_in h_L h_R := by
  unfold ppmLimitCw84LaunchC ppmLimitCw84LoopF pointwise
  simp only [ppmLimitCw84_point_equiv]

end

end Groundline
