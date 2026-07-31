import Mathlib.Data.Real.Basic
import Mathlib.Tactic.Ring

set_option linter.style.header false

/-!
# GENERATED FILE — do not edit

Emitted by `flinspect.lean_printer` (Track B; DESIGN §2.3) from flang with-sema
parse-tree dumps. Regenerate with `lean/pilot/generate.py`. Fidelity against the
hand-written pilot models is machine-checked in `Pilot/Fidelity.lean`.
-/

namespace TrackB.Generated

noncomputable section

/-- Generated from `ppm_limit_pos` in `MOM6/MOM_continuity_PPM.o_ptree` (flang with-sema dump).
Outputs `(h_l, h_r)` — the `intent(inout)` arguments, modeled functionally over ℝ. -/
def ppm_limit_pos (h_in h_l h_r h_min : ℝ) : ℝ × ℝ :=
  let curv := 3 * ((h_l + h_r) - 2 * h_in)
  if curv > 0 then
    let dh := h_r - h_l
    if |dh| < curv then
      if h_in ≤ h_min then
        (h_in, h_in)
      else if 12 * curv * (h_in - h_min) < (curv ^ 2 + 3 * dh ^ 2) then
        let scale := 12 * curv * (h_in - h_min) / (curv ^ 2 + 3 * dh ^ 2)
        (h_in + scale * (h_l - h_in), h_in + scale * (h_r - h_in))
      else (h_l, h_r)
    else (h_l, h_r)
  else (h_l, h_r)

end

end TrackB.Generated
