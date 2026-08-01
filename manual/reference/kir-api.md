# The kir API

The Python surface of the kernel-verification pipeline, for driving it
programmatically.
Everything here is importable from an installed `groundline`; the CLI is a
thin wrapper over exactly these calls.

## `groundline.kir` — the kernel IR and its passes

The IR vocabulary (frozen dataclasses) is catalogued in
[the kernel IR concept page](../concepts/kernel-ir.md); the API surface:

```python
from groundline.kir import (
    # expression nodes
    RealLit, IntLit, Var, ArrayRef, ComponentRef, Paren, Neg, BinOp, Cmp,
    Call, Cond,
    # statement nodes
    Assign, If, DoConcurrent, Do,
    # kernel shape
    Param, Kernel,
    # functional form (produced by functionalize)
    Let, IfExpr, Tuple_,
    # passes + the refusal exception
    pointize, functionalize, UnsupportedConstruct,
)
```

- `pointize(kernel: Kernel) -> Kernel` — strip the single loop-nest wrapper,
  scalarize arrays, synthesize component parameters, drop unused params.
  Refuses anything outside [the two licensed nest forms](../concepts/pointize.md).
- `functionalize(kernel: Kernel) -> (params, output_names, FunExpr)` — the
  imperative body as one functional expression;
  [state threading and the join](../concepts/functionalize.md). Called for
  you by the printer.
- `UnsupportedConstruct` — the refusal exception, raised at every boundary of
  the subset; its message names the construct
  ([catalog](refusals.md)).

## `groundline.frontend.kernel_base` — the seam

```python
from groundline.frontend.kernel_base import (
    KernelFrontend,        # Protocol: extract(spec) -> Kernel
    FortranKernelSpec,     # dump, subroutine, nest=None, def_name=None
    CppKernelSpec,         # source, function, include_dirs=(), compiler="clang++"
)
from groundline.frontend.flang_kernel import FlangKernelFrontend
from groundline.frontend.clang_kernel import ClangKernelFrontend
```

Typed addresses in, `Kernel` out:

```python
k = FlangKernelFrontend().extract(FortranKernelSpec(
        dump=Path("MOM6/MOM_continuity_PPM.o_ptree"),
        subroutine="ppm_limit_pos"))
```

`FortranKernelSpec` validates that `nest` and `def_name` travel together
(inline-loop addressing) or not at all. `CppKernelSpec` carries the pinned
clang invocation because the toolchain is part of the kernel's identity.

## `groundline.lean_printer` — rendering

```python
from groundline.lean_printer import print_kernel, print_module, print_expr
```

- `print_kernel(kernel, *, provenance="") -> str` — one complete Lean `def`
  from a **pointized** kernel (it runs `functionalize` itself); `provenance`
  becomes the def's doc comment.
- `print_module(kernels, *, namespace, blurb) -> str` — a full generated
  module: imports, linter options, header (from `blurb`), namespace,
  `noncomputable section`, the defs.

Behavioral details (literal normalization, parenthesization, precedence) are
in [Printer behavior](printer.md).

## `groundline.kernel_bank` — the manifest pipeline

```python
from groundline import kernel_bank as kb

m = kb.load_manifest(kb.resolve_manifest_path())   # or an explicit path
entry = m.kernel("ppm_limit_pos")

k_f = kb.extract_fortran_entry(entry)   # extract; pointize iff licensed
k_c = kb.extract_cpp_entry(entry)       # extract (point functions only)

text_f = kb.render_fortran(m)           # the full Fortran-side module text
text_c = kb.render_cpp(m)               # the full C++-side module text
```

`extract_fortran_entry` enforces the loop/point boundary: a loop-nest kernel
refuses unless its entry carries `pointize = true`, and the option refuses on
a kernel that is not a loop ([why](../concepts/pointize.md)).

Key names: `Manifest`, `KernelEntry`, `FortranConfig`, `CppConfig`,
`ManifestError` (malformed manifest — refuse, don't guess),
`resolve_manifest_path`, `load_manifest`, `fortran_entries` / `cpp_entries`,
`extract_all_fortran` / `extract_all_cpp`, `fortran_provenance` /
`cpp_provenance`, and the `MANIFEST_ENV` / `MANIFEST_FILENAME` constants.
`render_*` accept a pre-extracted list so extraction and rendering can be
separated (this is how `generate` prints per-kernel progress).

The golden tests import these same functions — driver and tests cannot
disagree about what the generated modules should contain.

## Stability

groundline is a pre-1.0 research tool: this surface is what the CLI, the tests,
and the notebooks use, and changes to it land with the corresponding DEVLOG
entry — but no semver-style compatibility promise exists yet.
