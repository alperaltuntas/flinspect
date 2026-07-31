import Pilot.SeqSchema
import Pilot.Generated
import Pilot.GeneratedCpp

set_option linter.style.header false

/-!
# Track B, fourth and fifth kernels: thickness_to_dz (plain DO, rule A)

Kernel pairs (both from the 3-D `thickness_to_dz_3d` in
MOM6/src/core/MOM_interface_heights.F90 — note: `src/core`, and the
subroutine carries BOTH a do-concurrent and a plain-DO variant of each branch
under its `do_offload` guard; the plain-DO variants are the default execution
path and the ones banked here):

  Fortran:  `thickness_to_dz_3d`, loop nest 4 — the plain-DO loop of the
            Boussinesq/else branch: `dz(i,j,k) = GV%H_to_Z * h(i,j,k)`
  C++:      `MOM::thickness_to_dz_3d_boussinesq_point`
            (TIM/mom/cpp/mom_interface_heights_kernel.hpp)

  Fortran:  `thickness_to_dz_3d`, loop nest 2 — the plain-DO loop of the
            `(.not.GV%Boussinesq) .and. allocated(tv%SpV_avg)` branch:
            `dz(i,j,k) = GV%H_to_RZ * h(i,j,k) * tv%SpV_avg(i,j,k)`
  C++:      `MOM::thickness_to_dz_3d_nonboussinesq_point`

These are the first PLAIN-DO kernels banked, and the first with synthesized
component parameters (rule B): the loop-invariant scalar components
`GV%H_to_Z` / `GV%H_to_RZ` become the scalar params `h_to_z` / `h_to_rz`
(captured loop-invariantly below), and the component array
`tv%SpV_avg(i,j,k)` becomes `spv_avg`, fed per cell (`spv i`).

A plain DO asserts no iteration independence, so the Fortran side is modeled
HONESTLY as the sequential fold `foldSeq` (Pilot/SeqSchema.lean); the
kernel-level theorems then *instantiate the schema lemma*
`foldSeq_eq_pointwiseMap` — a proof, where `do concurrent` kernels lean on
the source's assertion. Per the mature pattern there are no hand-written
models: the point lemmas relate the two generated defs directly (both `rfl`).
-/

namespace TrackB

noncomputable section

/-! ## Point lemmas (both endpoints generated) -/

/-- **Point lemma, Boussinesq:** both generated bodies are `h_to_z * h` —
definitional (only the parameter orders differ: C++ (dz, h, h_to_z) vs
Fortran (h, dz, h_to_z)). -/
theorem thicknessToDzBouss_point_equiv (dz h h_to_z : ℝ) :
    GeneratedCpp.thickness_to_dz_3d_boussinesq_point dz h h_to_z
      = Generated.thickness_to_dz_3d_boussinesq h dz h_to_z := rfl

/-- **Point lemma, non-Boussinesq:** both generated bodies are
`h_to_rz * h * spv` — definitional (C++ (dz, h, spv, h_to_rz) vs Fortran
(h, dz, h_to_rz, spv_avg)). -/
theorem thicknessToDzNonBouss_point_equiv (dz h spv h_to_rz : ℝ) :
    GeneratedCpp.thickness_to_dz_3d_nonboussinesq_point dz h spv h_to_rz
      = Generated.thickness_to_dz_3d_nonboussinesq h dz h_to_rz spv := rfl

/-! ## Kernel level: honest sequential fold ≡ AMReX launch -/

/-- The Fortran plain-DO nest, modeled honestly: a sequential fold of the
generated point function over an enumeration of the index box. `dz` is
`intent(inout)` (halo cells outside the loop range keep their values — which
is exactly what `foldSeq` gives cells outside `enum`). -/
def thicknessToDzBoussLoopF {ι : Type*} [DecidableEq ι]
    (h : ι → ℝ) (h_to_z : ℝ) (dz₀ : ι → ℝ) (enum : List ι) : ι → ℝ :=
  foldSeq (fun i v => Generated.thickness_to_dz_3d_boussinesq (h i) v h_to_z)
    dz₀ enum

/-- The AMReX `ParallelFor` launch of the C++ point kernel over the box. -/
def thicknessToDzBoussLaunchC {ι : Type*}
    (h : ι → ℝ) (h_to_z : ℝ) (dz₀ : ι → ℝ) : ι → ℝ :=
  fun i => GeneratedCpp.thickness_to_dz_3d_boussinesq_point (dz₀ i) (h i) h_to_z

/-- **Kernel equivalence, Boussinesq:** for every duplicate-free, complete
enumeration of the box, the sequential Fortran loop and the AMReX launch
produce the same output array — via the schema lemma, not an assertion. -/
theorem thicknessToDzBouss_kernel_equiv {ι : Type*} [DecidableEq ι]
    (h : ι → ℝ) (h_to_z : ℝ) (dz₀ : ι → ℝ) (enum : List ι)
    (hnd : enum.Nodup) (hall : ∀ i, i ∈ enum) :
    thicknessToDzBoussLoopF h h_to_z dz₀ enum
      = thicknessToDzBoussLaunchC h h_to_z dz₀ := by
  unfold thicknessToDzBoussLoopF thicknessToDzBoussLaunchC
  rw [foldSeq_eq_pointwiseMap _ enum hnd hall dz₀]
  funext i
  exact (thicknessToDzBouss_point_equiv (dz₀ i) (h i) h_to_z).symm

/-- The non-Boussinesq Fortran plain-DO nest: the scalar component `h_to_rz`
is loop-invariant (captured), the component array `spv_avg` is read per cell
(`spv i`) — exactly rule B's model meaning. -/
def thicknessToDzNonBoussLoopF {ι : Type*} [DecidableEq ι]
    (h spv : ι → ℝ) (h_to_rz : ℝ) (dz₀ : ι → ℝ) (enum : List ι) : ι → ℝ :=
  foldSeq (fun i v =>
      Generated.thickness_to_dz_3d_nonboussinesq (h i) v h_to_rz (spv i))
    dz₀ enum

/-- The AMReX `ParallelFor` launch of the C++ point kernel over the box. -/
def thicknessToDzNonBoussLaunchC {ι : Type*}
    (h spv : ι → ℝ) (h_to_rz : ℝ) (dz₀ : ι → ℝ) : ι → ℝ :=
  fun i => GeneratedCpp.thickness_to_dz_3d_nonboussinesq_point
    (dz₀ i) (h i) (spv i) h_to_rz

/-- **Kernel equivalence, non-Boussinesq** — via the schema lemma. -/
theorem thicknessToDzNonBouss_kernel_equiv {ι : Type*} [DecidableEq ι]
    (h spv : ι → ℝ) (h_to_rz : ℝ) (dz₀ : ι → ℝ) (enum : List ι)
    (hnd : enum.Nodup) (hall : ∀ i, i ∈ enum) :
    thicknessToDzNonBoussLoopF h spv h_to_rz dz₀ enum
      = thicknessToDzNonBoussLaunchC h spv h_to_rz dz₀ := by
  unfold thicknessToDzNonBoussLoopF thicknessToDzNonBoussLaunchC
  rw [foldSeq_eq_pointwiseMap _ enum hnd hall dz₀]
  funext i
  exact (thicknessToDzNonBouss_point_equiv (dz₀ i) (h i) (spv i) h_to_rz).symm

end

end TrackB
