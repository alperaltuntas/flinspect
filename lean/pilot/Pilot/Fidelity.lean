import Pilot.PpmLimitPos
import Pilot.Generated

set_option linter.style.header false

/-!
# Fidelity: generated model ≡ hand-written model

`Pilot/Generated.lean` is emitted by the deterministic printer
(`groundline.lean_printer`) from the *production* MOM6 with-sema dump;
`Pilot/PpmLimitPos.lean` was written by hand from the Fortran source during the
Track B pilot. This theorem checks — in Lean, not by eye — that the printer's
output is the same function. `rfl` succeeding means the two definitions are
definitionally equal: the printer introduced no semantic drift whatsoever.

Together with the pilot's `ppmLimitPos_point_equiv` (hand-written Fortran model
≡ hand-written C++ model), this transitively gives: **generated-from-dump
Fortran model ≡ C++ port**, with every link machine-checked.
-/

theorem generated_ppm_limit_pos_fidelity :
    TrackB.Generated.ppm_limit_pos = TrackB.ppmLimitPosF := rfl

/-- The generated model inherits the pilot's equivalence with the C++ port. -/
theorem generated_matches_cpp (h_in h_L h_R h_min : ℝ) :
    TrackB.ppmLimitPosC h_L h_R h_in h_min
      = TrackB.Generated.ppm_limit_pos h_in h_L h_R h_min := by
  rw [generated_ppm_limit_pos_fidelity]
  exact TrackB.ppmLimitPos_point_equiv h_in h_L h_R h_min
