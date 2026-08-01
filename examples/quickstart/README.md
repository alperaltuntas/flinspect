# groundline quickstart — a toy kernel pair, end to end

This directory is a self-contained instance of the groundline
kernel-verification pipeline: a tiny Fortran point kernel and its C++ port,
paired in a `kernels.toml` manifest, rendered into two generated Lean
modules, and related by a machine-checked theorem. Everything here works in
a bare clone of groundline, anywhere — no site paths, no external libraries.
Both sources are standalone files, so each side's compiler runs on demand:
`flang` on `PATH` for the Fortran side, `clang++` for the C++ side.

**The manual's [Quickstart page](https://alperaltuntas.github.io/groundline/quickstart/)
is the guided walkthrough of this directory** — with real, captured output
for every step. The short version below is just enough to orient a reader
browsing the repo.

## What's here

| File | Role |
|---|---|
| `toy_kernel.f90` | The Fortran side: `scale_clip_acc`, one grid point |
| `toy_kernel.cpp` | The C++ port (`scale_clip_acc_point`) — standalone, plain `double`, no includes |
| `toy_kernel_loop.f90` | The same update as a loop over a column — the quickstart's closing section pairs it under an explicit `pointize = true` license |
| `kernels.toml` | The manifest pairing the point kernels; both sides in source mode |

The generated Lean modules and the equivalence theorem live in the
repository's Lean project — `lean/groundline/Groundline/QuickstartFtn.lean`,
`QuickstartCpp.lean` (generated; do not edit) and `QuickstartEquiv.lean`
(the theorem, a one-line `rfl`).

## The four commands

From this directory (the CLI picks up `./kernels.toml` automatically):

```console
$ groundline kernel list        # what the manifest declares, with status
$ groundline kernel show NAME   # print one kernel's generated Lean, both sides
$ groundline kernel generate    # (re)write the generated Lean modules
$ groundline kernel verify      # models current? then: do the proofs still hold?
```

`verify` exits non-zero on any mismatch or proof failure — the CI gate in
miniature. The proof stage needs `lake` (Lean 4); each missing tool is
reported honestly rather than skipped silently.

## Notes

- The toy stays inside the supported kernel subset (anything outside it
  raises `UnsupportedConstruct` rather than guessing). Banking
  `toy_kernel_loop.f90` without `pointize = true` is a quick way to see a
  refusal — a loop is not a point function.
- Regenerating the modules re-stamps your local flang/clang versions into
  their header comments; the defs themselves are byte-stable across
  machines.
