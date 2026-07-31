# Installation

groundline's Track B is deliberately usable in tiers. Each tier adds one
external toolchain and unlocks one more stage of the pipeline; everything
below your tier keeps working. Be honest with yourself about which tier you
need — most readers exploring the method need only the first.

## Tier 1 — pip alone

```bash
git clone https://github.com/alperaltuntas/groundline
cd groundline
python3 -m venv .venv
PYTHONNOUSERSITE=1 .venv/bin/pip install -e '.[dev]'
```

Python ≥ 3.11, no compiler toolchains. This unlocks:

- extraction from **committed** flang dumps (the quickstart ships one, and the
  test fixtures under `tests/f90/` are all committed with provenance);
- the full Fortran side of the CLI: `groundline kernel list`, `show`,
  `generate --skip-cpp`, `verify --skip-cpp`;
- reading and regenerating the Fortran-side generated Lean *text* (printing
  needs no Lean installation — Lean is only needed to *check* proofs).

The `PYTHONNOUSERSITE=1` guard keeps a broken `~/.local` user site from
shadowing the venv; harmless where the user site is healthy, essential where
it is not. Use it on the *install* command too, or transitive dependencies can
silently resolve against the user site.

## Tier 2 — + flang (generate your own Fortran dumps)

The Fortran frontend consumes flang **with-sema parse-tree dumps**:

```bash
flang -fc1 -fdebug-dump-parse-tree kernel_source.f90 > kernel_source_ptree
```

The committed fixtures and the production corpus were generated with **flang
21** (the exact version is stamped in `tests/f90/PROVENANCE`). The dump format
has no formal stability contract, so other LLVM versions may work or may not —
the conformance corpus exists precisely to detect and localize format drift;
see [Port to a new LLVM](howto/new-llvm.md). Two constraints worth knowing
before you generate dumps at scale:

- the source must be *semantically valid*, not merely parseable — flang emits
  no dump at all on a semantic error;
- a file that USEs modules from other files needs those modules' `.mod` files
  built first, i.e. a full ordered build. The MOM6 production corpus is
  generated as a side product of the real build.

## Tier 3 — + clang (the C++ side)

The C++ frontend invokes `clang++` itself (`-ast-dump=json`); no dump files
are involved — clang's JSON is consumed in memory and never committed, because
its node IDs are memory addresses and nondeterministic across runs.

- For **standalone headers** like the quickstart's `toy_kernel.hpp`, a plain
  `clang++` on `PATH` is all you need.
- For the **real TIM kernels**, the headers include AMReX, so the manifest
  must also point at an AMReX install's `include/` directory (and an
  `mpi.h`); see the pinned `include_dirs` in
  [`examples/turbo-stack.kernels.toml`](https://github.com/alperaltuntas/groundline/blob/main/examples/turbo-stack.kernels.toml).
  The compiler and include directories are part of a kernel's identity — the
  invocation is stamped into the generated module's provenance header.

## Tier 4 — + Lean 4 / Mathlib (check the proofs)

The proofs live in `lean/pilot/`, a `lake` project depending on Mathlib.
Install the toolchain with [elan](https://github.com/leanprover/elan), then:

```bash
cd lean/pilot
lake exe cache get   # fetch the Mathlib binary cache — thousands of prebuilt
                     # modules; without it Mathlib builds from source for hours
lake build
```

This unlocks the last tier of `groundline kernel verify`: after the byte-diff
gate passes, it runs `lake build` in the manifest's `[lean] lake_dir`, which
re-checks every theorem and re-runs the axioms audit.

Two practical notes from experience:

- **The Mathlib binary cache is not optional in practice.** Also, prefer
  targeted imports (`Mathlib.Data.Real.Basic`, `Mathlib.Tactic.Ring`) over a
  blanket `import Mathlib` in new proof files — on a networked filesystem the
  blanket import can take minutes per file to elaborate.
- **A bare elan shim is worse than no `lake`.** `verify` skips the Lean tier
  with a clear note when `lake` is absent, but an elan shim on `PATH` without
  a provisioned toolchain *fails* the gate (elan tries to download a toolchain
  on the spot). Activate a real Lean environment before relying on the Lean
  tier.

## What each tier unlocks — summary

| Tier | Adds | Unlocks |
|---|---|---|
| 1 | `pip install` | extraction from committed dumps; Fortran-side `list`/`show`/`generate`/`verify` |
| 2 | flang | generating with-sema dumps for your own Fortran |
| 3 | clang++ (+ AMReX headers for TIM) | the C++ side of `show`/`generate`/`verify` |
| 4 | Lean 4 / Mathlib (elan) | checking the equivalence theorems; the `lake build` tier of `verify` |

The CLI degrades honestly between tiers: a missing `clang++` produces a
skip note (`show`) or an explicit error (`verify`, which must not pass
vacuously), and a missing `lake` produces a skip note naming what was skipped.
