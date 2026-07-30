import Pilot.PpmLimitPos

set_option linter.style.header false

/-!
# Axioms audit (trusted-base check, VISION D6)

`#print axioms` on each theorem must list nothing beyond Lean/Mathlib's three
standard axioms (`propext`, `Classical.choice`, `Quot.sound`) — in particular
no `sorryAx`. The output is checked by eye in the build log.
-/

#print axioms TrackB.ppmLimitPos_point_equiv
#print axioms TrackB.ppmLimitPos_kernel_equiv
