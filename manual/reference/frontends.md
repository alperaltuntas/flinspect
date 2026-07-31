# The two frontends

Both frontends implement the same seam — `extract(spec) -> Kernel` — and
produce the same [kernel IR](../concepts/kernel-ir.md); everything below the
seam is format-specific, everything above it is shared. Both are trusted-base
code: deterministic, structural, refusing.

## `frontend/flang_kernel.py` — Fortran, from flang with-sema dumps

**Input.** A flang **with-sema** parse-tree dump
(`flang -fc1 -fdebug-dump-parse-tree file.f90`). With-sema matters: the
production pipeline emits it, semantic analysis has resolved names and kinds,
and — a practical constraint — flang emits *no dump at all* on a semantic
error, so dumps of real code require a full ordered build with `.mod` files.

**How it reads.** The dump text is parsed into a literal node tree first (one
node per `A -> B -> C` chain element, children attached by `|`-depth), then
walked structurally. Two format facts the parser absorbs so callers never see
them: leaf payloads come both quoted (`Name = 'x'`) and unquoted
(`Intent = In`), and expression structure is taken **from the tree, never
re-parsed from unparse text** — the unparse annotations rewrite literals
(`12.0` resurfaces as `1.2e1_8`) while the structured `Real = '12.0'` leaf is
stable.

**Two extraction modes** (one spec type, `FortranKernelSpec`):

- *whole subroutine* — the subroutine's declarations become params/locals
  (undeclared dummies refuse), its execution part becomes the body;
- *inline loop nest* (`nest = N`, `def_name`) — loop nest #N by source-order
  ordinal; the enclosing subroutine's declarations are inherited
  *tolerantly* — a declaration outside the subset poisons only its own names,
  and extraction refuses iff the nest references one.
  [How-to](../howto/inline-loops.md).

**Notable refusal boundaries** (complete list in [the catalog](refusals.md)):
non-intrinsic calls, strides in loop control, elseif-join shapes, literal
kinds beyond real/int, chained `a%b%c` component paths.

## `frontend/clang_kernel.py` — C++, from clang JSON ASTs

**Input.** The frontend invokes clang itself:
`clang++ -std=c++20 -fsyntax-only -Xclang -ast-dump=json -Xclang
-ast-dump-filter <function>`, plus the manifest's `-I` dirs. A header is
wrapped in a one-line translation unit (`#include`) in a temp directory,
mirroring how a real build consumes it.

**The JSON is an in-memory intermediate, never persisted.** clang's node
`id` fields are memory addresses — nondeterministic across runs — so raw
dumps must never be committed or golden-compared; assertions belong on the
extracted IR or the printed Lean, both address-free. The `clang++ --version`
line and the full flag set are stamped into the generated module's header.

**The cast allowlist — the load-bearing refusal.** clang wraps almost every
read in `ImplicitCastExpr`, and unwrapping them wholesale would be exactly
the plausible-but-wrong-model failure mode: cast kinds like
`IntegralToFloating` *change the value*. Exactly two kinds are allowlisted,
each argued value-preserving:

- `LValueToRValue` — a variable read; pure value-category bookkeeping;
- `FunctionToPointerDecay` — a function name decaying to a pointer in callee
  position; no data value involved.

Anything else refuses — pinned by a fixture where `b + 1` produces an
`IntegralToFloating` cast and must raise.

**Intent mapping.** `Real &` → `inout`; `const Real` by value → `in`.
Everything else — pointers, const refs, plain mutable by-value `Real`,
non-Real types, default arguments — refuses. Outputs are the `Real &`
parameters in declaration order. The mapping keys on the *qualType spellings*,
not on where the `Real` alias comes from — which is why the AMReX-free
quickstart header needed zero frontend changes.

**No pointize.** TIM kernels are already per-point scalar functions, so
extraction emits a rank-0 `Kernel` directly; `functionalize` and the printer
are reused unchanged — the control-flow join machinery is frontend-agnostic.

**Format notes worth knowing** (from the original survey, all pinned):
`amrex::Math::abs`'s callee carries no namespace qualifier in the JSON
(acceptance is on the referenced declaration's name, found through amrex's
`using std::abs`); `FloatingLiteral.value` is the shortest round-trip form
(`3.0_rt` → `'3'`), which lands on the same Lean numerals as the Fortran
side; `else if` arrives as an `IfStmt` in the else slot and is kept nested,
which functionalize turns into the same if-expression chain as flang's
elseif blocks.

## One cross-language asymmetry, deliberate

C++ unary minus binds tighter than `*`, so `-2.0_rt * x` parses as
`(-2) * x`; Fortran's R1008 makes `-2.0*x(i)` the negation of the whole term,
`-(2 * x)`. The generated models on the two sides deliberately print these
*differently* — each mirrors its own source's parse — and the equivalence
theorems absorb the difference. A frontend that "harmonized" them would be
editorializing about semantics, which is the prover's job.

## Conformance corpora

- `tests/f90/` — Fortran fixtures: source + **committed dump** + PROVENANCE
  (flang version stamp); manifest `tests/f90/MANIFEST.md` maps construct →
  fixture → parser code path.
- `tests/cpp/` — C++ fixtures: source only (see above on JSON); a 3-line
  prelude mirrors `amrex::Real`/`_rt`/`Math::abs` so no include paths are
  needed; gated on `clang++` being on `PATH`; sibling `tests/cpp/MANIFEST.md`
  (its drift axis is the clang JSON schema, not a dump format).
