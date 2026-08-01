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

When a tool is missing, the gate says so rather than passing quietly: a
missing compiler that some kernel needs run fresh (`flang` for source-mode
Fortran entries, `clang++` for the C++ side) is an **error** on `verify` (a
gate must not pass vacuously) unless you explicitly scope the run with
`--skip-fortran`/`--skip-cpp`.

## The installation levels, in CI terms

| CI environment has | Run | Gate covers |
|---|---|---|
| Python only | pytest over `tests/f90` fixtures | Fortran extraction + printing against pre-generated dumps |
| + the *pinned* flang & clang++ | `groundline kernel verify` (quickstart manifest) | both sides of extraction + printing |
| + the dump directory & kernel sources | `verify --kernels examples/turbo-stack.kernels.toml` | the real kernel bank |
| + Lean toolchain | same | every equivalence theorem + axioms audit |

The quickstart manifest is the portable smoke test — both its sources are
standalone files, so any runner with flang and clang++ on `PATH` can execute
the second row. One subtlety there: the committed quickstart module headers
stamp the compiler versions that produced them (toolchain is provenance),
and `verify` byte-diffs the **whole file** — so the full byte-diff passes
only under the pinned toolchain. On runners with a different flang/clang,
cover the quickstart with the pytest suite instead: its golden tests compare
the *defs* only, by design. The production rows require site resources
(the case-study dumps and kernel headers live on NCAR storage),
which in practice means a self-hosted or site-local runner for the full gate.

## Example: GitHub Actions job (the portable level)

```yaml
kernel-tests:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.12"
    - run: pip install -e '.[dev]'
    - name: Test suite (compiler-gated halves skip when a toolchain is absent)
      run: pytest
```

The dump-, flang-, and clang-gated tests *skip* rather than fail when their
toolchain is absent, so the `pytest` step is safe on any runner and
strengthens itself as tools become available. On a runner that provides the
pinned flang and clang, add the byte-exact gate on top:

```yaml
    - name: Verify the quickstart kernel bank (byte-exact, both sides)
      run: groundline kernel verify
      working-directory: examples/quickstart
```

## The gate this is designed to become

The intended end state, from the project's vision: CI accepts a change only if
**every ported kernel carries a checked equivalence theorem** — `verify`'s
Lean stage — *and* (once the relational track's CLI lands) no forbidden
structural edge is introduced. Kernel `verify` is the first half, running
today; the conjunction is [roadmap](../limits.md).
