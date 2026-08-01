import Mathlib.Data.Real.Basic
import Mathlib.Tactic.Ring

set_option linter.style.header false
-- Generated expressions stay on one line, however wide.
set_option linter.style.longLine false
-- Outputs are also inputs; a kernel may never read an output's incoming value.
set_option linter.unusedVariables false

/-!
# GENERATED FILE — do not edit

Emitted by `groundline.lean_printer` from flang with-sema
parse-tree dumps (`groundline.frontend.flang_kernel`).
Regenerate with `groundline kernel generate` (manifest: `kernels.toml`).
-/

namespace Quickstart.GeneratedFtn

noncomputable section

/-- Generated from `scale_clip_acc` in `toy_kernel_ptree` (flang with-sema dump).
Outputs `(b)` — the `intent(inout)` arguments, modeled functionally over ℝ. -/
def scale_clip_acc (a b s lo : ℝ) : ℝ :=
  let w := s * a
  if w < lo then
    b + lo
  else b + w

/-- Generated from `scale_clip_acc_loop` in `toy_kernel_ptree` (flang with-sema dump).
Outputs `(b)` — the `intent(inout)` arguments, modeled functionally over ℝ. -/
def scale_clip_acc_loop (a b s lo : ℝ) : ℝ :=
  let w := s * a
  if w < lo then
    b + lo
  else b + w

end

end Quickstart.GeneratedFtn
