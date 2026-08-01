# groundline — the groundline kernel-verification Lean project

This `lake` project (Lean 4 + Mathlib) holds every kernel-verification proof: the
generated kernel models (`Groundline/GeneratedFtn.lean`, `Groundline/GeneratedCpp.lean`
— written by `groundline kernel generate`, never edited by hand), the
equivalence theorems, the iteration schemas, and the axioms audit
(`Groundline/AxiomsAudit.lean`).

To build:

```bash
lake exe cache get   # fetch the Mathlib binary cache first — hours saved
lake build
```

`groundline kernel verify` runs `lake build` here as its final tier when the
kernel manifest sets `[lean] lake_dir`. The layout and conventions are
documented in the manual: <https://alperaltuntas.github.io/groundline/reference/lean-project/>.
