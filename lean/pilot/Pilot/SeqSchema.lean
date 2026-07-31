import Mathlib.Logic.Function.Basic
import Mathlib.Data.List.Basic

set_option linter.style.header false

/-!
# The plain-DO schema lemma (Track B, extraction rule A)

A plain Fortran `do` nest asserts nothing about iteration independence, so —
unlike `do concurrent`, whose *source assertion* is what licenses the pointwise
model — its honest semantics is a **sequential fold** of per-point updates over
an enumeration of the index box. The license to model a pointized plain-DO
kernel with a pointwise map anyway is the once-and-for-all schema lemma proved
here: for any point function `f` and any duplicate-free, complete enumeration
of the box,

    foldSeq f s₀ enum = pointwiseMap f s₀ .

The extraction gate (`kir.pointize`, rule A) is what guarantees this lemma's
setting applies — every array reference in the loop body is indexed exactly by
the loop indices and every write lands in the iteration's own cell — so once
pointize has produced `f`, point-locality is baked into `f`'s **type**
(`f : ι → σ → σ` sees only its own cell's state; it cannot reference a
neighbor), and the lemma's hypothesis is structural rather than re-checked per
kernel. The gate is not the semantic justification; this lemma is.

Proof shape: induction over the enumeration with a frame argument — under
`Nodup`, iteration `i` finds cell `i`'s state pristine (`foldSeq_frame`),
reads at the own index are order-insensitive, writes land in disjoint cells,
and the fold telescopes to the map.

Reductions and cross-iteration recurrences do **not** fit this setting (a
scalar accumulator writes the same cell every iteration; a recurrence reads a
cell another iteration writes) — the gate refuses them, and their
sequential-vs-unordered question is real mathematics reserved for a future
step.
-/

namespace TrackB

variable {ι σ : Type*} [DecidableEq ι]

/-- One sequential iteration of the nest at cell `i`: the state array is
updated at `i` with `f i (s i)` — the point function sees the cell's own
current value and nothing else (point-locality is structural). -/
def seqStep (f : ι → σ → σ) (s : ι → σ) (i : ι) : ι → σ :=
  Function.update s i (f i (s i))

/-- The honest semantics of a plain, perfectly nested DO whose body is a point
function: fold `seqStep` sequentially over an enumeration of the index box.
The concrete nest supplies the lexicographic enumeration; the lemma below
holds for every duplicate-free one. -/
def foldSeq (f : ι → σ → σ) (s₀ : ι → σ) (enum : List ι) : ι → σ :=
  enum.foldl (seqStep f) s₀

/-- The pointwise map — what the `pointwise`-style kernel models (and AMReX's
`ParallelFor`) compute. -/
def pointwiseMap (f : ι → σ → σ) (s₀ : ι → σ) : ι → σ :=
  fun i => f i (s₀ i)

/-- **Frame:** a cell not in the enumeration is never written. -/
theorem foldSeq_frame (f : ι → σ → σ) (enum : List ι) :
    ∀ (s₀ : ι → σ) (i : ι), i ∉ enum → foldSeq f s₀ enum i = s₀ i := by
  induction enum with
  | nil => intro s₀ i _; rfl
  | cons a tl ih =>
    intro s₀ i hi
    rw [List.mem_cons, not_or] at hi
    have h1 : foldSeq f s₀ (a :: tl) = foldSeq f (seqStep f s₀ a) tl := by
      simp only [foldSeq, List.foldl_cons]
    rw [h1, ih (seqStep f s₀ a) i hi.2]
    exact Function.update_of_ne hi.1 _ _

/-- Per-cell form of the schema lemma: under `Nodup`, the fold's value at a
cell in the enumeration is one application of the point function to the
cell's pristine state. -/
theorem foldSeq_apply_of_mem (f : ι → σ → σ) (enum : List ι) :
    enum.Nodup → ∀ (i : ι), i ∈ enum → ∀ (s₀ : ι → σ),
      foldSeq f s₀ enum i = f i (s₀ i) := by
  induction enum with
  | nil => intro _ i hi; cases hi
  | cons a tl ih =>
    intro hnd i hi s₀
    rw [List.nodup_cons] at hnd
    have h1 : foldSeq f s₀ (a :: tl) = foldSeq f (seqStep f s₀ a) tl := by
      simp only [foldSeq, List.foldl_cons]
    rcases List.mem_cons.mp hi with h | h
    · -- i is the head: no later iteration touches cell i (frame), and the
      -- head iteration finds its state pristine.
      subst h
      rw [h1, foldSeq_frame f tl (seqStep f s₀ i) i hnd.1]
      exact Function.update_self _ _ _
    · -- i is in the tail: the head iteration wrote a ≠ i, so cell i's state
      -- is still pristine when its own iteration runs.
      have hne : i ≠ a := fun he => hnd.1 (he ▸ h)
      rw [h1, ih hnd.2 i h (seqStep f s₀ a)]
      rw [show seqStep f s₀ a i = s₀ i from Function.update_of_ne hne _ _]

/-- **The schema lemma:** the sequential fold of a point function over any
duplicate-free, complete enumeration of the index box equals the pointwise
map. This — not the extraction gate — is what licenses modeling a plain-DO
nest with `pointwise`; plain DO gets a *proof* where `do concurrent` supplies
an *assertion*. -/
theorem foldSeq_eq_pointwiseMap (f : ι → σ → σ) (enum : List ι)
    (hnd : enum.Nodup) (hall : ∀ i, i ∈ enum) (s₀ : ι → σ) :
    foldSeq f s₀ enum = pointwiseMap f s₀ :=
  funext fun i => foldSeq_apply_of_mem f enum hnd i (hall i) s₀

end TrackB
