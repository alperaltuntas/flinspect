import Pilot.PpmLimitCw84
import Pilot.Fidelity
import Pilot.GeneratedCpp

set_option linter.style.header false

/-!
# Fidelity, C++ side: generated model ≡ hand-written model

`Pilot/GeneratedCpp.lean` is emitted by the deterministic printer
(`groundline.lean_printer`) from clang JSON ASTs of the *production* TIM kernel
header (`groundline.frontend.clang_kernel`); `ppmLimitPosC` / `ppmLimitCw84C`
were written by hand from the C++ source during the pilot. These theorems
check — in Lean, not by eye — that the printer's output is the same function,
which turns the hand-written C++ models from load-bearing links into verified
references.

Two proof shapes, and why they differ:

* `ppm_limit_pos_point` — **`rfl`**: the two definitions are definitionally
  equal (the printer introduced no drift; source parentheses and `curv > 0`
  vs `0 < curv` are notation-level).
* `ppm_limit_cw84_point` — the same *control-flow representation* delta the
  Fortran-side proof (`ppmLimitCw84_point_equiv`) absorbs: `functionalize`
  carries CW84's sequential guarded pair as merged inline `Cond`s inside the
  result tuple, while the hand model mirrors the mutation order as a
  `let h_L' := ...; let h_R' := ... h_L' ...` chain. `(a, if c then x else y)`
  and `if c then (a, x) else (a, y)` are propositionally, not definitionally,
  equal — so a case split on the (syntactically shared) guards closes every
  branch by `rfl`, exactly as in `PpmLimitCw84.lean`.

## The fully-mechanical chain

With both fidelity theorems in hand, the transitive theorems at the bottom
relate the two GENERATED models directly: generated-C++ ≡ generated-Fortran,
every link machine-checked and both endpoints machine-produced —
dump → Lean is mechanical on both sides of the equivalence.
-/

/-- The printed C++ model of `ppm_limit_pos_point` is definitionally the
pilot's hand-written `ppmLimitPosC`. -/
theorem generated_cpp_ppm_limit_pos_fidelity :
    TrackB.GeneratedCpp.ppm_limit_pos_point = TrackB.ppmLimitPosC := rfl

/-- The printed C++ model of `ppm_limit_cw84_point` equals the hand-written
`ppmLimitCw84C` — pointwise, absorbing the sequential-lets vs merged-`Cond`s
representation delta (see the module docstring). -/
theorem generated_cpp_ppm_limit_cw84_fidelity (h_L h_R h_in : ℝ) :
    TrackB.GeneratedCpp.ppm_limit_cw84_point h_L h_R h_in
      = TrackB.ppmLimitCw84C h_L h_R h_in := by
  simp only [TrackB.GeneratedCpp.ppm_limit_cw84_point, TrackB.ppmLimitCw84C]
  split_ifs <;> rfl

/-- **Chain, PPM_limit_pos:** generated-from-clang C++ model ≡
generated-from-flang Fortran model — both sides machine-produced. -/
theorem generated_cpp_matches_generated_fortran_pos (h_in h_L h_R h_min : ℝ) :
    TrackB.GeneratedCpp.ppm_limit_pos_point h_L h_R h_in h_min
      = TrackB.Generated.ppm_limit_pos h_in h_L h_R h_min := by
  rw [generated_cpp_ppm_limit_pos_fidelity]
  exact generated_matches_cpp h_in h_L h_R h_min

/-- **Chain, PPM_limit_CW84:** generated-from-clang C++ model ≡
generated-from-flang Fortran model — both sides machine-produced. -/
theorem generated_cpp_matches_generated_fortran_cw84 (h_in h_L h_R : ℝ) :
    TrackB.GeneratedCpp.ppm_limit_cw84_point h_L h_R h_in
      = TrackB.Generated.ppm_limit_cw84 h_in h_L h_R := by
  rw [generated_cpp_ppm_limit_cw84_fidelity]
  exact TrackB.ppmLimitCw84_point_equiv h_L h_R h_in
