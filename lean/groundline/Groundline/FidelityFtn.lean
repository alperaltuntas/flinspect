import Groundline.PpmLimitPos
import Groundline.GeneratedFtn

set_option linter.style.header false

/-!
# Fidelity: generated model ≡ hand-written model

`Groundline/GeneratedFtn.lean` is emitted by the deterministic printer
(`groundline.lean_printer`) from the *production* MOM6 with-sema dump;
`Groundline/PpmLimitPos.lean` was written by hand from the Fortran source during the
first kernel study. This theorem checks — in Lean, not by eye — that the printer's
output is the same function. `rfl` succeeding means the two definitions are
definitionally equal: the printer introduced no semantic drift whatsoever.

Together with `ppmLimitPos_point_equiv` (hand-written Fortran model
≡ hand-written C++ model), this transitively gives: **generated-from-dump
Fortran model ≡ C++ port**, with every link machine-checked.
-/

theorem generated_ppm_limit_pos_fidelity :
    Groundline.GeneratedFtn.ppm_limit_pos = Groundline.ppmLimitPosF := rfl

/-- The generated model inherits the hand-written models' equivalence with the C++ port. -/
theorem generated_matches_cpp (h_in h_L h_R h_min : ℝ) :
    Groundline.ppmLimitPosC h_L h_R h_in h_min
      = Groundline.GeneratedFtn.ppm_limit_pos h_in h_L h_R h_min := by
  rw [generated_ppm_limit_pos_fidelity]
  exact Groundline.ppmLimitPos_point_equiv h_in h_L h_R h_min
