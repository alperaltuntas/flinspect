import Pilot.PpmLimitPos
import Pilot.PpmLimitCw84
import Pilot.Fidelity
import Pilot.FidelityCpp
import Pilot.SeqSchema
import Pilot.EdgeThicknessUpwind
import Pilot.ThicknessToDz

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

-- The plain-DO schema (Pilot/SeqSchema.lean). The polymorphic defs and the
-- structural-induction proofs use no classical reasoning, so these may report
-- a strict SUBSET of the three standard axioms — anything beyond them (in
-- particular sorryAx) is still a trusted-base violation.
#print axioms TrackB.foldSeq
#print axioms TrackB.pointwiseMap
#print axioms TrackB.foldSeq_frame
#print axioms TrackB.foldSeq_apply_of_mem
#print axioms TrackB.foldSeq_eq_pointwiseMap

#print axioms TrackB.Generated.edge_thickness_upwind
#print axioms TrackB.GeneratedCpp.edge_thickness_upwind_point
#print axioms TrackB.edgeThicknessUpwind_point_equiv
#print axioms TrackB.edgeThicknessUpwind_kernel_equiv

#print axioms TrackB.Generated.thickness_to_dz_3d_boussinesq
#print axioms TrackB.GeneratedCpp.thickness_to_dz_3d_boussinesq_point
#print axioms TrackB.thicknessToDzBouss_point_equiv
#print axioms TrackB.thicknessToDzBouss_kernel_equiv

#print axioms TrackB.Generated.thickness_to_dz_3d_nonboussinesq
#print axioms TrackB.GeneratedCpp.thickness_to_dz_3d_nonboussinesq_point
#print axioms TrackB.thicknessToDzNonBouss_point_equiv
#print axioms TrackB.thicknessToDzNonBouss_kernel_equiv
