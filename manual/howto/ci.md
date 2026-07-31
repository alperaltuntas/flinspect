# Wire verification into CI

`groundline kernel verify` is designed as a CI gate: it exits non-zero on any
drift or failure, and it prints exactly what it checked and what it skipped.

## What the gate checks

```console
$ groundline kernel verify
```

1. **Regenerate + byte-diff, per side.** Extract every banked kernel fresh
   from its sources and byte-compare the rendered modules against the
   committed `Generated.lean` / `GeneratedCpp.lean`. Any drift → non-zero
   exit, a unified-diff excerpt, and the fresh copy parked in a temp file.
   This catches: a stale committed file, upstream source changes, dump-format
   drift, and any accidental change to the pipeline's output.
2. **`lake build`** (when the manifest sets `[lean] lake_dir` and `lake` is
   on `PATH`): every theorem re-checked, the axioms audit re-printed in the
   log. Skipped with an explicit note when `lake` is absent; skipped when the
   byte-diff already failed (fix drift first — proofs about stale defs prove
   nothing).

Degradation is honest by design: a missing `clang++` is an **error** on
`verify` (a gate must not pass vacuously) unless you explicitly scope the run
with `--skip-cpp`.

## The tiers in CI terms

| CI environment has | Run | Gate covers |
|---|---|---|
| Python only | `groundline kernel verify --skip-cpp` (quickstart manifest) | Fortran extraction + printing against the committed dump |
| + the *pinned* clang++ | `groundline kernel verify` (quickstart manifest) | both sides of extraction + printing |
| + corpus & TIM headers | `verify --kernels examples/turbo-stack.kernels.toml` | the real kernel bank |
| + Lean toolchain | same | every equivalence theorem + axioms audit |

The quickstart manifest is the portable smoke tier — its Fortran dump is
committed, its C++ header is standalone — so *any* CI runner can execute the
first row. One subtlety for the second: the committed `GeneratedCpp.lean`
header stamps the clang version that produced it (toolchain is provenance),
and `verify` byte-diffs the **whole file** — so the full C++ byte-diff passes
only under the pinned clang. On runners with a different clang, cover the C++
side with the pytest suite instead: its quickstart golden test compares the
*defs* only, by design. The production rows honestly require site resources
(the MOM6 with-sema corpus and the TIM/AMReX headers live on NCAR storage),
which in practice means a self-hosted or site-local runner for the full gate.

## Example: GitHub Actions job (portable tier)

```yaml
kernel-verify:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.12"
    - run: pip install -e '.[dev]'
    - name: Verify the quickstart kernel bank (Fortran side, byte-exact)
      run: groundline kernel verify --skip-cpp
      working-directory: examples/quickstart
    - name: Test suite (C++ tier auto-gates on clang availability)
      run: |
        sudo apt-get update && sudo apt-get install -y clang
        pytest
```

The corpus- and clang-gated tests *skip* rather than fail when their tier is
absent, so the `pytest` step is safe on any runner and strengthens itself as
tools become available.

## The gate this is designed to become

The intended end state, from the project's vision: CI accepts a change only if
**every ported kernel carries a checked equivalence theorem** — `verify`'s
Lean tier — *and* (once the relational track's CLI lands) no forbidden
structural edge is introduced. Kernel `verify` is the first half, running
today; the conjunction is [roadmap](../limits.md).
