# CLI

The `groundline` console script is installed by `pip install`
(`[project.scripts]` → `groundline.cli:main`). It is argparse-only and
widget-free on purpose — it must work in a bare environment with no Jupyter
stack.
All help text below is the real `--help` output, captured from the installed
script (see `manual/snippets/render_snippets.sh`).

```console
$ groundline --help
--8<-- "cli_help.txt"
```

Today the `kernel` group is the CLI's only command group; the relational
track's `check`/`report` groups are designed to plug in as siblings when they
land ([roadmap](../relational.md)).

## `groundline kernel`

```console
$ groundline kernel --help
--8<-- "cli_kernel_help.txt"
```

Every subcommand takes `--kernels PATH`; resolution order is
`--kernels` > `$GROUNDLINE_KERNELS` > `./kernels.toml`
([details](manifest.md#resolution-order)).

### `kernel list`

```console
$ groundline kernel list --help
--8<-- "cli_kernel_list_help.txt"
```

Prints every manifest entry with its addressing (subroutine, nest ordinal,
header/function) and a basic existence status per side, plus whether each
output module is present:

```console
--8<-- "quickstart_list.txt"
```

### `kernel show NAME`

```console
$ groundline kernel show --help
--8<-- "cli_kernel_show_help.txt"
```

Extracts one kernel fresh from its sources and prints both generated Lean
defs to stdout — no files touched. A side whose compiler is not on `PATH` is
skipped with a stderr note (the C++ side needs the manifest's clang; a
source-mode Fortran kernel needs its flang). This is the by-eye-audit and
debugging tool: run it after adding a manifest row, before generating.

### `kernel generate`

```console
$ groundline kernel generate --help
--8<-- "cli_kernel_generate_help.txt"
```

(Re)writes the generated Lean modules for each enabled side, printing every
extracted kernel's parameter/local lists as it goes. `--skip-fortran` /
`--skip-cpp` scope the run. Regeneration is deterministic — same inputs, same
bytes — except the module header comments, which stamp the local compiler
version whenever a compiler ran on demand (by design: toolchain is
provenance).

### `kernel verify`

```console
$ groundline kernel verify --help
--8<-- "cli_kernel_verify_help.txt"
```

The CI gate. It runs two checks, in order:

1. **Are the generated models current?** Each enabled side is re-extracted
   from its sources and re-rendered **in memory**, then compared byte for
   byte against the `generated` module on disk — the file `generate` wrote
   (keep it in version control so a mismatch is meaningful). Any difference
   → the fresh copy is parked in a temp file, a unified-diff excerpt (first
   40 lines) is printed, and the exit code is non-zero. A missing module
   file counts as a mismatch. A missing compiler that some kernel needs run
   fresh is an **error** (a gate must not pass by accident) unless
   `--skip-fortran`/`--skip-cpp` scopes the run.
2. **Do the proofs still hold?** If the models are current and the manifest
   names a `[lean]` project, `verify` runs `lake build` there — re-checking
   every theorem in that project. If the manifest has no `[lean]` section,
   `verify` prints a note that no theorems were checked; if `lake` is not
   on `PATH`, a note that the proofs were not re-checked; if the model
   check already failed, the proof check is skipped (proofs about stale
   models prove nothing).

See [Wire verification into CI](../howto/ci.md) for gate recipes and the one
subtlety about the C++ comparison under a non-pinned clang.

## Exit codes and errors

| Code | Meaning |
|---|---|
| 0 | success (including `verify` fully green) |
| 1 | `verify` found a mismatch or a failure (model check, missing compiler, proof check) |
| 2 | usage/environment error: bad or missing manifest (`ManifestError`), a kernel outside the supported subset (`UnsupportedConstruct`), missing file |

An `UnsupportedConstruct` refusal surfaces as
`error: outside the supported kernel subset — <detail>`, where the detail
names the offending construct — for example, against the k-recurrence fixture:

```console
--8<-- "refusal_recurrence.txt"
```

The complete inventory of what refuses and why is the
[refusal catalog](refusals.md).
