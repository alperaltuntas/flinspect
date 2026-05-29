# flinspect — Design

> **Status:** living document, rewritten in place as the architecture firms up.
> This is the *how*: target architecture, the IR seam, the weakness→fix mapping,
> the principles that constrain the design, and the phased roadmap.
>
> For the *why* (goals and strategic decisions D1–D5) see `VISION.md`. For the
> dated narrative of roadblocks and resolutions see `DEVLOG.md`. Decision IDs
> (D1–D5) referenced here are defined in `VISION.md`.

---

## 1. Weaknesses being addressed (prioritized)

From the review of the current codebase. Ordered by impact on the vision.

| # | Weakness | Where | Fix lands in |
|---|----------|-------|--------------|
| W1 | Re-implements semantics flang already computed, from a *no-sema* dump | whole `parse_tree.py` | D4 + Phase 1 |
| W2 | Facts are heuristically over- *and* under-approximate; unsound for a verification layer | `_types_compatible`, `resolve_interface_procedures` (all-procs fallback), `unfound_*` drops | D3 + Phase 2 |
| W3 | Brittle text scraping: exact flang node strings, `|`-counting, `assert ...not recognized`, no per-file isolation | `parse_tree.py`, `utils.level()` | D2 (seam) + Phase 1 |
| W4 | Name-based matching ignores scope/visibility/overloading | `find_named_entity`, `get_subroutine_by_name` (`endswith`), no public/private | Phase 2 |
| W5 | Explorer keys cytoscape nodes by **bare name** → distinct same-named routines silently merge | `explorer.py` (`'id': node.name`) | Phase 3 |
| W6 | Hardcoded intrinsic list; `DoublePrecision→'r8_kind'` MOM-ism; named-kinds-only | `utils.py`, `_extract_kind_from_line` | resolved by sema/IR |
| W7 | Three full re-parse passes per file | `parse_structure/interfaces/calls` | Phase 1 (revisit) |
| W8 | No CLI; notebook-only despite "CI-enforceable" claim | — | Phase 4 |
| W9 | README oversells; ~90% aspiration | `README.md` | Phase 0 |
| W10 | Python 3.14 hard pin | `pyproject.toml` | low priority |

---

## 2. Target architecture

```
┌──────────────────────┐   ┌────────────────────────┐   ┌───────────────────────────┐
│ Frontends (swappable) │   │  flinspect IR          │   │ Consumers (flang-agnostic) │
│                       │   │  (the contract)        │   │                            │
│ A. flang sema dump    │──▶│  Entities + Relations  │──▶│  Graph build (ParseForest) │
│ B. LFortran ASR  (TBD)│   │  + confidence (D3)     │   │  Explorer (Jupyter)        │
│ C. flang FIR/API (TBD)│   │  flinspect-owned       │   │  Relational query layer    │
└──────────────────────┘   └────────────────────────┘   └───────────────────────────┘
        leaks here              the seam — nothing            never imports flang
        stay here               flang-specific lives here    query evals the ground
                                                              graph; SMT only over
                                                              D3 unknowns
```

**The one rule that gives the plan its value:** nothing on the consumer side
imports anything flang-specific. The IR is defined by our *domain* (the vision's
universe), not by flang's parse-tree node shapes.

**Litmus test for every IR field:** *"Could an LFortran adapter populate this
without contortion?"* If no, the field is leaking flang and must be reshaped.

### 2.1 IR contract (sketch — to be refined in Phase 1)

Entities (interned, scope-qualified identity — never bare names):
- `Module`, `Program`, `Subprogram`
- `Subroutine`, `Function` (with signature: ordered args of name/type/rank/kind/optional)
- `Interface` (generic name → set of specific procedures)
- `DerivedType` (parent type, type-bound bindings)

Relations (each edge tagged with confidence per D3):
- `calls(caller, callee)`
- `uses(scope, module)` — with only-list / rename info
- `defined_in(entity, scope)` / `contains(scope, entity)`
- `exports(module, entity)` (requires public/private — W4)
- inverse/derived (`called_by`, `imports`) computed, not stored

