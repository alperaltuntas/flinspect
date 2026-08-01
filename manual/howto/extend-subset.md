# Extend the construct subset

The kernel subset grows **pull, not push**: a construct enters only when a
real kernel demands it, and it enters through the conformance-fixture
workflow below. The unit of work is a *construct*, not a kernel — the CW84
kernel of the case studies entered as three constructs (logical IF
statement, unary minus, the control-flow join), each with its own fixtures.

## The workflow, fixture first

**1. Distill the construct into a minimal fixture.** Before touching any
extractor, write the smallest self-contained program exhibiting the construct.
Fortran fixtures live in `tests/f90/` (source + committed with-sema dump);
C++ fixtures in `tests/cpp/` (source only — clang JSON is never committed,
because its node IDs are nondeterministic; a three-line prelude mirrors
`amrex::Real`/`_rt` so no include paths are needed).

For Fortran, regenerate the dumps with the pinned flang:

```console
$ cd tests/f90 && ./gen_ptree_files.sh
```

The script writes through a temp file (a sema failure leaves the previous
fixture intact), cleans up side-effect `.mod` files, and stamps
`flang --version` into `tests/f90/PROVENANCE`. Two constraints it will
enforce the hard way: fixtures must be *semantically valid* Fortran (no dump
otherwise), and self-contained in one file (a cross-file USE needs `.mod`
files built in order).

**2. Add the manifest row.** `tests/f90/MANIFEST.md` (or
`tests/cpp/MANIFEST.md`) maps construct → fixture → parser code path. This is
what turns an LLVM upgrade from an archaeology project into a checklist — see
[Port to a new LLVM](new-llvm.md).

**3. Write the refusal tests first.** Pin the current behavior: the construct
refuses today, with a message naming it. Then decide the *boundary* of the
extension and pin its edges too. The join extension is the model: it admitted
one shape (single-branch `if`, branch bodies assigning only to outputs) and
added refusal tests for elseif-chain joins and non-output assignments inside
joined branches — the old blanket refusal test was retired only because that
exact shape became the supported one.

**4. Extend the extractor by exactly the construct.** Touch the narrowest
layer: a new dump node shape belongs in `frontend/flang_kernel.py` (or
`clang_kernel.py`), new IR vocabulary and pass logic in `kir.py`, new
rendering in `lean_printer.py`. Take expression structure from the tree,
never from unparse text.

**5. Golden-test the printed Lean.** The fixture's generated def is committed
as a golden expectation in `tests/test_kir_lean.py` — the contract layer that
must keep passing regardless of dump-format drift.

**6. Prove something with it.** An extension is done when a real kernel uses
it and its equivalence theorem compiles — and when regenerating shows the
extension changed **nothing retroactively**: the previously banked defs must
come out byte-identical (this has held for every extension so far, and
`groundline kernel verify` checks it for free).

## If the semantics is the question, stop

Some extensions are parsing work; some are *semantic decisions*. Admitting
plain-DO nests was the latter — modeling a sequential loop as a pointwise
map asserts something the source doesn't say, and that decision was raised
explicitly and then discharged properly, with a
[proved schema lemma](../concepts/pointize.md) rather than an assertion in
Python. If your construct changes what a model *means* (reductions,
recurrences, masks — see [Limits](../limits.md)), the extraction gate is the
easy half; budget for the Lean half, and don't ship the gate without it.
