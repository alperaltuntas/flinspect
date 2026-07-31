# Track B quickstart — a toy kernel pair, end to end

This directory is a self-contained instance of the Track B kernel-verification
pipeline: a tiny Fortran `do concurrent` point kernel and its C++ point-function
twin, banked in a `kernels.toml` manifest and rendered into two generated Lean
modules. It exists to prove (and demo) portability: everything below works in a
bare clone of flinspect, anywhere — no MOM6 corpus, no AMReX, no /glade paths.

## What's here

| File | Role |
|---|---|
| `toy_kernel.f90` | The Fortran kernel (`scale_clip_acc`) — scale, clip, accumulate |
| `toy_kernel_ptree` | Its **committed** with-sema flang dump (see `PROVENANCE`), so the Fortran side needs no flang install |
| `toy_kernel.hpp` | The C++ twin (`scale_clip_acc_point`) — standalone: its own `using Real = double;`, no AMReX/MPI includes |
| `kernels.toml` | The manifest pairing them and pinning outputs/namespaces |
| `Generated.lean`, `GeneratedCpp.lean` | The committed generated models (what `flinspect kernel generate` writes) |

## Walkthrough

Install flinspect (`pip install -e .` from the repo root), `cd` into this
directory — the CLI picks up `./kernels.toml` automatically (or pass
`--kernels examples/quickstart/kernels.toml` from anywhere; a
`FLINSPECT_KERNELS` env var works too).

```console
$ flinspect kernel list
manifest: .../examples/quickstart/kernels.toml  (1 kernel(s))
scale_clip_acc
    fortran: subroutine 'scale_clip_acc' in toy_kernel_ptree  [ok]
    cpp:     function 'scale_clip_acc_point' in toy_kernel.hpp  [ok]
...
```

Print one kernel's generated Lean defs — both sides, straight from the sources
(the C++ side is skipped with a note if `clang++` is not on `PATH`):

```console
$ flinspect kernel show scale_clip_acc
def scale_clip_acc (a b s lo : ℝ) : ℝ :=
  let w := s * a
  if w < lo then
    b + lo
  else b + w
...
def scale_clip_acc_point (b a s lo : ℝ) : ℝ :=
  let w := s * a
  if w < lo then
    b + lo
  else b + w
```

The two bodies coming out identical *is* the point — for real kernels (see
`examples/turbo-stack.kernels.toml`, the production MOM6 ⇄ TIM instance) the
remaining gap is closed by a machine-checked Lean proof.

Regenerate the committed modules, and check them:

```console
$ flinspect kernel generate     # rewrites Generated.lean / GeneratedCpp.lean
$ flinspect kernel verify       # byte-diffs a fresh regeneration against them
ok [fortran]: Generated.lean matches a fresh regeneration
ok [cpp]: GeneratedCpp.lean matches a fresh regeneration
```

`verify` exits non-zero on drift — that (plus `lake build`, for manifests that
set `[lean] lake_dir`, like the production one) is Track B's CI gate.

## Notes

- The toy stays inside the supported kernel subset (refuse-don't-guess:
  anything outside it raises `UnsupportedConstruct` rather than guessing).
- Regenerating `GeneratedCpp.lean` re-stamps your local clang version into its
  header comment; the defs themselves are byte-stable across machines.
- To regenerate the committed dump after editing `toy_kernel.f90`:
  `flang -fc1 -fdebug-dump-parse-tree toy_kernel.f90 > toy_kernel_ptree`
  (and update `PROVENANCE`, mirroring `tests/f90`'s convention).
