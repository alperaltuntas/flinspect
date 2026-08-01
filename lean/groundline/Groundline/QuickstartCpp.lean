import Mathlib.Data.Real.Basic
import Mathlib.Tactic.Ring

set_option linter.style.header false
-- Generated expressions stay on one line, however wide.
set_option linter.style.longLine false
-- Outputs are also inputs; a kernel may never read an output's incoming value.
set_option linter.unusedVariables false

/-!
# GENERATED FILE — do not edit

Emitted by `groundline.lean_printer` from clang JSON ASTs
(`groundline.frontend.clang_kernel`).
Regenerate with `groundline kernel generate` (manifest: `kernels.toml`).

Extraction provenance (pinned):
  clang version 21.0.0git (https://github.com/llvm/llvm-project.git bb982e733cfcda7e4cfb0583544f68af65211ed1)
  -std=c++20 -fsyntax-only -Xclang -ast-dump=json -Xclang -ast-dump-filter
-/

namespace Quickstart.GeneratedCpp

noncomputable section

/-- Generated from `scale_clip_acc_point` in `toy_kernel.cpp` (clang JSON AST).
Outputs `(b)` — the `intent(inout)` arguments, modeled functionally over ℝ. -/
def scale_clip_acc_point (b a s lo : ℝ) : ℝ :=
  let w := s * a
  if w < lo then
    b + lo
  else b + w

end

end Quickstart.GeneratedCpp
