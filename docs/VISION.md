# flinspect — Vision

> **Status:** living document, rewritten in place as decisions change. This is the
> *why*: where flinspect is going and the strategic decisions behind it.
>
> Companion documents in this directory:
> - **`DESIGN.md`** — the *how*: target architecture, the IR seam, the weakness→fix
>   mapping, and the phased roadmap.
> - **`DEVLOG.md`** — the *what happened*: append-only, dated record of roadblocks
>   and resolutions. When a devlog entry produces a durable conclusion, that
>   conclusion graduates here (or into DESIGN) as a clean statement; the devlog
>   keeps the narrative of how we got there.
>
> Keep this honest — it is most useful when it describes reality, not aspiration
> dressed as reality.

---

## 1. Purpose

flinspect has two faces today:

- **What it is:** a prototype that scrapes flang's textual parse-tree dump to build
  a structural/call graph of Fortran code, viewable in Jupyter.
- **What it wants to be (per `README.md`):** a *relational reasoning system* over
  Fortran programs — Alloy-like queries plus Z3-backed checks — used to make GPU
  modernization of MOM6 (and similar HPC codes) provably safe and CI-enforceable.

This document reconciles those two faces: it states the destination and records the
strategic decisions we've made about how to reach it. The architecture and the
step-by-step path live in `DESIGN.md`.

It is meant to be read by **both the maintainers and any assistant/agent** picking
up work, so it errs toward making implicit reasoning explicit.

---

## 2. What flinspect is today (honest baseline)

Pipeline:

```
flang -fdebug-dump-parse-tree[-no-sema]  →  text dump
   →  ParseTree (line-by-line regex + `|`-depth scraping)   [flinspect/parse_tree.py, ~1560 lines]
   →  NodeRegistry of interned nodes                        [node_registry.py, parse_node.py]
   →  ParseForest builds NetworkX module/call graphs        [parse_forest.py]
   →  Explorer renders subgraphs in Jupyter (ipycytoscape)  [explorer.py]
```

Key facts about the current implementation:

- The "parser" is a flat dispatch of `if "<substring>" in line` checks plus a
  `level()` function that counts leading `|` characters to infer tree depth.
- It also contains a hand-rolled, partial **type/rank/kind inference engine** and
  **generic-interface / type-bound-procedure resolver** (`_infer_*`,
  `_types_compatible`, `resolve_interface_procedures`, `_resolve_binding_name`).
- The fixture generator (`tests/f90/gen_ptree_files.sh`) uses
  `-fdebug-dump-parse-tree-no-sema`, **but the production build makefile
  (`build-utils/makefile-templates/ncar-flang_ptree.mk`) uses the *with-sema*
  dump** (`-fdebug-dump-parse-tree`). Tests and production are currently parsing
  *different* dump variants. (See Decision D4.)

---

## 3. The vision (destination)

Turn flinspect from a structural explorer into a **relational reasoning substrate
over sound, compiler-derived facts** about Fortran programs.

- **Universe:** Modules, Subroutines, Functions, Interfaces, Derived Types, plus
  the relations `calls`, `called_by`, `uses`, `defined_in`, `contains`, `exports`,
  `imports`.
- **Query layer:** a declarative relational algebra (join `.`, intersection `&`,
  union `+`, difference `-`, transitive closure `*`, inverse `~`) with
  quantification — the Alloy-flavored sketch in `README.md`.
- **Reasoning layer:** Z3-backed checking of architectural invariants, returning
  **counterexamples** (e.g., exact call chains that violate host/device
  separation).
- **Headline use case:** incremental, *provably monotonic* GPU porting of MOM6 —
  computing the porting frontier, classifying blockers, and enforcing "no new
  HostOnly edge crosses into GPU_Port" as a CI gate.

The vision is genuinely valuable and differentiated. **The thing that currently
blocks it is the quality and stability of the underlying facts** — see the
weaknesses table in `DESIGN.md`.

---

## 4. Strategic decisions (the conclusions we've reached)

These are the load-bearing decisions. Each has a rationale so future-us can tell
whether changing circumstances should change the decision.

### D1 — Commit to the flang ecosystem (pursue "Option A" now)

Build on flang's **semantic (with-sema) parse-tree dump** as the near-term fact
source.

**Why:**
- flang is backed by NVIDIA/AMD/Arm under LLVM — the vendors whose hardware our
  GPU-porting use case targets. Best bet for longevity and continued support.
- It already compiles MOM6/FMS, so it is guaranteed to ingest our real code.
- Our build pipeline **already emits the dump** — the integration (preprocessing,
  `-D` macros, include paths) exists.

### D2 — Treat the flang dump's *format* as untrusted; isolate it behind an IR

flang's adoption guarantees the *compiler* persists and keeps parsing our code. It
does **not** guarantee the `-fdebug-dump-*` *text format* is stable — these are
debugging aids with no stability contract. Therefore:

> **All flang-specific parsing lives behind a seam. Everything downstream depends
> on a flinspect-owned intermediate representation (IR), never on flang's format.**

This is what makes a later backend swap (e.g., LFortran, or flang's real
programmatic API) a *localized* change instead of a rewrite. See the architecture
in `DESIGN.md`.

### D3 — Resolution confidence is a first-class fact

Every relation (especially call edges) carries a confidence:
`resolved | assumed | unresolved`.

**Why:** the current facts are simultaneously over-approximate (unknown types →
"compatible"; unmatched generic → "fan out to all procedures") and under-approximate
(unresolved calls silently dropped). A *verification* layer cannot sit on facts
that silently mix guesses with truths. Making confidence explicit:
- lets the Z3 layer distinguish "provably" from "possibly,"
- survives the backend swap unchanged, and
- means migrating to a more precise frontend (LFortran) **automatically upgrades
  reasoning quality** without touching the query layer.

### D4 — Unify on the with-sema dump

Switch test fixtures (and any docs) to `-fdebug-dump-parse-tree` (with sema) so
tests and production parse the same thing, and so we consume *resolved* names/types
instead of re-deriving them. Investigate `-fdebug-dump-symbols` as an additional
(or primary) input — it carries the resolved symbol table directly.

**Status — VALIDATED (2026-05-28).** With-sema parse-tree generation now covers the
entire MOM6/FMS2 stack with zero genuine errors (FMS2 104/104, MOM6-infra 14/14,
MOM6 340/340), via `build.sh --gen-ptree`. The feasibility worry behind D3's
fallback is resolved: with-sema can be the **sole** production input; a no-sema
path is now only an optional resilience measure, not a coverage requirement. The
total enabling cost was four small, foundational fixes — see `DEVLOG.md` for the
full account.

### D5 — A frontend upgrade (LFortran/fparser2, or flang's structured API) is a much-later option, not a near-term track

LFortran's ASR (or fparser2/PSyclone) — or flang's own more structured outputs —
would replace text-scraping with a real semantic API, the durable fix for
format fragility. **But it is explicitly deferred.** Two things changed the
calculus: D4 proved with-sema already gives full-coverage facts (so there is
nothing to *rescue*), and the Phase 1 seam (D2) makes any backend swap a localized
change (so we need not pre-decide it). Its value also remains conditional on the
frontend actually ingesting MOM6/FMS, which is unproven.

So this is a **much-later, optional exploration**, not a parallel spike. Revisit
only if dump-format churn actually bites (Q1 in `DESIGN.md`) or we want a precision
upgrade the dump can't provide — and prefer the in-ecosystem hedge
(`-fdebug-dump-symbols`, Q2) before any non-flang frontend, consistent with D1.
