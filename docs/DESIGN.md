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

**Ontology — everything is a set or a relation.** The IR is a small collection of
**named, typed relations over interned atoms**, in the spirit of Alloy. Atoms are
scope-qualified entity identities (never bare names). Entity *kinds* are unary
relations (sets) of atoms; structural facts are binary/n-ary relations between them.
Querying is then one closed algebra (join `.`, `&`, `+`, `-`, closure `*`, inverse
`~`) over that schema — every operation takes relations and returns a relation, so
results compose. We borrow Alloy's **ontology and algebra**, *not* its solver: we
evaluate queries over one given instance, we do not enumerate models over a bounded
scope (see Q4). This keeps the IR's interface as narrow-and-deep as it gets — "a set
of relations plus a fixed operator set" — and is engine-neutral: a relation is a
predicate in Datalog and an edge set in NetworkX, so the Q4 backend choice never
touches the model.

Entity sets (unary relations of interned, scope-qualified atoms):
- `Module`, `Program`, `Subprogram`
- `Subroutine`, `Function` (with signature: ordered args of name/type/rank/kind/optional)
- `Interface` (generic name → set of specific procedures)
- `DerivedType` (parent type, type-bound bindings)

Relations:
- `calls(caller, callee)`
- `uses(scope, module)` — with only-list / rename info
- `defined_in(entity, scope)` / `contains(scope, entity)`
- `exports(module, entity)` (requires public/private — W4)
- inverse/derived (`called_by`, `imports`) computed, not stored

**Confidence is modeled by stratified relations, not by a tuple attribute (D3).**
Rather than attach a `resolved|assumed|unresolved` tag to each tuple (which makes
every relation n+1-ary and clutters every join), each confidence-bearing relation is
split into strata — e.g. `calls_resolved` / `calls_assumed` / `calls_unresolved` —
each a *pure* relation. This keeps "everything is a relation" literally true and,
more importantly, hands us the standard sound-analysis lattice for free:
- **must** = `calls_resolved` — the under-approximation; a violation here is a
  *definite* finding.
- **may** = `calls_resolved + calls_assumed + calls_unresolved` — the
  over-approximation; a violation only here is *possible*, and is exactly what the
  optional SMT layer reasons over (∃/∀ across the unknowns; VISION §3, Q4).

`unresolved` targets are kept as first-class atoms, **not** silently dropped. The one
genuinely awkward case for a flat-relational model is the ordered, typed **signature**
(a sequence of records); model it with explicit positional relations
(`arg_at(sub, i, param)`, `param_type(param, type)`, …) at the IR boundary, while
letting the frontend keep signatures record-shaped internally (principle #10 — be
pragmatic below the seam).

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
2. **Everything is a set or a relation.** Model facts as named, typed relations over
   interned atoms — entity kinds are sets, structure is relations, one closed algebra
   queries them (§2.1). This is Alloy's *ontology*, not its solver: we evaluate over
   one given instance, not enumerate models over a bounded scope (Q4). Encode
   confidence as stratified must/may relations, not tuple attributes. Payoff: a tiny,
   engine-neutral interface, and the sound over-/under-approximation lattice for free.
   (D3, Q4)
3. **Deep modules, narrow interfaces.** The frontend is one method —
   `extract(sources) -> IR` — hiding all of flang's text format, depth-counting,
   regex, and resolution. The interface stays far smaller than the body; we avoid a
   crowd of shallow helpers.
4. **Pull complexity down to the frontend.** Consumers (forest, Explorer, future
   query layer) never learn that flang exists. Litmus test for every IR field:
   *could a non-flang adapter populate this without contortion?* If not, it leaks.
5. **One layer, one vocabulary.** flang parse-tree terms live below the seam; the
   domain (modules, calls, types) lives at it; graph/relation terms live above. A
   flang node-string above the seam — or a NetworkX detail below it — is a bug.
6. **Partial knowledge is a value, not an error.** Incomplete resolution is the
   normal case, so it is a first-class fact: confidence
   (`resolved | assumed | unresolved`) is part of the model — stratified per #2, never
   silently dropped or invented. (D3, W2)
7. **Identity is scope-qualified, never a bare name.** No name-only lookups or
   `endswith` matching, in the model or the Explorer. (W4, W5)
8. **Domain-shaped, not codebase-shaped.** The IR models Fortran-the-language, not
   MOM6-the-codebase — no `DoublePrecision -> 'r8_kind'` MOM-isms baked in; such
   mappings, if needed, live in a consumer. General enough for any Fortran program,
   not for speculative non-Fortran inputs. (W6)
9. **Isolate faults.** One unparseable file reports and is skipped; it must not
   abort the forest.
10. **Invest at the seam, ship everywhere else.** The IR boundary is the one line
   worth perfecting because everything compounds on it; elsewhere (rendering, CLI),
   be pragmatic.
11. **Keep `VISION.md` and `README.md` honest.** Mark roadmap as roadmap.

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
