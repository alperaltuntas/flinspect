# The Lean project

All proofs live in `lean/pilot/` — a `lake` project (Lean 4, Mathlib
dependency) named for the Track B pilot it grew out of. `lake build` checks
everything; `groundline kernel verify` runs it as its final tier when the
manifest sets `[lean] lake_dir`.

## Layout

| File | Role |
|---|---|
| `Pilot/Generated.lean` | **Generated** — the five Fortran-side defs, emitted by `groundline kernel generate`; do not edit |
| `Pilot/GeneratedCpp.lean` | **Generated** — the five C++-side defs, with the pinned clang invocation stamped in the header; do not edit |
| `Pilot/PpmLimitPos.lean` | The pilot: hand-written models `ppmLimitPosF`/`ppmLimitPosC`, the point lemma, the `pointwise` iteration schema, the kernel theorem |
| `Pilot/PpmLimitCw84.lean` | Second kernel: hand-written C++ model, point lemma proved directly against the generated Fortran def, kernel theorem |
| `Pilot/Fidelity.lean` | `generated_ppm_limit_pos_fidelity` (**`rfl`**) + the transitive `generated_matches_cpp` |
| `Pilot/FidelityCpp.lean` | C++-side fidelity theorems + the fully-mechanical chain theorems `generated_cpp_matches_generated_fortran_{pos,cw84}` |
| `Pilot/SeqSchema.lean` | The plain-DO schema: `seqStep`, `foldSeq`, `pointwiseMap`, `foldSeq_frame`, `foldSeq_apply_of_mem`, **`foldSeq_eq_pointwiseMap`** |
| `Pilot/EdgeThicknessUpwind.lean` | Third kernel: both endpoints generated; point lemma `rfl`; do-concurrent license |
| `Pilot/ThicknessToDz.lean` | Fourth and fifth kernels: honest `foldSeq` models, schema-lemma instantiation |
| `Pilot/AxiomsAudit.lean` | `#print axioms` on **every** Track B declaration ([the audit](../concepts/trusted-base.md#the-axioms-audit)) |
| `Pilot.lean` | Root import list |

## The two schemas (iteration licenses)

- **`pointwise`** (`PpmLimitPos.lean`) — arrays as functions on an abstract
  index type ι; both `do concurrent (k,j,i)` and `amrex::ParallelFor(box)`
  are modeled as the pointwise map of the point function. License: the
  source's `do concurrent` independence assertion. Kernels without a scalar
  argument fill the schema's scalar slot with a dummy `0` (the CW84 idiom).
- **`foldSeq` + `foldSeq_eq_pointwiseMap`** (`SeqSchema.lean`) — the honest
  sequential fold for plain-DO kernels, equated with the pointwise map by
  proof, once and for all. See
  [the thickness_to_dz case study](../case-studies/thickness-to-dz.md).

## Conventions

- **No hand-written models for new kernels** (the mature pattern): point
  lemmas relate the two *generated* defs directly. The pilot-era hand models
  remain as machine-checked, human-readable references — no longer
  load-bearing.
- **Targeted Mathlib imports only** (`Mathlib.Data.Real.Basic`,
  `Mathlib.Tactic.Ring`, `Mathlib.Logic.Function.Basic`,
  `Mathlib.Data.List.Basic`) — a blanket `import Mathlib` costs minutes per
  file on a networked filesystem.
- **Every new declaration gets an `#print axioms` line** in
  `AxiomsAudit.lean` before merging. Kernel-side declarations must report
  exactly `[propext, Classical.choice, Quot.sound]`; the polymorphic schema
  declarations report strict subsets (documented in the audit file); anything
  beyond the three — in particular `sorryAx` — is a trusted-base violation.
- **Generated files are regenerated, never edited**; `groundline kernel
  verify`'s byte-diff enforces it.
- Mathlib's style linters expect Mathlib file headers; project files disable
  that lint per-file (`set_option linter.style.header false`) — this is
  project code, not a Mathlib contribution.

## Toolchain

`lean-toolchain` pins the Lean version; `lake-manifest.json` pins Mathlib.
After installing [elan](https://github.com/leanprover/elan), run
`lake exe cache get` before the first `lake build` — the Mathlib binary cache
(thousands of prebuilt modules) is the difference between minutes and hours.
A full project build is currently 798 jobs.
