import Pilot.PpmLimitPos
import Pilot.PpmLimitCw84
import Pilot.Fidelity
import Pilot.FidelityCpp

set_option linter.style.header false

/-!
# Axioms audit (trusted-base check, VISION D6)

`#print axioms` on each theorem must list nothing beyond Lean/Mathlib's three
standard axioms (`propext`, `Classical.choice`, `Quot.sound`) — in particular
no `sorryAx`. The output is checked by eye in the build log.
-/

#print axioms TrackB.ppmLimitPos_point_equiv
#print axioms TrackB.ppmLimitPos_kernel_equiv

#print axioms TrackB.Generated.ppm_limit_pos
#print axioms generated_ppm_limit_pos_fidelity
#print axioms generated_matches_cpp

#print axioms TrackB.Generated.ppm_limit_cw84
#print axioms TrackB.ppmLimitCw84_point_equiv
#print axioms TrackB.ppmLimitCw84_kernel_equiv

#print axioms TrackB.GeneratedCpp.ppm_limit_pos_point
#print axioms TrackB.GeneratedCpp.ppm_limit_cw84_point
#print axioms generated_cpp_ppm_limit_pos_fidelity
#print axioms generated_cpp_ppm_limit_cw84_fidelity
#print axioms generated_cpp_matches_generated_fortran_pos
#print axioms generated_cpp_matches_generated_fortran_cw84
