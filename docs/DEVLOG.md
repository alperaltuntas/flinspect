# flinspect — Devlog

> **Status:** append-only, newest-first. Each entry is dated and records a
> roadblock and its resolution as it happened. **Do not rewrite past entries** —
> they are the historical record, true as of their date. When an entry produces a
> durable conclusion, graduate that conclusion into `VISION.md` (decisions) or
> `DESIGN.md` (architecture) as a clean statement, and leave the entry here as the
> story of how we got there.
>
> Decision IDs (D1–D5) and weakness IDs (W1–W10) refer to `VISION.md` / `DESIGN.md`.

---

## 2026-07-30 — Notebooks overhauled: a post-seam suite, and the venv made self-sufficient

**What:** replaced the pre-seam notebook collection with a four-notebook
explanatory suite (`notebooks/README.md` + `01_getting_started` →
`04_confidence_queries`) and repaired the venv so `PYTHONNOUSERSITE=1` works for
*everything*. Consumer-side work only — no frontend or IR changes.

- **The venv was not self-sufficient.** Under `PYTHONNOUSERSITE=1`,
  nbformat/nbconvert died on missing `platformdirs`/`attrs` even though
  jupyterlab is a declared dependency — pip had satisfied those transitive deps
  from the (broken) `~/.local` user site at install time, so they never landed
  in the venv. Meanwhile *without* the env var, `import flinspect.explorer`
  fails because the user site's broken pandas shadows the venv. Fix:
  `PYTHONNOUSERSITE=1 .venv/bin/pip install -e '.[dev]'` (re-resolves the tree
  without the user site; pulled in platformdirs, attrs, requests,
  python-dateutil, …). Verified: 99 tests, `jupyter nbconvert`, and headless
  notebook execution all pass under `PYTHONNOUSERSITE=1`; the bare-mode suite is
  unchanged (98 + 1 skip). `~/.local` itself untouched. Launch and install
  commands are documented in `notebooks/README.md` — the env var belongs on the
  *install* command too, or the hole reopens.
- **The old suite (7 tracked notebooks + root `test.ipynb`) is retired.** Only
  the untracked `explorer_TIM_new.ipynb` ran against the current package; the
  rest imported pre-seam APIs (`frontend._nodes`, `e.store[...]`,
  `pf.registry`, `node.program_unit.parse_tree_path`) and referenced dump
  directories that no longer exist. Every `*_TIM*` name was aspirational —
  there is still no TIM corpus (see 2026-05-28 below). Their durable ideas were
  rebuilt, not copied: the reachability analyses ("which FMS2 modules does MOM6
  actually need", the direct API surface) live in `03_module_dependencies` on
  `get_module_dependency_graph()` + IR relations. `environment.yml` went with
  them — its only content beyond `pip install -e .` was pyvis, which only the
  retired notebooks used; the venv flow above is the single documented setup.
- **Suite conventions** (spelled out in `notebooks/README.md`): seam-only
  imports (`flinspect.{ir, parse_forest, graph_view, explorer}`), one parameter
  cell per notebook, corpus root from `FLINSPECT_CORPUS` (glade default),
  outputs committed **stripped**, and every notebook must execute end-to-end
  headlessly (the 69 KB committed-outputs blob does not survive this policy).
  `01_getting_started` is fully portable — it runs off the `tests/f90` fixtures
  and demonstrates the `assumed` stratum with a small hand-built IR, since no
  self-contained fixture produces one (the known dynamic-dispatch manifest gap).
- **Findings recorded, not fixed** (this was a consumer-side pass; the package
  is untouched):
  - (a) **The IR carries no source provenance.** Corpus-level analyses want
    "which source tree defined this module"; the pre-seam notebooks read a
    `parse_tree_path` node attribute that rightly no longer exists. Workaround
    in `03`: extract each corpus subdirectory separately and attribute modules
    by where they are defined. Whether provenance becomes an IR fact is a
    deliberate decision for later, not a notebook's call.
  - (b) `ParseForest.get_call_graph()` **prints** an unresolved-count line on
    every call — noisy for library consumers; candidate cleanup.
  - (c) 84 call events originate from `program` units or module-level code and
    therefore appear in the relations but not as call-graph edges (nodes are
    subroutines/functions only) — noted where visible (`04`).
  - (d) The module dependency graph carries two **self-loops**
    (`mom_diag_buffers`, `mom_io_file` — same-module EXTENDS edges), so
    `nx.is_directed_acyclic_graph` is False even though no multi-module cycle
    exists; `03` checks strongly-connected components instead.

Corpus replay unchanged: 458 files, 0 errors, resolved 22,764 / assumed 165 /
unresolved 1,527.

---

## 2026-07-30 — Phase 3 landed: the Explorer shows what it knows (and what it doesn't)

**What:** completed Phase 3 (DESIGN §4) — Explorer correctness. W5 is closed, the
D3 confidence strata are now visible rather than merely stored, and the part of
the Explorer worth testing no longer needs a browser.

- **W5 was half-fixed and the docs didn't know it.** Phase 1a's IR rewrite already
  keyed cytoscape nodes by the scope-qualified `Entity.id` with `name` demoted to a
  display label, so the merge bug was gone; the W-table row still cited
  `explorer.py ('id': node.name)`. What was genuinely missing was a *pin* (the
  Explorer had zero tests) and any display of confidence. Verified end-to-end
  before touching anything — selector options, cytoscape node/edge data, and
  `get_call_graph()` nodes all keep three same-named routines apart — then pinned
  it. The row now reads "fixed in Phase 1a (identity) + Phase 3 (pinned,
  confidence shown)".