Confidence enum: `resolved` (frontend proved it) | `assumed` (heuristic
over-approximation, e.g. generic fan-out) | `unresolved` (target not found — kept
as a first-class fact, **not** silently dropped).

### 2.2 Frontend interface (sketch)

```python
class Frontend(Protocol):
    def extract(self, sources: Iterable[Path]) -> IR: ...
```

- `frontend/flang_dump.py` — Option A; absorbs all current `parse_*`, `_infer_*`,
  `level()`, regex.
- `frontend/lfortran_asr.py` — stub with the real signature raising
  `NotImplementedError`. Its existence is a *forcing function*: it keeps the IR
  honest. The day we fill it in is the day we learn whether the seam was real.

---

## 3. Design principles

These principles are ordered roughly from most to least
load-bearing.

1. **Get the IR right first.** Design its state and invariants before any behavior;
   the frontend and consumers exist only to establish or rely on them. A reasoning
   layer built on the wrong abstraction can't be rescued by good code. (D2)
2. **Deep modules, narrow interfaces.** The frontend is one method —
   `extract(sources) -> IR` — hiding all of flang's text format, depth-counting,
   regex, and resolution. The interface stays far smaller than the body; we avoid a
   crowd of shallow helpers.
3. **Pull complexity down to the frontend.** Consumers (forest, Explorer, future
   query layer) never learn that flang exists. Litmus test for every IR field:
   *could a non-flang adapter populate this without contortion?* If not, it leaks.
4. **One layer, one vocabulary.** flang parse-tree terms live below the seam; the
   domain (modules, calls, types) lives at it; graph/relation terms live above. A
   flang node-string above the seam — or a NetworkX detail below it — is a bug.
5. **Partial knowledge is a value, not an error.** Incomplete resolution is the
   normal case, so it is a first-class fact: every relation carries
   `resolved | assumed | unresolved`. We never silently drop or invent. (D3, W2)
6. **Identity is scope-qualified, never a bare name.** No name-only lookups or
   `endswith` matching, in the model or the Explorer. (W4, W5)
7. **Domain-shaped, not codebase-shaped.** The IR models Fortran-the-language, not
   MOM6-the-codebase — no `DoublePrecision -> 'r8_kind'` MOM-isms baked in; such
   mappings, if needed, live in a consumer. General enough for any Fortran program,
   not for speculative non-Fortran inputs. (W6)
8. **Isolate faults.** One unparseable file reports and is skipped; it must not
   abort the forest.
9. **Invest at the seam, ship everywhere else.** The IR boundary is the one line
   worth perfecting because everything compounds on it; elsewhere (rendering, CLI),
   be pragmatic.
10. **Keep `VISION.md` and `README.md` honest.** Mark roadmap as roadmap.

---

## 4. Migration plan (phased)

Each phase is independently shippable and leaves the tool working.

**Phase 0 — Reset expectations.** Trim `README.md` to what exists; move the
relational/Z3/GPU material under an explicit "Roadmap / Vision" heading. Land the
docs. *(docs only)* — **DONE 2026-05-28.**

**Phase 1 — Carve the seam (the core refactor).**
- Define the IR (§2.1) as flinspect-owned types.
- Create `frontend/` package + `Frontend` protocol; move all flang-text logic into
  `frontend/flang_dump.py`.
- Make `ParseForest`/`Explorer` consume the IR only.
- Add the `lfortran_asr.py` stub.
- Switch fixtures to the with-sema dump (D4); make tests assert on the IR, not on
  flang strings.
- Add per-file fault isolation (W3).

**Phase 2 — Soundness & resolution quality.**
- Consume *resolved* names/types from sema (and/or `-fdebug-dump-symbols`), retiring
  the hand-rolled inference where the compiler already answers (W1, W6).
- Add the confidence field end-to-end; convert `unfound_*` into first-class
  `unresolved` edges (W2).
- Scope/visibility-correct resolution; kill `endswith` matching (W4).

