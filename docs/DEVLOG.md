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
