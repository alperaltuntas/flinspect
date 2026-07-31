# Two IRs, one frontend layer

groundline has two faces that consume the *same* compiler syntax trees for two
very different purposes, and the architecture keeps them strictly apart.

## The relational IR: broad and shallow

The original, top-down face (the "relational track") models a whole codebase
as **entities and relations**: modules, subroutines, interfaces, derived
types; USE dependencies, containment, and call edges stratified by resolution
confidence. It is deliberately *shallow* — it records that `subroutine a`
calls `subroutine b`, never what `a` computes. Its consumers are structural:
dependency graphs, call-graph queries, an interactive explorer. It lives in
`groundline/ir.py` and is introduced in [The relational track](../relational.md).

## The kernel IR: narrow and deep

Track B needs the opposite projection: for **one** procedure (or one loop nest
inside a procedure), a *complete, typed* expression and statement tree — every
literal's spelling, every parenthesis, every guard — deep exactly where the
relational IR is shallow. That is the **kernel IR** (`groundline/kir.py`), and
it has exactly one consumer: the [Lean printer](printer-fidelity.md).

## Why they are separate

The two IRs share the frontend layer (dump ingestion, tree parsing, the
conformance corpus) and nothing else. Two rules, stated in the design docs and
enforced in review:

1. **Do not bloat the relational IR.** A field only the Lean printer needs
   never appears in `groundline/ir.py`. A reasoning layer built on a muddled
   abstraction can't be rescued by good code, and "one IR to serve both" would
   be exactly that muddle: relational consumers would drag around expression
   trees they never read, and the semantic track would inherit invariants
   designed for whole-codebase queries.
2. **The kernel-IR → Lean path is trusted-base code.** It must stay small,
   deterministic, and auditable ([why](trusted-base.md)); tying it to the
   relational machinery would grow the trusted base for no verification
   benefit.

## One seam shape, twice

Each track hides its format-specific machinery behind one deep method. The
relational seam is `Frontend.extract(sources) -> IR`; the Track B mirror is
`KernelFrontend.extract(spec) -> Kernel` (`groundline/frontend/kernel_base.py`),
implemented twice:

- `FlangKernelFrontend` — consumes pre-generated flang **with-sema parse-tree
  dumps** (text); addressed by `FortranKernelSpec(dump, subroutine[, nest,
  def_name])`.
- `ClangKernelFrontend` — invokes `clang++ -ast-dump=json` itself; addressed
  by `CppKernelSpec(header, function, include_dirs, clang)` — the toolchain
  travels in the spec because it is part of the kernel's identity.

What differs between the two languages is only the *address* of a kernel;
everything downstream — the kernel IR, [pointize](pointize.md),
[functionalize](functionalize.md), the printer — is shared and knows nothing
about either compiler. That shared spine is what made the C++ side cheap to
add: the control-flow join machinery banked for a Fortran kernel worked for
its C++ twin untouched, and the whole clang frontend needed zero changes when
it later met an AMReX-free standalone header.
