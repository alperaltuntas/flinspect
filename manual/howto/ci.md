# Wire verification into CI

`groundline kernel verify` is designed as a CI gate: it exits non-zero on any
drift or failure, and it prints exactly what it checked and what it skipped.

## What the gate checks

```console
$ groundline kernel verify
```

1. **The model check, per side.** Every kernel is extracted fresh from its
   sources and the rendered modules are compared byte for byte against the
   `generated` files on disk. Any difference → non-zero exit, a
   unified-diff excerpt, and the fresh copy parked in a temp file. This
   catches: a stale generated file, upstream source changes, dump-format
   drift, and any accidental change to the pipeline's output.
2. **The proof check** (when the manifest names a `[lean]` project and
   `lake` is on `PATH`): `lake build` re-checks every theorem in that
   project, and the axioms audit reappears in the log. `verify` prints an
   explicit note when the manifest has no `[lean]` section or `lake` is
   absent; it skips the proof check when the model check already failed
   (proofs about stale models prove nothing).

When a tool is missing, the gate says so rather than passing quietly: a missing `clang++` is an **error** on
`verify` (a gate must not pass vacuously) unless you explicitly scope the run
with `--skip-cpp`.

## The installation levels, in CI terms

| CI environment has | Run | Gate covers |
|---|---|---|
| Python only | `groundline kernel verify --skip-cpp` (quickstart manifest) | Fortran extraction + printing against the committed dump |
| + the *pinned* clang++ | `groundline kernel verify` (quickstart manifest) | both sides of extraction + printing |
| + the dump directory & kernel sources | `verify --kernels examples/turbo-stack.kernels.toml` | the real kernel bank |
| + Lean toolchain | same | every equivalence theorem + axioms audit |

The quickstart manifest is the portable smoke test — its Fortran dump is
committed, its C++ source is standalone — so *any* CI runner can execute the
first row. One subtlety for the second: the committed `GeneratedCpp.lean`
header stamps the clang version that produced it (toolchain is provenance),
and `verify` byte-diffs the **whole file** — so the full C++ byte-diff passes
only under the pinned clang. On runners with a different clang, cover the C++
side with the pytest suite instead: its quickstart golden test compares the
*defs* only, by design. The production rows require site resources
(the case-study dumps and kernel headers live on NCAR storage),
which in practice means a self-hosted or site-local runner for the full gate.

## Example: GitHub Actions job (the portable level)

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
    - name: Test suite (C++ half auto-gates on clang availability)
      run: |
        sudo apt-get update && sudo apt-get install -y clang
        pytest
```

The dump- and clang-gated tests *skip* rather than fail when their toolchain is
absent, so the `pytest` step is safe on any runner and strengthens itself as
tools become available.

## The gate this is designed to become

The intended end state, from the project's vision: CI accepts a change only if
**every ported kernel carries a checked equivalence theorem** — `verify`'s
Lean stage — *and* (once the relational track's CLI lands) no forbidden
structural edge is introduced. Kernel `verify` is the first half, running
today; the conjunction is [roadmap](../limits.md).
