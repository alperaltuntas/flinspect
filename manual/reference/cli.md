# CLI

The `groundline` console script is installed by `pip install`
(`[project.scripts]` → `groundline.cli:main`). It is argparse-only and
widget-free by design — it must work in a bare venv with no Jupyter stack.
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
defs to stdout — no files touched. The C++ side is skipped with a stderr note
when the manifest's clang is not on `PATH`. This is the by-eye-audit and
debugging tool: run it after adding a manifest row, before generating.

### `kernel generate`

```console
$ groundline kernel generate --help
--8<-- "cli_kernel_generate_help.txt"
```

(Re)writes the generated Lean modules for each enabled side, printing every
extracted kernel's parameter/local lists as it goes. `--skip-fortran` /
`--skip-cpp` scope the run. Regeneration is deterministic — same inputs, same
bytes — except the C++ module's header comment, which stamps the local clang
version (by design: toolchain is provenance).

### `kernel verify`

```console
$ groundline kernel verify --help
--8<-- "cli_kernel_verify_help.txt"
```

Track B's CI gate, in order:

1. regenerate each enabled side **in memory** and byte-diff against the
   committed `out` files. Drift → the fresh copy is parked in a temp file, a
   unified-diff excerpt (first 40 lines) is printed, and the exit code is
   non-zero. A missing committed file is drift. A missing clang is an
   **error** (a gate must not pass vacuously) unless `--skip-cpp` is given;
2. if the manifest has `[lean] lake_dir` and every diff passed: run
   `lake build` there (skipped with an explicit note when `lake` is not on
   `PATH`; skipped when drift was found — proofs about stale defs prove
   nothing).

See [Wire verification into CI](../howto/ci.md) for gate recipes and the one
subtlety about the C++ byte-diff under a non-pinned clang.

## Exit codes and errors

| Code | Meaning |
|---|---|
| 0 | success (including `verify` fully green) |
| 1 | `verify` found drift or a failure (byte-diff, missing clang, `lake build`) |
| 2 | usage/environment error: bad or missing manifest (`ManifestError`), a kernel outside the supported subset (`UnsupportedConstruct`), missing file |

An `UnsupportedConstruct` refusal surfaces as
`error: outside the supported kernel subset — <detail>`, where the detail
names the offending construct — for example, against the k-recurrence fixture:

```console
--8<-- "refusal_recurrence.txt"
```

The complete inventory of what refuses and why is the
[refusal catalog](refusals.md).