- **New fixture `test_name_collision`** (D7 corpus work): three modules each
  defining `apply_bc` with an *identical* signature, so the name is all they share
  and a name-keyed consumer would collapse three nodes into one. The caller reaches
  each through a different USE form — wildcard-with-rename, only-list, only-list
  with rename — which is also what keeps the file legal (three wildcard USEs would
  make the bare name ambiguous). That closes the manifest's **USE renames** gap:
  both rename forms had no fixture, only hand-built-registry unit tests.
- **Found while writing it:** the only-list rename form projects onto
  `Use(only=(), renames=(('bc_c','apply_bc'),))` — an *empty* only-list, which the
  `Use` docstring reads as "whole module". Resolution is unaffected (it follows the
  rename, and the corpus numbers are unchanged), so this is a fact-recording bug in
  the projection, not a resolution bug. Out of scope here (frontend), recorded in
  `tests/f90/MANIFEST.md`; the new test asserts the renames and deliberately not
  the only-list, so nothing pins the wrong fact.
- **Confidence rendering.** Call edges take their line style from the stratum
  (solid `resolved`, dashed `assumed`, dotted + muted `unresolved`); `defined=False`
  targets render ghosted (dashed outline, italic, low opacity) so "we never parsed
  this" reads at a glance; interface-membership edges get their own colour and
  arrowhead because they are structure, not calls, and carry no confidence. The
  pre-existing direction encoding stays on the *colour* channel, so the two
  encodings compose instead of fighting. A legend in the widget makes the whole
  scheme discoverable — the point of the phase is that partial knowledge is
  visible, which it isn't if you have to read the stylesheet to decode it.
