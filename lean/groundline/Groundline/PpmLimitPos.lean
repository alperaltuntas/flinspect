import Mathlib.Data.Real.Basic
import Mathlib.Tactic.Ring

set_option linter.style.header false

/-!
# The first kernel: PPM_limit_pos equivalence

The first kernel study (groundline DESIGN §4): hand-written Lean models of one already-
ported MOM6 kernel pair, and a machine-checked equivalence proof over ℝ.

Kernel pair:
  Fortran:  subroutine PPM_limit_pos          MOM6/src/core/MOM_continuity_PPM.F90
  C++:      MOM::ppm_limit_pos_point          TIM/mom/cpp/mom_continuity_ppm_kernel.hpp

Modeling choices (DESIGN Q5), decided here and to be recorded in DEVLOG:
  * Reals: every `real` / `amrex::Real` is ℝ (VISION D6 — algorithmic
    equivalence, not floating-point identity).
  * `intent(inout)` scalars are modeled functionally: the pair (h_L, h_R) is
    both input and result. (Logos proved fold ≡ mutating loop; both shapes are
    known-provable. Functional is the simpler Lean idiom.)
  * Each model mirrors ITS OWN source's expression shapes (Fortran `curv**2 +
    3.0*dh**2` vs C++ `curv*curv + 3*(dh*dh)`), so the equivalence theorem is
    doing real work: it absorbs exactly the algebraic differences a transcriber
    introduced, and nothing else.
  * `do concurrent (k,j,i)` and `amrex::ParallelFor(box)` are both modeled as a
    pointwise map over an abstract index type ι. `do concurrent` *asserts*
    iteration independence, which is what licenses this model; the same holds
    for ParallelFor's per-cell lambda. The schema theorem then lifts the point
    lemma to whole arrays.
-/

namespace Groundline

noncomputable section

/-! ## Point models -/

/-- Model of the loop body of Fortran `PPM_limit_pos` (per grid point).

Source (MOM_continuity_PPM.F90, the `do concurrent` body):
```
curv = 3.0*((h_L(i,j,k) + h_R(i,j,k)) - 2.0*h_in(i,j,k))
if (curv > 0.0) then
  dh = h_R(i,j,k) - h_L(i,j,k)
  if (abs(dh) < curv) then
    if (h_in(i,j,k) <= h_min) then
      h_L(i,j,k) = h_in(i,j,k) ; h_R(i,j,k) = h_in(i,j,k)
    elseif (12.0*curv*(h_in(i,j,k) - h_min) < (curv**2 + 3.0*dh**2)) then
      scale = 12.0*curv*(h_in(i,j,k) - h_min) / (curv**2 + 3.0*dh**2)
      h_L(i,j,k) = h_in(i,j,k) + scale*(h_L(i,j,k) - h_in(i,j,k))
      h_R(i,j,k) = h_in(i,j,k) + scale*(h_R(i,j,k) - h_in(i,j,k))
    endif
  endif
