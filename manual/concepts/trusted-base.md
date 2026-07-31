# The trusted base and the axioms audit

A machine-checked proof moves trust; it does not remove it. Track B is
explicit about where the remaining trust sits, and audits what can be audited.

## What you must trust (and why it is small)

1. **The Lean kernel and Mathlib's three standard axioms** — the same base as
   all of Mathlib (see below).
2. **The extraction/printing pipeline** — dump parsing, the kernel IR, the
   two passes, the Lean printer. This is *the* trusted base Track B adds,
   and three properties keep it auditable:
   - **deterministic** — same dump in, same Lean out, byte for byte; pinned
     by golden tests and by `groundline kernel verify`'s byte-diff gate;
   - **small** — a few files, each readable in one sitting
     (`kir.py`, `frontend/flang_kernel.py`, `frontend/clang_kernel.py`,
     `lean_printer.py`);
   - **refusing** — anything outside the modeled subset raises
     `UnsupportedConstruct` rather than producing a plausible-but-wrong model
     ([the refusal discipline](kernel-ir.md)).

   The rule adopted wholesale from Logos Research's migration-by-proof work:
   **no LLM anywhere inside this pipeline.** Agents may write ports and
   search for proofs — the checker verifies those — but a wrong *model* makes
   every proof vacuous, so the model-producing code must be boring,
   deterministic, and human-auditable.
3. **The compilers' front ends** — flang's with-sema parse tree and clang's
   AST are taken as ground truth about what the source says. This is the same
   trust every build of the model already places in them.
4. **The modeling conventions** — reals for floating point (stated on the
   [home page](../index.md), prominently), synthesized component parameters
   modeled as real scalars, `intent(inout)` modeled functionally. These are
   part of what each theorem *means*, recorded in `kir.py`'s docstring and in
   each generated def's doc comment.

One human step remains, by design: a **one-time by-eye audit** of each newly
banked generated def against its source — feasible precisely because the
printer [mirrors the source's shapes](printer-fidelity.md). After banking,
drift is caught mechanically (`verify` byte-diffs; `lake build` re-checks).

## The axioms audit

Lean will happily let a file `sorry` its way to green, and tactics can in
principle smuggle in axioms. The defense is one command: `#print axioms`
reports, for any theorem, the complete set of axioms its proof ultimately
rests on. `lean/pilot/Pilot/AxiomsAudit.lean` runs it on **every** Track B
declaration — generated defs, point lemmas, fidelity theorems, kernel-level
theorems, and the schema lemmas — so the answer appears in every build log.

The acceptable answer, and what each axiom is:

```text
[propext, Classical.choice, Quot.sound]
```

- `propext` — propositional extensionality: logically equivalent propositions
  are equal.
- `Classical.choice` — the axiom of choice, which also powers classical
  (non-constructive) case analysis; it enters here through Mathlib's real
  numbers and their decidable order.
- `Quot.sound` — soundness of quotient types; ℝ itself is constructed as a
  quotient.

These are Lean/Mathlib's three standard axioms — the accepted foundation of
essentially all formalized mathematics in Lean. What must **never** appear is
`sorryAx` (an unfinished proof) or any custom axiom: either would mean a
theorem was assumed, not proved.

The audit from the current build (fresh output of
`lake env lean Pilot/AxiomsAudit.lean`; all 798-job `lake build` green):

```text
--8<-- "axioms_audit.txt"
```

Note the five `TrackB.foldSeq*` lines: the plain-DO schema definitions and
their structural-induction proofs use *no classical reasoning*, so they report
strict subsets of the three axioms (the two defs, none at all). The audit file
documents that a subset is expected there — anything *beyond* the three, in
particular `sorryAx`, is still a trusted-base violation.

## What sits outside the fence

The theorems say nothing about floating-point rounding (see
[what the theorems mean](../index.md#what-the-theorems-mean-and-deliberately-do-not)),
about the driver code around the kernels, or about constructs the pipeline
refused. The fence is drawn tightly on purpose; everything inside it is
machine-checked, and the [refusal catalog](../reference/refusals.md) is the
map of the fence line.
