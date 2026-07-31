# Refusal catalog

Every site in the pipeline that raises `UnsupportedConstruct`, what triggers
it, and why it refuses. This list is the method's honesty made visible: what
is *not* here is modeled exactly, and anything that hits one of these sites
fails loudly instead of producing a plausible-but-wrong model
([why that matters](../concepts/kernel-ir.md)).

The catalog is complete as of this manual's writing — it was compiled by
`grep -n "raise UnsupportedConstruct"` over the four trusted-base modules
(77 sites), and each entry's message text is greppable in the source. Related
but distinct: a malformed *manifest* raises `ManifestError`
([manifest rules](manifest.md#general-rules)), and clang/file-system failures
raise ordinary errors — neither is a subset refusal.

## Fortran extraction (`frontend/flang_kernel.py`)

### Structural guards on the dump tree

These fire when the dump's shape differs from what the construct grammar
implies — the early-warning surface for dump-format drift (see
[Port to a new LLVM](../howto/new-llvm.md)).

| Trigger | Why it refuses |
|---|---|
| an expected child node is absent (`expected child '<name>' under '<node>'`) | the dump shape moved, or the construct is a variant the walker has not been taught; guessing a different child would misread the tree |
| a node expected to have exactly one child has several (`expected exactly one child`) | same — structural ambiguity is never resolved by picking one |
| a subroutine is found zero or several times (`found N definitions`) | the kernel's address must be unique to be meaningful |
| `LoopBounds` without a leading index name | unrecognized loop-control shape |
| an unrecognized loop control (`loop control '<node>'`) | only `do concurrent` headers and plain counted `do` loops are modeled |

### The construct subset

| Trigger | Why it refuses |
|---|---|
| literal kinds other than real/int (`literal kind '<kind>'`) | only real and integer literals are modeled (no logical/character/complex) |
| a call to anything but a supported intrinsic (`call to '<name>' (not a supported intrinsic)`; the set is `abs`) | an unmodeled callee makes the model wrong by omission; user procedures are out of scope by design |
| an unrecognized expression node (`expression node '<node>'`) | catch-all: the expression grammar outside literals, designators, parentheses, negation, binary ops, comparisons, and intrinsic calls is unmodeled |
| an array-element base that is not a plain name or single component (`array-element base`) / an unrecognized data reference (`data reference '<node>'`) | only `x`, `x(i,j,k)`, `base%comp`, `base%comp(i,j,k)` are modeled |
| a chained component path `a%b%c` (`component base '<node>' (only single-level base%comp is supported)`) | multi-level component reads have no synthesized-parameter rule ([rule B](../concepts/pointize.md#component-reads-rule-b)) |
| an unrecognized executable construct (`executable construct '<node>'`) | only assignments, IF constructs, and do-constructs may appear in a kernel body |
| an unrecognized action statement (`action statement '<node>'`) | within a body, only assignment and the one-line logical IF statement are modeled |
| an unrecognized `IfConstruct` child (`IfConstruct child '<node>'`) | if/elseif/else blocks only — no construct names, no other clauses |
| `do concurrent` with a stride / plain `do` with a stride | a strided box is not the full index box the iteration schemas model |
| an unsupported intrinsic type (`intrinsic type '<type>'`) or type spec (`type spec '<node>'`) | only `real`, `integer`, and (as dummies) derived types are declared into kernels |
| an unsupported declaration attribute (`attribute '<node>'`; whole-subroutine mode) | `intent` and `dimension` are understood; `optional`, `pointer`, etc. change semantics the model doesn't carry |
| a dummy argument with no declaration (`undeclared dummy args`) | a parameter of unknown type/intent cannot be modeled |

### Inline-loop addressing (rule B; `extract_loop_kernel`)

| Trigger | Why it refuses |
|---|---|
| nest ordinal out of range (`loop nest N requested, but the subroutine has M`) | ordinals are the address; a silent clamp would extract the wrong loop |
| the addressed nest references a name whose declaration was rejected (`loop nest N references '<name>' — <reason>`) | declarations are inherited [tolerantly](../howto/inline-loops.md) — poison is per-name, and only a *referenced* poisoned name refuses |

## C++ extraction (`frontend/clang_kernel.py`)

### Function shape

| Trigger | Why it refuses |
|---|---|
| the function found zero or several times in the dump (`found N definitions`) | unique address, as on the Fortran side |
| non-`void` return type | TIM point kernels return through `Real &` parameters; a return value is a different calling convention |
| parameter type other than `Real &` / `const Real` (pointers, const refs, mutable by-value, non-Real, …) | the [intent mapping](frontends.md) is deliberately total on exactly two spellings |
| a parameter with a default argument | a defaulted parameter changes the function's arity story; never appears in TIM kernels |
| unexpected children of the function declaration, multiple bodies, or no body | structural guards on the JSON shape |
| locals shadowing parameters (`locals shadow parameters`) | shadowing would silently redirect reads in the flat `let` model |

### Statements and declarations

| Trigger | Why it refuses |
|---|---|
| any statement other than a declaration, an assignment, or an `if` (`statement '<kind>'`) — so `for`, `while`, `+=`, `return`, … | the C++ subset mirrors the Fortran one: straight-line assignments and structured ifs |
| a declaration that is not a `VarDecl` (`declaration '<kind>'`) | only plain local variables are modeled |
| a local of any type but `Real`/`const Real` (`local '<name>': type '<qual>'`) | only real scalars exist in the kernel IR |
| a local without a copy-initializer (`= form`) | an uninitialized or direct/list-initialized local does not map to `let name := value` |
| a local declared more than once | C++ block scoping does not map to the flat `Let` model; renaming would break the by-eye audit |
| an assignment whose target is not a (reference) parameter | writes must go to outputs; anything else is outside the state-threading model |
| assignment/binary nodes with unexpected operand counts; `if` with an init-statement, condition variable, or `constexpr`; unexpected `if` child counts | structural guards on the JSON shape |

### Expressions and the cast allowlist

| Trigger | Why it refuses |
|---|---|
| **an implicit cast not on the allowlist** (`implicit cast kind '<kind>' is not on the value-preserving allowlist`) — only `LValueToRValue` and `FunctionToPointerDecay` pass | the load-bearing refusal: cast kinds like `IntegralToFloating` *change the value*; unwrapping them wholesale is exactly how a plausible-but-wrong model would slip in |
| a reference to anything but a parameter or local (`only parameters and locals are supported in expressions`) | globals, members, and enumerators are outside the model |
| unary operators other than prefix `-` | only negation is modeled |
| binary opcodes outside `+ - * /` and the six comparisons (so `%`, `&&`, bit-ops, …) | unmodeled arithmetic |
| calls to anything whose referenced declaration is not `abs`, calls with no callee or a non-`DeclRefExpr` callee, `abs` with ≠ 1 argument | same intrinsic policy as Fortran |
| user-defined literal with an unexpected shape, a suffix other than `_rt`, or a non-`FloatingLiteral` operand | only AMReX's `_rt` real literals are modeled |
| any other expression node (`expression node '<kind>'`) | catch-all |

## Pointize (`groundline/kir.py`)

| Trigger | Why it refuses |
|---|---|
| the body is not exactly one do-concurrent or plain-do nest | pointize models one loop nest; prologue/epilogue statements would be silently attributed to every iteration |
| duplicate loop index in a plain-do nest | the schema lemma requires a duplicate-free enumeration |
| a do-construct inside the loop body | the nest is not perfectly nested — the pointwise model has no place for an inner loop |
| an array reference not indexed exactly by the loop indices (offsets like `p(i,K+1)`, partial indexing, non-variable subscripts) | not point-local: reads another iteration's cell — the k-recurrence boundary ([case study](../case-studies/edge-thickness-upwind.md#the-boundary-marked-with-a-refusal-fixture)) |
| assignment to a scalar parameter inside a plain-do nest | the accumulator/reduction shape (`s = s + a(i)`): every write must land in the iteration's own cell for the schema lemma's setting to apply |
| assignment to a derived-type component | component *writes* would break rule B's loop-invariance guarantee |
| component read whose base is not an `intent(in)` derived-type dummy | `intent(in)` is what *guarantees* loop-invariance rather than assumes it |
| component read neither a loop-invariant scalar nor an array at exactly the loop indices (e.g. offset subscripts) | outside the two licensed shapes of rule B |
| a synthesized parameter name colliding with an existing name | refuse-don't-rename: a renamed parameter would defeat the by-eye audit of generated Lean against source |
| unsupported assignment targets, unscalarizable expression nodes, non-assignment/If statements in the loop body | catch-alls closing the pass |

## Functionalize (`groundline/kir.py`)

| Trigger | Why it refuses |
|---|---|
| no `inout`/`out` parameters | nothing to return — a kernel with no outputs has no functional meaning |
| assignment to a name that is neither local nor output | an unmodeled state (a global, an index) would be silently dropped |
| statements after an `if` with an elseif chain | the join's merge formula is binary by design ([the join](../concepts/functionalize.md#the-control-flow-join)) |
| a joined branch containing anything but assignments (nested `if`s, …) | the merge is defined only over per-variable assignments |
| assignment to a non-output inside a joined branch | a `let` may not escape its branch |
| any other statement form | catch-all |

## Printer (`groundline/lean_printer.py`)

These are final honesty gates — reachable only if a caller bypasses the
normal pipeline order:

| Trigger | Why it refuses |
|---|---|
| a call the printer cannot spell (anything but `abs`/`min`/`max`) | no invented Lean spelling for an unmodeled callee |
| an `ArrayRef` or `ComponentRef` surviving to printing | pointization was skipped or incomplete — printing them as bare names would silently change meaning |
| a non-real parameter surviving to printing | the generated def's signature is `(… : ℝ)`; anything else must have been dropped or synthesized away |
| unprintable expression/functional nodes | catch-alls |

## One refusal delegated to Lean

One cross-iteration channel is deliberately left to the proof checker rather
than the Python gate: a local scalar **read before its first write** in a
plain-DO body (which would carry the previous iteration's value) prints as an
unbound name, and the generated Lean **fails to elaborate**. Loud, and never
a wrong model — see [Pointize](../concepts/pointize.md#one-gap-closed-by-the-checker).
