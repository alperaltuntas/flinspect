# The kernel manifest (`kernels.toml`)

The manifest is the single declarative home of everything site-specific:
which kernel pairs are banked, where the dumps and headers live, which
toolchain extracts the C++ side, and where the generated modules go. The
package itself carries **no built-in paths or defaults** — the schema is
implemented (and documented) in `groundline/kernel_bank.py`.

## Resolution order

Every `groundline kernel` subcommand locates its manifest the same way, first
match wins:

1. `--kernels PATH` (CLI flag)
2. `$GROUNDLINE_KERNELS` (environment variable)
3. `./kernels.toml` (current directory)

Nothing else — no home-directory config, no fallback path.

## General rules

- Parsed with stdlib `tomllib` (no extra dependency).
- String values expand `${ENV_VAR}` from the environment; an **unset variable
  refuses** (`ManifestError`), never expands to empty.
- Relative paths resolve against **the manifest file's directory**, so a
  manifest travels with its tree.
- **Unknown keys refuse.** The manifest sits close to the trusted base: a
  typo like `namespcae` must fail loudly, not be silently ignored. Types are checked;
  missing required keys are named.
- Duplicate kernel names refuse.

## `[fortran]` — the flang side (omit to disable the side entirely)

| Key | Required | Meaning |
|---|---|---|
| `corpus` | yes | root directory of the with-sema `*_ptree` dumps; each kernel's `dump` resolves under it |
| `out` | yes | where `kernel generate` writes the Fortran-side Lean module |
| `namespace` | yes | Lean namespace of the generated module (e.g. `Groundline.GeneratedFtn`) |
| `blurb` | no | extra lines appended to the generated module's header comment |

## `[cpp]` — the clang side (omit to disable)

| Key | Required | Meaning |
|---|---|---|
| `out` | yes | where `kernel generate` writes the C++-side Lean module |
| `namespace` | yes | Lean namespace of the generated module |
| `header_dir` | no (default `.`) | root the kernels' `header` values resolve under |
| `include_dirs` | no | pinned `-I` directories — part of the kernel identity, stamped into the generated provenance header |
| `clang` | no (default `clang++`) | the compiler executable |
| `provenance_root` | no | headers display relative to this root in generated doc comments — what keeps them byte-stable across machines |
| `blurb` | no | extra header-comment lines |

## `[lean]` — the proof stage (optional)

| Key | Required | Meaning |
|---|---|---|
| `lake_dir` | yes (if section present) | `kernel verify` runs `lake build` here after the byte-diff gate passes |

## `[[kernel]]` — one table per banked pair

```toml
[[kernel]]
name = "ppm_limit_pos"
fortran = { dump = "MOM6/MOM_continuity_PPM.o_ptree", subroutine = "ppm_limit_pos" }
cpp     = { header = "mom_continuity_ppm_kernel.hpp", function = "ppm_limit_pos_point" }
```

- `name` (required) — the entry's identity, and (for inline-loop entries) the
  generated def's name.
- `fortran = { dump, subroutine [, nest [, def_name]] }` — `dump` resolves
  under `[fortran].corpus`. Without `nest`, the whole subroutine is the
  kernel and **the entry must be named after the subroutine** (enforced).
  With `nest = N`, loop nest #N of the subroutine (source-order ordinal) is
  extracted, generated under `def_name` if given, else under `name` — see
  [inline-loop addressing](../howto/inline-loops.md). `def_name` without
  `nest` refuses.
- `cpp = { header, function }` — `header` resolves under `[cpp].header_dir`.
- Either side may be omitted (a Fortran-only or C++-only entry is legal); an
  entry with neither refuses, as does a side whose section is absent.

The manifest-relative spellings of `dump` and `header` (the latter re-rooted
at `provenance_root` when set) are what appear in the generated doc comments —
resolved absolute paths never leak into generated files.

## The two committed instances

- [`examples/quickstart/kernels.toml`](https://github.com/alperaltuntas/groundline/blob/main/examples/quickstart/kernels.toml)
  — the self-contained toy pair; everything relative, no `[lean]` section.
- [`examples/turbo-stack.kernels.toml`](https://github.com/alperaltuntas/groundline/blob/main/examples/turbo-stack.kernels.toml)
  — the production instance (the MOM6 ⇄ TIM case study): the five banked pairs, the NCAR
  corpus and kernel header paths, pinned AMReX/MPI include dirs, and
  `lake_dir = "../lean/groundline"`. On another site, copy it and repoint the
  paths — that file is the *only* thing that changes.
