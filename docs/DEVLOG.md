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
