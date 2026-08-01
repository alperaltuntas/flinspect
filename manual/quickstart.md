# Quickstart

`examples/quickstart/` is a complete, self-contained instance of the
kernel-verification pipeline: a toy Fortran kernel and its C++ port, paired
up in a manifest, rendered into two generated Lean modules, and related by a
machine-checked equivalence theorem. It runs in a bare clone — no site paths,
no external libraries. The Fortran side needs only
[level 1](installation.md) of the installation (a pre-made flang dump ships
with the example); the C++ side needs `clang++` on `PATH`; checking the
theorem at the end needs Lean (level 4).

Every command output on this page is real, captured from the pipeline (see
`manual/snippets/render_snippets.sh` in the repository for exactly how).

## The kernel pair

The Fortran side — scale `a` by `s`, clip to `lo` from below, accumulate
into `b`:

```fortran
--8<-- "examples/quickstart/toy_kernel.f90"
```

There are two subroutines here. `scale_clip_acc` computes **one grid point**,
and it is the one we pair with the C++ port; `scale_clip_acc_loop` is the
same update written as a loop over a column, and we will come back to it in
step 3.

The C++ port has the same per-point shape — outputs are non-const references,
inputs are const values:

```cpp
--8<-- "examples/quickstart/toy_kernel.cpp"
```

The manifest, `kernels.toml`, ties the two sides together. `[fortran]` and
`[cpp]` configure each language side once — where its inputs live, and which
Lean module gets generated; each `[[kernel]]` then gives one kernel's
location on each side (the full schema is in
[the manifest reference](reference/manifest.md)):

```toml
--8<-- "examples/quickstart/kernels.toml"
```

## 1. List what the manifest declares

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

Two things to notice. The two point-kernel bodies are **identical** — for
this toy that is the whole demonstration: two compilers, two languages, one
extraction pipeline, same function. And each def's doc comment records its
provenance — which symbol, in which file, through which frontend.

Without `clang++` on `PATH`, the C++ def is skipped with a note on stderr;
the Fortran side always works.

## 3. The loop version — and why it refuses by default

A loop over a column and a function of one point are different things, so
groundline will not silently treat them as the same. If you remove the
`pointize = true` line from the loop kernel's entry and ask for it:

```console
$ groundline kernel show scale_clip_acc_loop
--8<-- "quickstart_pointize_refusal.txt"
```

Putting `pointize = true` back is the explicit license: it tells groundline
to strip the loop and model its **per-point body**, which is exactly what
you want when a C++ port turned a Fortran loop into a per-point function.
What makes that reduction legitimate — the loop's `do concurrent`
independence assertion here, a proved schema lemma for plain `do` loops — is
the subject of [the Pointize concept page](concepts/pointize.md). All five
production kernels in the case studies use this license; the manifest states
it out loud each time.

## 4. Generate the Lean modules

```console
$ groundline kernel generate
--8<-- "quickstart_generate.txt"
```

`generate` writes the two generated modules to wherever the manifest's
`generated` keys point — here, into the repository's Lean proof project
(`lean/groundline/`), where the theorems can import them. The files are
meant to be kept in version control: they change only when a kernel's source
(or the pipeline) changes, and step 6 leans on that. The full Fortran-side
module, exactly as generated:

```lean
--8<-- "lean/groundline/Groundline/QuickstartFtn.lean"
```

The Fortran module is byte-identical no matter where you run this. The C++
module's defs are too; only its header comment differs across machines,
because it records which clang produced the AST — the toolchain is part of
the provenance.

## 5. The theorems — the actual point of all this

The two generated defs are related by theorems in
`lean/groundline/Groundline/QuickstartEquiv.lean`, committed right next to
the generated modules:

```lean
--8<-- "lean/groundline/Groundline/QuickstartEquiv.lean"
```

`rfl` proves an equality by *definitional* equality: Lean's kernel unfolds
both definitions and sees the same function — the strongest possible way for
the proof to close (see [the fidelity contract](concepts/printer-fidelity.md)).
The second theorem closes the loop from step 3: the loop's extracted
per-point body is the same function as the standalone point subroutine.

One honest note on the workflow: **the theorem file is yours to write.**
groundline generates the two definitions deterministically; relating them is
a proof, and a human (or a proof-searching agent) writes it once per kernel.
For shape-identical pairs like this one it is a single `rfl` line. For real
kernels, whose bodies differ in shape between the two languages, the working
patterns are documented — see [Bank a new kernel pair](howto/bank-a-kernel.md)
and the [case studies](case-studies/ppm-limit-pos.md); every kernel banked
so far closed with a handful of lines. Once written, the theorem is
re-checked mechanically forever after (next step).

## 6. Verify — the whole chain as one command

```console
$ groundline kernel verify
--8<-- "quickstart_verify.txt"
```

`verify` does two things, in order:

1. **Are the generated models current?** For each side, it re-extracts every
   kernel from its sources (the dump, the `.cpp`) and re-renders the Lean
   module in memory, then compares the result **byte for byte** with the
   module on disk from step 4. Any difference — an edited source, a stale
   module, a changed pipeline — fails with a diff excerpt, and the fresh
   copy is parked in a temp file so you can inspect it.
2. **Do the proofs still hold?** Because this manifest names a `[lean]`
   project, `verify` then runs `lake build` there, which re-checks every
   theorem in that project — for the quickstart, the two equivalence
   theorems above. If a manifest names no `[lean]` project, `verify` says so
   explicitly and you have only checked that the models are current, not
   that any theorem holds.

Both stages exit non-zero on failure, which is what makes `verify` a CI
gate: after any change to the Fortran, the C++, or the pipeline itself, one
command re-establishes that the committed models match the sources *and*
the equivalence still holds. See [Wire verification into CI](howto/ci.md).

## Where the production instance differs

The production manifest,
[`examples/turbo-stack.kernels.toml`](https://github.com/alperaltuntas/groundline/blob/main/examples/turbo-stack.kernels.toml),
declares the five MOM6 ⇄ TIM kernel pairs of the case studies. Its `[fortran]
dumps` points at the dump directory of the real MOM6 build, its C++ sources
are the real port's headers (with their AMReX include paths pinned), every
kernel is a loop in the Fortran source (`pointize = true` throughout), and
the same `[lean]` project holds their theorems:

```console
$ groundline kernel list --kernels examples/turbo-stack.kernels.toml
--8<-- "production_list.txt"
```

Those paths are site-specific by nature (NCAR's GLADE filesystem) — the
manifest is the *only* place they exist; the package itself carries no
built-in paths. To pair up your own kernels, copy either manifest and
repoint it: see [Bank a new kernel pair](howto/bank-a-kernel.md).