- **Extracted `flinspect/graph_view.py`** — the pure half: IR + center entity →
  neighbourhood → list of `{'data', 'classes'}` element dicts, with no ipywidgets
  or ipycytoscape import, hence unit-testable without a kernel or browser
  (`tests/test_graph_view.py`). `explorer.py` keeps the stylesheet, the legend and
  the event wiring and nothing else; rendering is not the seam (principle #10), but
  the *content decisions* turned out to be exactly the testable part.
- **Two bugs fell out of the extraction.** (a) `classes` is a top-level cytoscape
  element attribute, not a data key — the old code passed `'classes': 'selected'`
  *inside* `data`, so the `node.selected` style (the purple border on the focused
  node) had never applied. Now set via `ipycytoscape.Node(classes=...)` and pinned.
  (b) `enclosing_module_name` returned "Unknown Module" for entities whose scope is
  named but not defined in the parsed set; module-qualified unresolved targets
  (`netcdf::nf90_open`) now group under their own module.
- **Stratum labels moved to the seam.** `RESOLVED`/`ASSUMED`/`UNRESOLVED` and a
  per-edge `IR.call_confidence(caller, callee)` lookup now live in `ir.py` as a
  *computed view* — the strata remain pure relations (D3 is untouched), but the two
  consumers that must *say* which stratum an edge came from no longer each
  re-implement three membership tests. `get_call_graph()` attaches `confidence` to
  every NetworkX edge and gained `must_only=True` (build from `calls_must`); it
  filters edges only, so `defined=False` targets remain as isolated nodes — the
  node set is still "every subroutine/function in the IR".

**Corpus replay (458 files, unchanged since 2026-05-28):** 0 file errors; the
element builder ran over all 7,108 browsable entities in ~29 s producing 45,437
resolved / 329 assumed / 3,046 unresolved call edges and 2,103 membership edges
across the neighbourhoods (edges are counted once per neighbourhood they appear
in), with 2,035 ghosted undefined node instances — 268 of them grouped under
`netcdf`, courtesy of the fallback above.

**One number doesn't reproduce, and it predates this phase.** Replaying the corpus
gives `resolved 22,764 / assumed 165 / unresolved 1,527`, whereas the Phase 2 entry
below records `22,764 / 114 / 1,578`. `resolved` matches exactly and so does
may (24,456) — the entire difference is 51 edges sitting on the
`assumed`↔`unresolved` boundary. Checked: the corpus files are untouched since
May, the split is insensitive to file order (identical sorted vs. reversed), and a
replay at `HEAD` *before* this phase's commits gives 165/1,527 too — so this is not
a Phase 3 regression but a discrepancy in how the Phase 2 figure was captured
(most likely measured before the last of that phase's frontend fixes landed).
Entries are append-only, so the number below stays as written; the reproducible
figures are these.

Suite: 99 tests green (70 → 99: name-collision IR + call-graph identity, the
graph_view element/strata/ghosting tests, the call-graph confidence attribute).
The `assumed` stratum is pinned against a hand-built IR rather than a fixture —
only genuine dynamic dispatch produces it and that construct still has no
self-contained fixture (manifest gap) — which is legitimate above the seam, where
the input is an IR, not a dump. Note `tests/test_graph_view.py` instantiates the
widget once as a smoke test, so the whole suite now wants `PYTHONNOUSERSITE=1` on
machines where a broken user-site pandas shadows the venv (documented in the test
module).

---

## 2026-07-29 — Phase 2 landed: sema's answers replace the hand-rolled resolver

**What:** completed Phase 2 (DESIGN §4) — soundness & resolution quality. The IR's
call relation is now stratified by confidence (D3), call resolution is *read from
sema* instead of re-derived, and the heuristic inference engine is gone (W1, W2,
W4, W6). Landed as two code commits (IR stratification; frontend resolution
overhaul) plus this docs pass.

- **IR (D3):** the single `calls` set became three pure relations —
  `calls_resolved` / `calls_assumed` / `calls_unresolved` — with `calls` (may)
  and `calls_must` (must) as computed union views, so existing consumers kept
  working unchanged. Unresolved *targets* are first-class entities with
  `defined=False` (scope-qualified `module::name` when the use-chain or sema's
  mangling pins the module, bare name atoms otherwise), replacing the
  `(caller, name)` `unresolved_calls` side-table. The old silent drop of `mpi_*`
  calls is gone too.
- **Attribution turned out cleaner than feared.** DESIGN Q2 warned the unparse
  annotation is per-*statement*, leaving `a = f(x) + g(y)` one string to split
  across two calls. In fact every `Expr` node carries its own annotation, and a
  `FunctionReference`'s *parent* `Expr` line is exactly the resolved text of that
  one call (`Expr = 'area_r(y)'`); `CallStmt` lines annotate themselves. The call
  pass keeps a stack of enclosing annotated `Expr`s, so each recorded call event
  gets its own resolved text and no cross-call attribution heuristic exists.
- **The mangling rule (Q1 caveat), derived empirically** from all 994 distinct
  mangled names in the corpus: always exactly three components,
  `imported$owner$specific`. One subtlety found the hard way: the middle
  component is the module that owns the specific's *symbol*, which is usually but
  not always its definition site — `fms2_io_mod$fms2_io_mod$compressed_read_2d`
  names a subroutine whose body lives in netcdf_io_mod (fms2_io_mod holds it by
  use-association), so demangled lookup follows the owner module's use-chain
  before falling back to a `defined=False` entity. Rule + fixture:
  `frontend/_flang_text.py::demangle`, `test_private_specifics`.
- **Type-bound calls:** sema resolves *static* dispatch in the unparse by
  hoisting the object into the argument list (`call obj%reset()` →
  `'CALL reset_bounds(obj)'` — even for `=>`-renamed and private impls), so those
  edges are `resolved`. *Dynamic* dispatch (polymorphic receiver, deferred
  binding) keeps the `obj%binding(...)` shape; those edges are classified through
  the declared type's binding table as `assumed` (an override may win at
  runtime), or `unresolved` when the receiver's type is unknown. Three latent
  binding-table bugs were fixed on the way: `generic :: g => a, b` was recorded
  as `g => b` (last name won), `procedure :: a, b, c` as `a => c`, and inherited
  bindings (EXTENDS chain) were never searched.
- **Retired (W1, W6):** `resolve_interface_procedures`, `_procedure_matches`,
  `_types_compatible`/`_ranks_compatible`/`_kinds_compatible`, all `_infer_*`
  call-site type/rank/kind inference, per-argument parsing in the call pass, the
  `DoublePrecision → 'r8_kind'` MOM-ism, and `get_subroutine_by_name` (the last
  `endswith` lookup, already dead). Variable *type* tracking survives — it types
  `obj%binding()` receivers — and signature parsing (types/ranks/kinds/optional)
  survives as entity facts. **No-sema input support is dropped** (decided with
  the maintainer; D4 made it redundant): nothing rejects a no-sema dump, but it
  is untested and unadvertised — generics would degrade to `assumed` fan-out.
- **Scope/visibility-correct lookup (W4):** the frontend now parses
  `AccessStmt`s (module default + per-name overrides), and `find_named_entity`
  crosses a wildcard USE only for names the used module makes public, follows
  only-lists/renames as before, and searches a routine's own USE statements
  before its enclosing unit's. Only-list imports are deliberately not
  visibility-checked (flang already validated them).

**Production corpus (458 MOM6+FMS2 with-sema dumps): 0 file errors; 42,199 call
events → resolved 22,764 / assumed 114 / unresolved 1,578** (may = 24,456,
must = 22,764; `resolved` is 93% of may). The may count sits 15% below the
Phase 1b baseline (28,931), outside the "few percent" acceptance band, so the
delta was decomposed edge-by-edge against a baseline replay rather than accepted:
- **6,655 edges removed**, of which 6,639 are fan-out siblings — edges to *other*
  members of a generic the caller invoked, i.e. exactly the W2 over-approximation
  this phase existed to eliminate. The residual 16 were inspected individually:
  all are corrected wrong edges (self-edges from dynamic dispatch resolved to the
  caller's own generic sibling, and name-coincidence binding matches like
  `reopen_mom_file → mom_io_infra::file_is_open` from the old
  search-all-types-for-a-binding heuristic).
- **2,180 edges added**: 1,578 first-class unresolved edges (the old
  `unresolved_calls` side-table, now real may-edges) plus ~600 correct edges the
  old engine could not find — demangled cross-module targets, `use`-renamed
  callees, and module-pinned externals (`netcdf::nf90_get_var_fourbyteint`,
  courtesy of the mangling).

Suite: 70 tests green (3 new fixtures: `test_external_calls`,
`test_type_bound_generic`, `test_private_specifics`; the retired engine's tests
replaced by attribution/demangle/visibility coverage, not dropped).

**Known residue, recorded not hidden:** (a) a function reference nested in
another call's argument list is still not recorded as a call site — a
long-standing under-approximation, now documented at the skip site (W2 residue);
(b) the hardcoded intrinsic list still filters function references, and names it
misses (`sqrt`, `loc`, `exp` are absent) surface as bare-name unresolved atoms —
same behaviour as the baseline, now at least visible in the unresolved stratum;
(c) dynamic dispatch lands on the *declared* type's impl as `assumed` — a later
phase could fan out over the EXTENDS overrides instead.

---

## 2026-07-29 — Phase 1b landed: fixtures and production now parse the same dump

**What:** completed Phase 1b (DESIGN §4) — tests and production consume the *same*
dump variant at last, closing the mismatch Phase 0 flagged (and W1/W3's fixture
half). Deliberately a **format adaptation only**: the hand-rolled resolution engine
and the IR's call semantics are untouched, so the diff stays reviewable. Retiring
the engine in favour of sema's answers is Phase 2.

- **Packaging first** (W10, plus a bug): `requires-python` relaxed from the
  `>=3.14,<3.15` hard pin to `>=3.11`, and `packages = ["flinspect"]` replaced with
  setuptools *discovery* — the explicit list silently omitted `flinspect.frontend`
  after the Phase 1a split, so the installed package was broken. Added a `dev`
  extra (pytest). W10 is closed.
- **Three helpers absorb the format difference** (`frontend/_flang_text.py`):
  `node_path` (match structure while ignoring an unparse annotation),
  `unparse_text`, and `splice_annotated_child` — which collapses an annotated
  `Expr` and its child back into *exactly* the single line a no-sema dump emits, so
  the existing structural matchers keep working verbatim. Three call sites changed:
  the `CallStmt` assert, argument type inference, and kind extraction (which would
  otherwise have gone silently `None` on every kind-selected declaration in real
  code — the failure mode no fixture would have caught, since none uses a kind).
- **Fixtures regenerated with-sema.** `gen_ptree_files.sh` drops `-no-sema`, writes
  through a temp file so a sema failure leaves the previous fixture intact and
  reports flang's diagnostics, cleans up the `.mod` files the dump emits as a side
  effect, and stamps `tests/f90/PROVENANCE` with `flang --version` (Q1: the format
  has no stability contract, so a format change should show up as a version delta).
- **`test_optional_args.f90` redesigned** — see the spike entry below; its two
  specifics now differ in their first argument's type, which is what makes the
  generic legal, while the optional dummies and the 3-/4-argument and keyword calls
  still exercise argument-count and keyword matching.
- **New fixture `test_generic_function`** — a generic *function* in an assignment.
  It is the only fixture exercising the `FunctionReference` path at all: the one
  named for it (`test_func_ref_array`) never contained a `FunctionReference` under
  either dump variant, since flang resolves `fields(i,:,:)` to an `ArrayElement`.
  What that fixture actually covers is rank reduction by a scalar subscript; its
  test section now says so instead of implying coverage we didn't have.

**Evidence it worked, twice over:**
- *Equivalence on fixtures* — for all six fixtures that survive sema unchanged, the
  no-sema and with-sema dumps project onto a **byte-identical IR** (entities,
  signatures, `calls`, `contains`, `uses`, `interface_members`, unresolved calls).
  The adaptation adds no facts and loses none; only the input shape changed.
- *The production corpus* — replaying the 458 surviving with-sema dumps from the D4
  run (`bin/flang_ptree/MOM6_using_FMS2`, MOM6+FMS2): **346 file errors → 0**, and
  **177 → 28,931 call edges** (1,707 unresolved, first-class per D3). The
  pre-Phase-1b frontend failed on every file containing a `CALL`, so before this
  change the production input was effectively unparseable while the tests were
  green — the exact hazard of tests and production disagreeing. Entity counts are
  identical before and after, confirming the change is confined to the call pass.

Suite: 49 tests green (37 pre-existing, unchanged in intent, + 12 new).

---

## 2026-07-29 — Phase 1b spike: what with-sema actually changes

**Context:** DESIGN §4 required spiking before switching fixtures — D4 validated
dump *generation*, not that the string-matching parser could *consume* with-sema
output.

**Findings.** Structure and interface parsing pass unchanged; `parse_calls` failed
on **every** file. Only four node types gain an unparse annotation — `CallStmt`,
`AssignmentStmt`, `Expr`, `Variable` — which is why the blast radius was small:
`SubroutineStmt`, `UseStmt`, `ModuleStmt` and friends are untouched. Two shapes to
absorb:

1. Statements carry the source they unparse to *after* resolution:
   `ActionStmt -> CallStmt = 'CALL compute_real(r,1_4)'`. The old
   `line.endswith("ActionStmt -> CallStmt")` assert fails on all of them.
2. An annotated `Expr` occupies its line, pushing its structural child one level
   deeper — so an operator that used to sit on the `Expr` line (`-> Add`) now sits
   on the child, and literals gain kind suffixes (`1_4`, `.true._4`).

**Q2 answered — yes, positively.** The unparse annotation carries the
sema-**resolved** specific procedure while the structured child still shows the
generic (`ProcedureDesignator -> Name = 'compute'`). Verified for generic
subroutine calls, generic function references, and type-bound generics. So the
textual dump is enough; `-fdebug-dump-symbols` is not needed for this.

**Caveat found later, not in the original spike:** the resolved name is *not*
always a plain identifier. Where only the generic is USE-imported (so the specific
isn't accessible by name in that scope), flang emits a mangled, fully-qualified
form — `mpp_mod$mpp_mod$mpp_error_basic`, seen throughout the FMS corpus. Phase 2
must demangle `module$module$specific` rather than assume an identifier. Phase 1b
therefore only *records* the raw text (`ParseTree.call_unparse`, below the seam,
unused) as a hook, and leaves callee extraction on the structured tree.

**`test_optional_args.f90` was invalid Fortran all along.** Sema rejects it:
"Generic 'init' may not have specific procedures 'init_simple' and 'init_advanced'
as their interfaces are not distinguishable" — `init_simple(x, n)` and
`init_advanced(x, n, tol, debug)` are ambiguous for a 2-argument call, because the
extra dummies are optional. It only ever compiled because `-no-sema` never checked.
A lesson about no-sema fixtures generally: they can encode Fortran that no compiler
would accept, so the facts derived from them can describe programs that cannot
exist.

---

## 2026-06-18 — Phase 1a landed: the IR seam

**What:** completed Phase 1a (DESIGN §4) — the structural half of the seam, as a
pure refactor with fixtures still on no-sema.

- `flinspect/ir.py`: the relational IR per DESIGN §2.1 — entities as frozen value
  objects keyed by scope-qualified `EntityId`, relations as tuple sets,
  `callees`/`callers` derived rather than stored, `unresolved_calls` first-class.
- `flinspect/frontend/` package with the `Frontend` protocol
  (`extract(sources) -> IR`); `parse_tree.py` became `frontend/flang_dump.py` and
  the node/registry/state helpers became its privates (`_nodes`, `_registry`,
  `_state`, `_flang_text`, `_variable_info`). The frontend keeps the interned node
  graph *internally* and projects onto the IR at the boundary (principle #10).
- `lfortran_asr.py` stub raising `NotImplementedError` — the forcing function that
  keeps the IR honest.
- `ParseForest`/`Explorer` rewritten to consume the IR only; per-file fault
  isolation, so one unparseable file is collected as a `FileError` instead of
  aborting the forest (W3, principle #9).
- Tests split along the seam: `tests/test_ir.py` asserts on the IR,
  `tests/frontend/test_flang_dump.py` keeps the below-seam resolution-engine tests.
  `tests/test_parse_tree.py` retired.

**Why it matters:** consumers no longer know flang exists, which is what made
Phase 1b a change to one file's line matching rather than a change everywhere.

---

## 2026-05-28 — Phase 0 landed: docs split + README reset

**What:** completed Phase 0 (DESIGN §4) — "reset expectations."
- Split the single `VISION_AND_PLAN.md` into three living docs: `VISION.md` (why /
  decisions), `DESIGN.md` (how / architecture / roadmap), `DEVLOG.md` (this
  append-only log). Old file removed.
- Rewrote `README.md` to lead with what flinspect *is today* (a structural-
  exploration prototype) and quarantined all the relational/Z3/GPU material under
  an explicit, clearly-disclaimed `# Roadmap / Vision` heading (W9). The detailed
  GPU-porting worked examples were preserved there (they exist nowhere else); the
  README now cross-links the three `docs/` files.

**Why it matters:** W9 (README ~90% aspiration stated as present tense) is closed.
Tests-vs-production dump-variant mismatch and the seam refactor remain for Phase 1.

---

## 2026-05-28 — `--gen-ptree` cannot build AMReX (TIM infra path)

**Context:** ran `./build.sh --gen-ptree --jobs 4` with no `--infra`, so it
defaulted to the **TIM** infrastructure (`libinfra-TIM.a`), which pulls in AMReX.
All prior full-coverage runs used `--infra FMS2`, which never builds AMReX.

**Symptom:** the AMReX CMake configure failed — `which: invalid option -- 'f'`
noise, then `clang: error: no such file or directory: 'testCCompiler.c.o'` during
CMake's compiler-validation step.

**Root cause (structural, not a regression):** the `ncar-flang_ptree.mk` template
is a deliberately *non-compiling, dump-only* toolchain — `CFLAGS` carries
`-Xclang -ast-dump -fsyntax-only` (no object file is ever produced), `FC = flang
-fc1`, `LD`/`AR = echo`. `amrex-utils/Makefile` does `include $(TEMPLATE)` and
builds AMReX via CMake, which begins by compiling+linking a test program. With
`-fsyntax-only` no `.o` exists, so the link fails. The `which flang -fc1`
expansion (`-DCMAKE_Fortran_COMPILER=$(shell which $(FC))`) is the harmless
`which: invalid option` noise. CMake picks up the dump-only `CFLAGS` from the
environment.

**Resolution:** none needed — this is inherent. A non-compiling compiler can't
produce a real library. Guidance: for the parse-tree corpus use `--infra FMS2`
(the proven path, AMReX is external C++/Fortran glue, not MOM6 science code). If
TIM parse trees are ever specifically needed, pre-build AMReX with a real compiler
and pass `--amrex <path>` so `--gen-ptree` skips building it (build.sh only builds
AMReX from the submodule when `--amrex` is absent). Caveat: TIM files that
`use amrex_*` would still need flang-produced `.mod` files for full sema.

---

## 2026-05-28 — FULL COVERAGE: the `FC_AUTO_R8` fix (D4 validated)

**Context:** after the FFLAGS fix, MOM6 sat at 194/340 with all remaining genuine
errors in one class — `REAL(4)`-vs-`REAL(8)` argument-kind mismatches in five
gatekeeper files (`grid`, `MOM_EOS_TEOS10`, `MOM_TFreeze`, `monin_obukhov`,
`sat_vapor_pres`).

**Root cause:** the `ncar-flang_ptree.mk` template omitted
`FC_AUTO_R8 = -fdefault-real-8 -fdefault-double-8` that every *real* MOM6 template
(e.g. `ncar-flang.mk`) uses. Without it flang treated default `real` as `REAL(4)`,
clashing with the r8 dummies in the GSW/TEOS10 equation-of-state code.

**Resolution:** added `FC_AUTO_R8` to the template's `FFLAGS`. Result: **FMS2
104/104, MOM6-infra 14/14, MOM6 340/340, zero genuine errors.** The ~140 MOM6
files previously failing were cascade behind the EOS/TEOS10 chain and resolved
along with the five gatekeepers. **This validates D4** — with-sema over the full
stack works; total enabling cost was four small foundational fixes (this r8 flag,
the FFLAGS reset, the `mpp` TRANSFER `SIZE=` patch, the `mpp_group_update`
optional-arg). D3's no-sema fallback is no longer required for coverage.

---

## 2026-05-28 — Big artificial blocker: FFLAGS pollution (64→194/340)

**Context:** MOM6 coverage was stuck at 64/340 with many `-L<colon-joined-paths>`
"unknown argument" errors. The temptation was to retreat to no-sema; instead we
investigated the `-L` error.

**Root cause:** `activate_llvm.sh` exports
`FFLAGS="-I${INCLUDE_DIR} -L${LIB_DIR}"` with colon-joined paths (invalid on a
compile line), and build.sh's MOM6-stage `mkmf -c "${FFLAGS} ..."` inherited it,
polluting CPPDEFS. A first fix (setting `FFLAGS=""` in build.sh defaults) failed
because `activate_llvm.sh` is sourced *later* and re-exports it.

**Resolution:** reset `FFLAGS=""` immediately after `source activate_llvm.sh` in
build.sh's `flang_ptree` module-load case. MOM6 jumped 64→194/340, 0 unknown-arg
errors. This proved the low coverage was a *build bug*, not flang rejecting MOM6 —
the remaining 146 failures were the r4/r8 class (next entry) plus its cascade.

**Lesson learned:** trust the build.sh-run logs, not standalone `make` probes — a
standalone probe was contaminated by ncarcompilers `-L` injection because it
wasn't run under `module reset`.

---

## 2026-05-28 — Sema scope probe: failures are sparse and foundational

**Context:** with the build plumbing fixed, needed to know whether with-sema was
tractable or an open-ended tail of incompatibilities.

**Findings:** genuine flang↔source rejections are **sparse and foundational** —
only ~4–5 files across FMS2+MOM6 (`mpp`, `grid`, `monin_obukhov`,
`sat_vapor_pres`, `MOM_domain_infra`), clustered in a few error classes sharing a
REAL r4/r8 kind / generic-resolution root. Low coverage elsewhere is *cascade*
behind these gatekeepers, not independent bugs — patching `mpp` alone took FMS2
from 26→103 of 104 files.

**Patches applied (kept):**
- `mpp/include/mpp_chksum_int.fh`: flang's sema rejected `TRANSFER(mask_val,
  i4tmp)` into an array mold ("Dimension 1 of LHS has extent 2, but RHS has extent
  1") — legal Fortran other compilers accept. Fixed with explicit
  `TRANSFER(..., SIZE(i4tmp))`. Because `mpp` is foundational, this unblocked the
  whole FMS2 stack.
- `mpp/include/mpp_group_update.fh`: MOM6 (`MOM_domain_infra`) calls
  `mpp_do_group_update` with a 4th arg `omp_offload` that the stock 3-arg specific
  lacks → generic mismatch. Added `logical, optional, intent(in) :: omp_offload`
  to the FMS template (keeping MOM6 source pristine for analysis fidelity).

**Conclusion:** with-sema is tractable. (Decision deferred to chase the r4/r8 root
cause — resolved in the FC_AUTO_R8 entry above.)

---

## 2026-05-28 — Merged parse-tree generation into `build.sh --gen-ptree`

**Context:** removing `-no-sema` to get with-sema dumps broke generation —
`mpp_mod.mod not found` etc. The standalone `gen_parse_tree.sh` was meant to mimic
`build.sh` but had drifted badly (stale `INFRA_ROOT=submodules/FMS`; real path is
`submodules/infra/FMS2`) and broken.

**Root cause of the constraint:** the with-sema dump (`-fdebug-dump-parse-tree`)
requires every USE'd module's `.mod` file to exist, and flang emits **no dump at
all** on a semantic error. So with-sema couples fact extraction to a complete,
topologically-ordered build — but the dump self-bootstraps, emitting each `.mod`
as a side effect.

**Resolution:** deleted `gen_parse_tree.sh`; merged its intent into `build.sh` as
an additive `--gen-ptree` mode (forces the `flang_ptree` template, best-effort
`make -k`, tolerant of per-file failures). Fixed along the way: the INFRA path,
`-fc1` ordering (baked `FC = flang -fc1` into the template so `-fc1` is always
first), and the MPI `mpi.mod`/`mpif.h` include paths (plain flang, not the mpifort
wrapper). Activates flang via `source .../activate_llvm.sh`.

**This is the central cost of D4:** with-sema is coupled to a full ordered build.
The two dump modes:
- `-fdebug-dump-parse-tree-no-sema` — pure syntactic, standalone on any single
  file, no deps. Names/types/generics unresolved.
- `-fdebug-dump-parse-tree` (with sema) — adds constant folding, resolved KIND
  values, typed expressions. Requires all dependency `.mod` files.