endif
```
Argument order follows the Fortran argument list (h_in, h_L, h_R, h_min). -/
def ppmLimitPosF (h_in h_L h_R h_min : ℝ) : ℝ × ℝ :=
  let curv := 3 * ((h_L + h_R) - 2 * h_in)
  if 0 < curv then
    let dh := h_R - h_L
    if |dh| < curv then
      if h_in ≤ h_min then
        (h_in, h_in)
      else if 12 * curv * (h_in - h_min) < curv ^ 2 + 3 * dh ^ 2 then
        let scale := 12 * curv * (h_in - h_min) / (curv ^ 2 + 3 * dh ^ 2)
        (h_in + scale * (h_L - h_in), h_in + scale * (h_R - h_in))
      else (h_L, h_R)
    else (h_L, h_R)
  else (h_L, h_R)

/-- Model of C++ `MOM::ppm_limit_pos_point` (mom_continuity_ppm_kernel.hpp).

Source:
```
Real const curv = 3.0_rt * ((h_L + h_R) - 2.0_rt * h_in);
if (curv > 0.0_rt) {
  Real const dh = h_R - h_L;
  if (amrex::Math::abs(dh) < curv) {
    if (h_in <= h_min) { h_L = h_in; h_R = h_in; }
    else if (12.0_rt * curv * (h_in - h_min) < ((curv * curv) + (3.0_rt * (dh * dh)))) {
      Real const scale = 12.0_rt * curv * (h_in - h_min) / ((curv * curv) + (3.0_rt * (dh * dh)));
      h_L = h_in + scale * (h_L - h_in);
      h_R = h_in + scale * (h_R - h_in);
    }
  }
}
```
Argument order follows the C++ parameter list (h_L, h_R, h_in, h_min). -/
def ppmLimitPosC (h_L h_R h_in h_min : ℝ) : ℝ × ℝ :=
  let curv := 3 * ((h_L + h_R) - 2 * h_in)
  if 0 < curv then
    let dh := h_R - h_L
    if |dh| < curv then
      if h_in ≤ h_min then
        (h_in, h_in)
      else if 12 * curv * (h_in - h_min) < curv * curv + 3 * (dh * dh) then
        let scale := 12 * curv * (h_in - h_min) / (curv * curv + 3 * (dh * dh))
        (h_in + scale * (h_L - h_in), h_in + scale * (h_R - h_in))
      else (h_L, h_R)
    else (h_L, h_R)
  else (h_L, h_R)

/-! ## The point lemma -/

/-- **Point lemma:** the C++ port computes the same function over ℝ as the
Fortran original, for every input. The proof has to absorb exactly the
transcription deltas: `curv**2 + 3.0*dh**2` (Fortran) vs
`(curv*curv) + (3.0*(dh*dh))` (C++), in both the guard and the divisor. -/
theorem ppmLimitPos_point_equiv (h_in h_L h_R h_min : ℝ) :
    ppmLimitPosC h_L h_R h_in h_min = ppmLimitPosF h_in h_L h_R h_min := by
  unfold ppmLimitPosC ppmLimitPosF
  have hsq : ∀ c d : ℝ, c * c + 3 * (d * d) = c ^ 2 + 3 * d ^ 2 := by
    intro c d; ring
  simp only [hsq]

/-! ## The iteration schema -/

/-- Both `do concurrent (k=1:nz, j=jis:jie, i=iis:iie)` and
`amrex::ParallelFor(box, ...)` mean: apply the point function at every index of
the box, each cell's result depending only on that cell's inputs. `ι` abstracts
the index box (concretely `Fin ni × Fin nj × Fin nk`). -/
def pointwise {ι : Type*} (f : ℝ → ℝ → ℝ → ℝ → ℝ × ℝ)
    (h_in h_L h_R : ι → ℝ) (h_min : ℝ) : (ι → ℝ) × (ι → ℝ) :=
  (fun i => (f (h_in i) (h_L i) (h_R i) h_min).1,
   fun i => (f (h_in i) (h_L i) (h_R i) h_min).2)

/-- The Fortran subroutine over the whole box (arrays as functions on ι). -/
def ppmLimitPosLoopF {ι : Type*} (h_in h_L h_R : ι → ℝ) (h_min : ℝ) :
    (ι → ℝ) × (ι → ℝ) :=
  pointwise ppmLimitPosF h_in h_L h_R h_min

/-- The AMReX kernel launch over the whole box (the C++ point function takes
(h_L, h_R, h_in, h_min), so adapt the argument order). -/
def ppmLimitPosLaunchC {ι : Type*} (h_in h_L h_R : ι → ℝ) (h_min : ℝ) :
    (ι → ℝ) × (ι → ℝ) :=
  pointwise (fun a b c d => ppmLimitPosC b c a d) h_in h_L h_R h_min

/-- **Kernel equivalence:** the ported AMReX launch and the legacy Fortran
loop nest produce identical output arrays on every box, for all inputs. -/
theorem ppmLimitPos_kernel_equiv {ι : Type*}
    (h_in h_L h_R : ι → ℝ) (h_min : ℝ) :
    ppmLimitPosLaunchC h_in h_L h_R h_min = ppmLimitPosLoopF h_in h_L h_R h_min := by
  unfold ppmLimitPosLaunchC ppmLimitPosLoopF pointwise
  simp only [ppmLimitPos_point_equiv]

end

end Groundline
