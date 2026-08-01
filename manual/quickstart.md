# Quickstart

`examples/quickstart/` is a complete, self-contained instance of the
kernel-verification pipeline: a toy Fortran kernel and its C++ twin, banked in a manifest and
rendered into two generated Lean modules. It runs in a bare clone — no
corpus, no AMReX, no site paths. The Fortran side needs only
[level 1](installation.md) of the installation (the flang dump is committed
next to the source); the C++ side needs `clang++` on `PATH`.

Every command output on this page is real, captured from the pipeline (see
`manual/snippets/render_snippets.sh` in the repository for exactly how).

## The kernel pair

The Fortran kernel — scale, clip from below, accumulate — written as a
`do concurrent` point kernel:

```fortran
--8<-- "examples/quickstart/toy_kernel.f90"
```

And its C++ twin, a per-point function of the kind an AMReX-style port
produces (kept deliberately standalone — its own `using Real = double;`, no
includes):

```cpp
--8<-- "examples/quickstart/toy_kernel.hpp"
```

The pairing lives in `kernels.toml`, the [kernel manifest](reference/manifest.md):

```toml
--8<-- "examples/quickstart/kernels.toml"
```

## 1. List what the manifest banks

From `examples/quickstart/` (the CLI finds `./kernels.toml` on its own; from
anywhere else, pass `--kernels path/to/kernels.toml`):

```console
$ groundline kernel list
--8<-- "quickstart_list.txt"
```

## 2. Show the generated Lean, both sides

```console
$ groundline kernel show scale_clip_acc
--8<-- "quickstart_show.txt"
```

Two things to notice. The two bodies are **identical** — for this toy that is
the whole demonstration: two compilers, two languages, one extraction
pipeline, same function. And each def's doc comment records its provenance —
which symbol, in which dump or header, through which frontend.

Without `clang++` on `PATH`, the C++ def is skipped with a note on stderr;
the Fortran side always works.

## 3. Generate the committed modules

```console
$ groundline kernel generate
--8<-- "quickstart_generate.txt"
```

This (re)writes `GeneratedFtn.lean` and `GeneratedCpp.lean` — both are
committed, so you can diff what you just generated against the repository.
The Fortran module is byte-stable across machines; the C++ module's *defs*
are byte-stable while its header comment re-stamps your local clang version
(by design — the toolchain is provenance).

The full committed Fortran module:

```lean
--8<-- "examples/quickstart/GeneratedFtn.lean"
```

## 4. Verify — the CI gate in miniature

```console
$ groundline kernel verify
--8<-- "quickstart_verify.txt"
```

`verify` regenerates from the sources and **byte-diffs** against the
committed files, exiting non-zero on any drift (and parking the fresh copy in
a temp file for inspection). For manifests that set `[lean] lake_dir` — the
production one does — it then runs `lake build`, which re-checks every
theorem. See [Wire verification into CI](howto/ci.md).

## 5. The equivalence theorem (Lean level)

The quickstart directory deliberately ships no Lean project — the two
generated defs are the demo. But the theorem they set up is one line, and it
was checked against the committed defs while writing this page (via
`lake env lean` in `lean/groundline`, which has Mathlib available):

```lean
theorem scale_clip_acc_equiv (a b s lo : ℝ) :
    Quickstart.GeneratedCpp.scale_clip_acc_point b a s lo
      = Quickstart.GeneratedFtn.scale_clip_acc a b s lo := rfl

#print axioms scale_clip_acc_equiv
-- 'scale_clip_acc_equiv' depends on axioms: [propext, Classical.choice, Quot.sound]
```

`rfl` means the two definitions are *definitionally equal* — the strongest
possible statement (see [the fidelity contract](concepts/printer-fidelity.md)).
For the real kernels the bodies differ in shape between the two languages and
the theorems do real work; that story is told in the
[case studies](case-studies/ppm-limit-pos.md).

## Where the production instance differs

The production manifest,
[`examples/turbo-stack.kernels.toml`](https://github.com/alperaltuntas/groundline/blob/main/examples/turbo-stack.kernels.toml),
banks the five MOM6 ⇄ TIM kernel pairs of the manual's case studies against
the with-sema dump corpus of the real MOM6 build and the real C++ headers
(AMReX include paths pinned), and points `[lean] lake_dir` at `lean/groundline`
so `verify` ends in a full proof check:

```console
$ groundline kernel list --kernels examples/turbo-stack.kernels.toml
--8<-- "production_list.txt"
```

Those paths are site-specific by nature (NCAR's GLADE filesystem) — the
manifest is the *only* place they exist; the package itself carries no
built-in paths. To bank your own kernels, copy either manifest and repoint
it: see [Bank a new kernel pair](howto/bank-a-kernel.md).
