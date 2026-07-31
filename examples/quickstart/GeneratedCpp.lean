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

Emitted by `flinspect.lean_printer` (Track B; DESIGN §2.3) from clang JSON ASTs
(`flinspect.frontend.clang_kernel`).
Regenerate with `flinspect kernel generate` (manifest: `kernels.toml`).

Extraction provenance (pinned):
  clang version 21.0.0git (https://github.com/llvm/llvm-project.git bb982e733cfcda7e4cfb0583544f68af65211ed1)
  -std=c++20 -fsyntax-only -Xclang -ast-dump=json -Xclang -ast-dump-filter
-/

namespace Quickstart.GeneratedCpp

noncomputable section

/-- Generated from `scale_clip_acc_point` in `toy_kernel.hpp` (clang JSON AST).
Outputs `(b)` — the `intent(inout)` arguments, modeled functionally over ℝ. -/
def scale_clip_acc_point (b a s lo : ℝ) : ℝ :=
  let w := s * a
  if w < lo then
    b + lo
  else b + w

end

end Quickstart.GeneratedCpp
