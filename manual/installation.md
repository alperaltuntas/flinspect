# Installation

You don't need every toolchain to use groundline. The Python package alone
already runs the Fortran side of the pipeline end to end; flang, clang, and
Lean each add one more stage on top. This page walks through the four levels
in order — if you are just exploring the method, the first one is all you
need.

## Level 1 — the Python package

The recommended install is the groundline conda environment:

```bash
git clone https://github.com/alperaltuntas/groundline
cd groundline
conda env create -f environment.yml
conda activate groundline
```

This creates an isolated environment named `groundline` (Python 3.12) and
installs the package into it in editable mode, so a `git pull` takes effect
immediately. No compiler toolchains are involved. With this you can:

- extract kernels from **pre-generated** flang dumps (`dump =` entries in a
  manifest) — the test fixtures under `tests/f90/` are all committed with
  provenance, and a production dump directory works the same way;
- run the Fortran side of the CLI over such manifests: `groundline kernel
  list`, `show`, `generate --skip-cpp`, `verify --skip-cpp`;
- read and regenerate the Fortran-side generated Lean *text* (printing needs
  no Lean installation — Lean is only needed to *check* proofs).

??? note "pip/venv instead of conda"

    If you prefer a plain virtualenv:

    ```bash
    python3 -m venv .venv
    .venv/bin/pip install -e '.[dev]'
    ```

    One pitfall worth knowing either way: a stale or broken `~/.local` user
    site-packages can shadow the environment's packages. If you see import
    errors that make no sense, set `PYTHONNOUSERSITE=1` (on the install
    command too) and they will go away.

## Level 2 — add flang, for the Fortran side of your own sources

The Fortran frontend consumes flang **with-sema parse-tree dumps**, and there
are two ways a manifest can supply them:

- **Source mode** (`source =` in the kernel entry) — for a standalone file
  that USEs nothing outside itself, groundline runs flang on it directly and
  reads the dump in memory; no dump file exists on disk. This is how the
  [quickstart](quickstart.md) works, and it's the mirror of how the C++ side
  runs clang. It needs `flang` on `PATH`.
- **Dump mode** (`dump =`) — for kernels living inside a real codebase, the
  dump is generated once inside the code's own build and kept with
  provenance:

```bash
flang -fc1 -fdebug-dump-parse-tree kernel_source.f90 > kernel_source_ptree
```

The committed fixtures and the production dump collection were generated
with **flang 21** (the exact version is stamped in `tests/f90/PROVENANCE`). The dump format
has no formal stability contract, so other LLVM versions may or may not work
as is — the conformance fixtures exist precisely to detect and localize format
drift; see [Port to a new LLVM](howto/new-llvm.md). Two constraints to know,
whichever mode you use:

- the source must be *semantically valid*, not merely parseable — flang emits
  no dump at all on a semantic error;
- a file that USEs modules from other files needs those modules' `.mod` files
  built first, which means a full ordered build — this is exactly what rules
  out source mode for such files and makes dump mode exist. The case studies'
  dump directory is generated as a side product of the real model build.

## Level 3 — add clang, for the C++ side

The C++ frontend invokes `clang++` itself (`-ast-dump=json`); there are no
dump files to manage — clang's JSON is consumed in memory and never
committed, because its node IDs are memory addresses and change between runs.
(Why the two frontends consume different formats at all is answered in
[the frontends reference](reference/frontends.md#why-two-different-input-formats).)

- For **standalone sources** like the quickstart's `toy_kernel.cpp`, a plain
  `clang++` on `PATH` is all you need.
- Sources with dependencies need their include paths in the manifest. The
  production case study's kernels include AMReX, so its manifest pins an
  AMReX install's `include/` directory (and an `mpi.h`); see `include_dirs`
  in
  [`examples/turbo-stack.kernels.toml`](https://github.com/alperaltuntas/groundline/blob/main/examples/turbo-stack.kernels.toml).
  The compiler and include directories are part of a kernel's identity — the
  invocation is stamped into the generated module's provenance header.

## Level 4 — add Lean 4 / Mathlib, to check the proofs

The proofs live in `lean/groundline/`, a `lake` project depending on Mathlib.
Install the toolchain with [elan](https://github.com/leanprover/elan), then:

```bash
cd lean/groundline
lake exe cache get   # fetch the Mathlib binary cache — thousands of prebuilt
                     # modules; without it Mathlib builds from source for hours
lake build
```

This enables the last stage of `groundline kernel verify`: after the
byte-diff gate passes, it runs `lake build` in the manifest's
`[lean] project`, which re-checks every theorem and re-runs the axioms
audit.

Two practical notes from experience:

- **Get the Mathlib binary cache.** It is technically optional and
  practically not. Relatedly, prefer targeted imports
  (`Mathlib.Data.Real.Basic`, `Mathlib.Tactic.Ring`) over a blanket
  `import Mathlib` in new proof files — on a networked filesystem the blanket
  import can take minutes per file to elaborate.
- **A bare elan shim is worse than no `lake` at all.** `verify` skips the
  Lean stage with a clear note when `lake` is absent, but an elan shim on
  `PATH` without a provisioned toolchain *fails* the gate (elan tries to
  download a toolchain on the spot). Activate a real Lean environment before
  relying on this stage.

## Summary — what each level adds

| Level | Adds | What you can do |
|---|---|---|
| 1 | the conda environment | extract from pre-generated dumps; Fortran-side `list`/`show`/`generate`/`verify` over them |
| 2 | flang | source-mode Fortran kernels (the quickstart); generate dumps of your own Fortran |
| 3 | clang++ (+ the headers' include paths) | the C++ side of `show`/`generate`/`verify` |
| 4 | Lean 4 / Mathlib (elan) | check the equivalence theorems; the `lake build` stage of `verify` |

The CLI is upfront about missing tools: without the compiler a side needs
(`flang` for source-mode Fortran kernels, `clang++` for C++), `show` prints a
skip note and `verify` errors (a gate must not pass by accident); without
`lake`, `verify` prints a skip note naming exactly what was skipped.
