import Groundline.QuickstartFtn
import Groundline.QuickstartCpp

set_option linter.style.header false

/-!
# The quickstart equivalence theorems

`Groundline/QuickstartFtn.lean` and `Groundline/QuickstartCpp.lean` are the
quickstart's generated models, written by `groundline kernel generate` from
`examples/quickstart/kernels.toml`. This file holds the theorems relating
them; `groundline kernel verify` re-checks it via `lake build`, and the
quickstart page of the manual walks through it.
-/

namespace Quickstart

/-- The point pair: the C++ port computes the same function as the Fortran
subroutine, on every input. `rfl` means the two generated definitions are
definitionally equal — Lean's kernel sees them as the same function by
unfolding alone. -/
theorem scale_clip_acc_equiv (a b s lo : ℝ) :
    GeneratedCpp.scale_clip_acc_point b a s lo
      = GeneratedFtn.scale_clip_acc a b s lo := rfl

/-- The loop version's per-point body (extracted under `pointize = true`)
is the same function as the standalone point subroutine. -/
theorem scale_clip_acc_loop_equiv (a b s lo : ℝ) :
    GeneratedFtn.scale_clip_acc_loop a b s lo
      = GeneratedFtn.scale_clip_acc a b s lo := rfl

end Quickstart
