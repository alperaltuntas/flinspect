import Mathlib.Data.Real.Basic
import Mathlib.Tactic.Ring

set_option linter.style.header false
-- Generated code keeps each expression on one line (merged-join tuples can be
-- arbitrarily wide), so the line-length style lint does not apply.
set_option linter.style.longLine false
-- Generated defs keep every parameter positionally (inout/out outputs are
-- also inputs); a kernel that never reads an output's incoming value leaves
-- its binder unused by design.
set_option linter.unusedVariables false

/-!
# GENERATED FILE — do not edit

Emitted by `groundline.lean_printer` (Track B; DESIGN §2.3) from flang with-sema
parse-tree dumps (`groundline.frontend.flang_kernel`).
Regenerate with `groundline kernel generate` (manifest: `kernels.toml`).
-/

namespace Quickstart.Generated

noncomputable section

/-- Generated from `scale_clip_acc` in `toy_kernel_ptree` (flang with-sema dump).
Outputs `(b)` — the `intent(inout)` arguments, modeled functionally over ℝ. -/
def scale_clip_acc (a b s lo : ℝ) : ℝ :=
  let w := s * a
  if w < lo then
    b + lo
  else b + w

end

end Quickstart.Generated
