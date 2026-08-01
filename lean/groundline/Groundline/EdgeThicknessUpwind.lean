import Groundline.PpmLimitPos
import Groundline.GeneratedFtn
import Groundline.GeneratedCpp

set_option linter.style.header false

/-!
# The third kernel: upwind edge thickness (inline do concurrent)

Kernel pair:
  Fortran:  `zonal_edge_thickness`, loop nest 1 — the in-subset
            `do concurrent` under `if (CS%upwind_1st)`
            (MOM6/src/core/MOM_continuity_PPM.F90)
  C++:      `MOM::edge_thickness_upwind_point`
            (TIM/mom/cpp/mom_continuity_ppm_kernel.hpp)

The first kernel banked through **inline-loop addressing**: the Fortran twin
is not a standalone subroutine but a loop inside `zonal_edge_thickness`,
addressed by its source-order nest ordinal; the generated def's name
(`edge_thickness_upwind`) is supplied by the driver, which records the
pairing. Per the mature pattern there is NO hand-written model — the point
lemma relates the two generated defs directly, and here it is `rfl`: both
sides are `(h_in, h_in)`.

The loop is a `do concurrent`, so the license for the pointwise model is the
source's own independence assertion, exactly as for the first kernels — contrast
`Groundline/ThicknessToDz.lean`, where the plain-DO kernels get a *proof* (the
schema lemma) instead of an assertion.

`meridional_edge_thickness` contains the textually identical `h_S`/`h_N`
loop; the function proved here is the same.
-/

namespace Groundline

noncomputable section

/-! ## The point lemma (both endpoints generated) -/

/-- **Point lemma:** the C++ port computes the same function over ℝ as the
model extracted from the Fortran loop. Both generated bodies are
`(h_in, h_in)` — the equality is definitional. -/
theorem edgeThicknessUpwind_point_equiv (h_W h_E h_in : ℝ) :
    GeneratedCpp.edge_thickness_upwind_point h_W h_E h_in
      = GeneratedFtn.edge_thickness_upwind h_in h_W h_E := rfl

/-! ## The iteration schema -/

/-- The Fortran `do concurrent (k,j,i)` nest over the whole box, with the
generated point function. No scalar argument, so `pointwise`'s scalar slot is
filled with a dummy `0` on both sides (the CW84 idiom). -/
def edgeThicknessUpwindLoopF {ι : Type*} (h_in h_W h_E : ι → ℝ) :
    (ι → ℝ) × (ι → ℝ) :=
  pointwise (fun a b c _ => GeneratedFtn.edge_thickness_upwind a b c)
    h_in h_W h_E 0

/-- The AMReX `ParallelFor` launch over the whole box (the C++ point function
takes (h_L, h_R, h_in), so adapt the argument order). -/
def edgeThicknessUpwindLaunchC {ι : Type*} (h_in h_W h_E : ι → ℝ) :
    (ι → ℝ) × (ι → ℝ) :=
  pointwise (fun a b c _ => GeneratedCpp.edge_thickness_upwind_point b c a)
    h_in h_W h_E 0

/-- **Kernel equivalence:** the ported AMReX launch and the legacy Fortran
loop nest produce identical output arrays on every box, for all inputs. -/
theorem edgeThicknessUpwind_kernel_equiv {ι : Type*} (h_in h_W h_E : ι → ℝ) :
    edgeThicknessUpwindLaunchC h_in h_W h_E
      = edgeThicknessUpwindLoopF h_in h_W h_E := by
  unfold edgeThicknessUpwindLaunchC edgeThicknessUpwindLoopF pointwise
  simp only [edgeThicknessUpwind_point_equiv]

end

end Groundline
