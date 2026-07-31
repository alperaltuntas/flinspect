# groundline Track B — kernel equivalence by proof

!!! abstract "Why *groundline*?"

    In glaciology, the **grounding line** is where floating ice meets
    bedrock. That is exactly the boundary this tool draws through a codebase:
    what merely *floats* — `assumed` dispatch, `unresolved` calls, untested
    ports — versus what *rests on bedrock* — facts the compiler's semantic
    analysis resolved, and kernel equivalences proved in Lean. The relational
    track's own vocabulary already says it: it evaluates queries over a
    *ground graph* of grounded facts, stratified into must/may views. The
    name marks the line the tool exists to find, and to push forward.

**groundline's Track B proves that TURBO's C++/AMReX ports of MOM6 ocean-model
kernels compute the same mathematics as the legacy Fortran** — machine-checked
in Lean 4 with Mathlib, over the real numbers. Both sides of every proof are
*generated* from compiler syntax trees (flang for Fortran, clang for C++) by a
small, deterministic, auditable translator; no human transcription and no
language model sits anywhere on the trusted path.

```text
flang with-sema dump ──▶ kernel IR ──▶ Generated.lean        (Fortran side)
clang JSON AST       ──▶ kernel IR ──▶ GeneratedCpp.lean     (C++ side)
                              │
                              ▼
        machine-checked equivalence theorems in Lean 4 / Mathlib, over ℝ
```

The pipeline is driven by a declarative manifest (`kernels.toml`) and a
console script:

```console
--8<-- "quickstart_verify.txt"
```

Today the bank covers the **entire current TIM point-kernel population — five
of five kernels** ported from MOM6 to TIM (the TURBO Infrastructure for MOM,
AMReX-based), each with a checked equivalence theorem and an axioms audit:
`ppm_limit_pos`, `ppm_limit_cw84`, `edge_thickness_upwind`,
`thickness_to_dz_3d_boussinesq`, and `thickness_to_dz_3d_nonboussinesq`.

## What the theorems mean — and deliberately do not

!!! warning "Read this before citing a theorem"

    Every equivalence in this project is proved **over ℝ, the mathematical
    real numbers — not over IEEE floating point**.

    **What a theorem certifies:** *algorithmic* agreement. The Fortran loop
    body and the C++ point function are the same mathematical function on
    every input — there is no transcription error: no wrong sign, no swapped
    edge value, no off-by-one index, no dropped guard branch. That class of
    error is the dominant risk of a human- or LLM-driven port, and it is
    eliminated for every banked kernel.

    **What a theorem does not certify:** bit-for-bit floating-point identity.
    Numerical drift from operation reordering, fused multiply-add, or
    reduction order is real and remains the province of the existing
    regression and ensemble-consistency testing machinery. This division of
    labor is deliberate — the *reals-first* philosophy of Altuntas et al.
    (VSS 2025, EPTCS 432) applied to porting: where bitwise reproducibility
    is unattainable anyway, **prove the mathematics and test the numerics**.

    Two further honest boundaries: the proofs cover the per-point kernel
    bodies and their iteration schemas, not the surrounding driver code; and
    the translator refuses (rather than approximates) any construct outside
    its supported subset — see [the refusal catalog](reference/refusals.md).

## Lineage

Track B follows Logos Research's **"migration by proof"** template: an agent
may write the port and search for proofs, but a *deterministic* translator
renders both versions into Lean with floats modeled as ℝ, and a machine-checked
proof establishes they compute the same function on every input. The
load-bearing ideas adopted wholesale: **no LLM inside the proof pipeline**,
generated Lean readable enough to audit line-by-line against the source, and
equivalence over ℝ as the honest claim. groundline is this pattern instantiated
for Fortran → C++/AMReX, with compiler syntax trees as the substrate; the
reals-first division of labor with numerical testing comes from Altuntas et
al. (VSS 2025, EPTCS 432).

## Where to go

- **[Installation](installation.md)** — what each dependency tier unlocks,
  from `pip install` alone up to proving theorems.
- **[Quickstart](quickstart.md)** — a self-contained toy kernel pair, end to
  end, in five minutes.
- **[Concepts](concepts/two-irs.md)** — the architecture, written for a
  scientific-software reader who has not seen Lean.
- **[Case studies](case-studies/ppm-limit-pos.md)** — the five production
  kernels, retold as narratives: what each one taught, including the bug the
  machine-checking found.
- **[Reference](reference/manifest.md)** — the manifest schema, the CLI, the
  API, and the complete refusal catalog.
- **[Limits & roadmap](limits.md)** — what is out of scope today, honestly
  labeled.

!!! note "The engineering record"

    This manual documents what runs today. The engineering record — vision,
    design decisions, and the append-only development log the case studies
    are drawn from — lives in the repository:
    [`docs/VISION.md`](https://github.com/alperaltuntas/groundline/blob/main/docs/VISION.md),
    [`docs/DESIGN.md`](https://github.com/alperaltuntas/groundline/blob/main/docs/DESIGN.md),
    [`docs/DEVLOG.md`](https://github.com/alperaltuntas/groundline/blob/main/docs/DEVLOG.md).
    groundline also has a second, top-down face — a relational model of program
    structure — introduced briefly in [The relational track](relational.md).