**Phase 3 — Explorer correctness.** Scope-qualified node identity (W5); show
confidence (e.g., assumed edges dashed).

**Phase 4 — Make it CI-usable.** A CLI that runs a query/invariant over a forest
and exits non-zero on violation — the minimum for the README's "CI-enforceable"
claim (W8).

**Phase 5+ — The vision proper.** The relational query layer over the IR is the
core (ground-graph evaluation: closure, difference, reachability), then the
GPU-porting frontier tooling on top of it. An SMT (Z3) layer is an *optional*
add-on scoped to reasoning over D3 unknowns (∃/∀ over `assumed`/`unresolved`
edges), not the main checker — see Q4. (Out of scope for detailed planning until
Phases 1–2 land; the IR + confidence model is the prerequisite.)

**Deferred — Frontend upgrade exploration (much later, optional).** Evaluate an
alternative frontend — LFortran ASR / fparser2 ("Option B"), or flang's own more
structured outputs / programmatic API ("Option C") — and swap it in behind the
Phase 1 seam if it improves resolution precision or removes dump-format fragility.
This is explicitly *not* near-term: with-sema already provides full-coverage facts
(D4), and the seam makes the swap localized whenever we choose to do it. Revisit
only if dump-format churn actually bites (see Q3) or we want a precision upgrade
the dump can't give. Resolves D5.

---

## 5. Open questions / to validate

- **Q1 (live):** How stable has flang's dump format been across recent LLVM
  releases? This is now the *most* relevant resilience question — it sizes how much
  fixture/format-version defense we need within Option A, and is the trigger that
  would reopen the deferred frontend-upgrade exploration.
- **Q2:** Does the with-sema dump fully resolve generics and type-bound bindings in
  the textual output, or do we need `-fdebug-dump-symbols` for that? Determines how
  much of `_infer_*`/`resolve_*` can be deleted vs. retained in Phase 2. (The
  in-ecosystem hedge against Q1, ahead of any non-flang frontend.)
- **Q3 (deferred, gates D5):** Does LFortran's ASR — or fparser2 — actually ingest
  FMS+MOM6 at current maturity? Only relevant if/when we pursue the deferred
  frontend-upgrade exploration; not near-term.
- **Q4:** The reasoning split. The facts are *one fixed ground graph*, so invariant
  checking is query *evaluation* (reachability, closure, set difference), not Alloy's
  search over a space of small models — a recursive relational engine (home-grown, or
  a Datalog/Soufflé backend) is the natural core and scales to a whole codebase. An
  SMT solver (Z3) is *not* the workhorse here and encodes the ground graph poorly;
  it earns its place only over the D3 *unknowns* — "does some / every resolution of
  the `assumed`/`unresolved` edges violate the invariant?" Open: is that residual
  SMT layer worth building, and where exactly is the Datalog↔SMT handoff? Affects
  Phase 5 design. **Sequencing:** start the query layer in-process with NetworkX +
  Python set ops (the README's relational operators map onto it almost one-to-one,
  and the facts are a single fixed graph); adopt a real Datalog engine — CozoDB
  (embedded, Python bindings) first, Soufflé (standalone, compiles to C++) only if
  scale demands — as a *localized* upgrade once invariant rules outgrow hand-written
  traversals. If the query layer consumes the IR through a thin interface, that swap
  is contained, exactly like the frontend swap (D2). So none of this needs deciding
  before Phase 1.

---

## 6. Glossary

- **Option A** — frontend built on flang's textual parse-tree dump (current
  direction).
- **Option B** — frontend built on a semantic-IR library (LFortran ASR / fparser2).
- **IR** — flinspect's own intermediate representation; the seam between frontends
  and consumers.
- **sema / no-sema** — flang dumps *with* / *without* semantic analysis (name &
  type resolution, generic binding).
- **confidence** — `resolved | assumed | unresolved` tag on a relation (D3).
- **frontier** (vision) — `calls*(GPU_Port) − GPU_Port`; the minimal interface to
  port next.
