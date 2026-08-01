# groundline quickstart — a toy kernel pair, end to end

This directory is a self-contained instance of the groundline
kernel-verification pipeline: a tiny Fortran point kernel (plus its loop
variant) and its C++ point-function port, paired in a `kernels.toml` manifest,
rendered into two generated Lean modules, and related by machine-checked
theorems. Everything here works in a bare clone of groundline, anywhere — no
site paths, no external libraries.

**The manual's [Quickstart page](https://alperaltuntas.github.io/groundline/quickstart/)
is the guided walkthrough of this directory** — with real, captured output
for every step. The short version below is just enough to orient a reader
browsing the repo.

## What's here

| File | Role |
|---|---|
| `toy_kernel.f90` | The Fortran side: `scale_clip_acc` (one grid point) and `scale_clip_acc_loop` (the same update over a column) |
| `toy_kernel_ptree` | Its **committed** flang dump (see `PROVENANCE`), so the Fortran side needs no flang install |
| `toy_kernel.cpp` | The C++ port (`scale_clip_acc_point`) — standalone, plain `double`, no includes |
| `kernels.toml` | The manifest pairing them; the loop kernel carries the explicit `pointize = true` license |

The generated Lean modules and the equivalence theorems live in the
repository's Lean project — `lean/groundline/Groundline/QuickstartFtn.lean`,
`QuickstartCpp.lean` (generated; do not edit) and `QuickstartEquiv.lean`
(the theorems, both `rfl`).

## The four commands

From this directory (the CLI picks up `./kernels.toml` automatically):

```console
$ groundline kernel list        # what the manifest declares, with status
$ groundline kernel show NAME   # print one kernel's generated Lean, both sides
$ groundline kernel generate    # (re)write the generated Lean modules
$ groundline kernel verify      # models current? then: do the proofs still hold?
```

`verify` exits non-zero on any mismatch or proof failure — the CI gate in
miniature. The C++ side needs `clang++` on `PATH`; the proof stage needs
`lake` (Lean 4); each is skipped or reported honestly when absent.

## Notes

- The toy stays inside the supported kernel subset (anything outside it
  raises `UnsupportedConstruct` rather than guessing). Removing the
  `pointize = true` line and asking for the loop kernel is a quick way to
  see a refusal.
- Regenerating `QuickstartCpp.lean` re-stamps your local clang version into
  its header comment; the defs themselves are byte-stable across machines.
- To regenerate the committed dump after editing `toy_kernel.f90`:
  `flang -fc1 -fdebug-dump-parse-tree toy_kernel.f90 > toy_kernel_ptree`
  (and update `PROVENANCE`, mirroring `tests/f90`'s convention).
