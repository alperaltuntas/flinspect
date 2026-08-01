#!/usr/bin/env bash
# Regenerate every pre-rendered command output embedded in the manual.
#
# The manual is built fully statically (no flang/clang/Lean at site-build
# time): each snippet file here is the REAL output of the command that the
# manual shows, captured by this script and committed. Rerun after any change
# that affects CLI output, then rebuild the site. tests/test_manual.py pins
# representative snippets against fresh runs (gated like the other
# corpus/clang tests), so the manual cannot rot silently.
#
# Requirements (run what your environment provides):
#   - always:            groundline installed (pip install -e .), run from the
#                        repo root with the venv active
#   - quickstart:        flang and clang++ on PATH — the quickstart is all
#                        source mode, each side's compiler runs on demand
#                        (NCAR: . /glade/work/altuntas/llvm-root/activate_llvm.sh)
#   - production list/show: the MOM6 dump directory + TIM headers referenced by
#                        examples/turbo-stack.kernels.toml
#   - axioms audit:      lake on PATH with the Mathlib cache provisioned
#                        (NCAR: . /glade/work/altuntas/lean-root/activate_lean.sh)
#
# Machine-path hygiene: quickstart outputs elide the absolute repo prefix to
# "…" so the committed snippets look like what any user sees; production
# outputs keep their /glade paths verbatim — the production manifest is
# honestly site-specific.

set -euo pipefail
cd "$(dirname "$0")/../.."          # repo root
REPO=$(pwd)
SNIP="$REPO/manual/snippets"

elide() { sed "s|$REPO|…|g"; }

# --- CLI help text (runs everywhere) ---------------------------------------
groundline --help                 > "$SNIP/cli_help.txt"
groundline kernel --help          > "$SNIP/cli_kernel_help.txt"
groundline kernel list --help     > "$SNIP/cli_kernel_list_help.txt"
groundline kernel show --help     > "$SNIP/cli_kernel_show_help.txt"
groundline kernel generate --help > "$SNIP/cli_kernel_generate_help.txt"
groundline kernel verify --help   > "$SNIP/cli_kernel_verify_help.txt"

# --- Quickstart walkthrough (C++ side needs clang++) ------------------------
# The verify snippet keeps its lake stage readable: the axioms audit replays
# into every build log (one `info:` line per declaration — see the trusted-base
# page), which is exactly right for CI and far too long for the quickstart, so
# compact_lake folds that block into one marker line.
compact_lake() {
  awk '/^(info:|ℹ|✔| )/ { if (!m) print "    ⋮ (the axioms audit replays here — one line per declaration)"; m=1; next }
       { print }'
}
(
  cd examples/quickstart
  groundline kernel list                    | elide > "$SNIP/quickstart_list.txt"
  groundline kernel show scale_clip_acc             > "$SNIP/quickstart_show.txt"
  groundline kernel generate                | elide > "$SNIP/quickstart_generate.txt"
  PYTHONUNBUFFERED=1 groundline kernel verify 2>&1 | elide | compact_lake \
                                                    > "$SNIP/quickstart_verify.txt"
)

# --- Production manifest (needs the corpus; show also needs clang++) --------
groundline kernel list --kernels examples/turbo-stack.kernels.toml \
    > "$SNIP/production_list.txt"
groundline kernel show ppm_limit_cw84 --kernels examples/turbo-stack.kernels.toml \
    > "$SNIP/production_show_ppm_limit_cw84.txt"

# --- The quickstart's closing loop section -----------------------------------
# toy_kernel_loop.f90 banked without its `pointize = true` license (loops and
# point functions don't compare unless you say so), then with it (the loop's
# per-point body, extracted). The page presents this as "add these lines to
# kernels.toml"; the temp manifest reproduces exactly that state.
TMP=$(mktemp -d)
cat > "$TMP/kernels.toml" <<MANIFEST
[fortran]
sources = "$REPO/examples/quickstart"
generated = "$TMP/G.lean"
namespace = "Demo"

[[kernel]]
name = "scale_clip_acc_loop"
fortran = { source = "toy_kernel_loop.f90", subroutine = "scale_clip_acc_loop" }
MANIFEST
( groundline kernel show scale_clip_acc_loop --kernels "$TMP/kernels.toml" 2>&1 || true ) \
    | elide > "$SNIP/quickstart_pointize_refusal.txt"
echo "pointize = true" >> "$TMP/kernels.toml"
groundline kernel show scale_clip_acc_loop --kernels "$TMP/kernels.toml" \
    > "$SNIP/quickstart_show_loop.txt"
rm -rf "$TMP"

# --- A real refusal (runs everywhere; exercises the CLI error path) ---------
# The recurrence fixture distilled from find_dz_for_eta's pressure
# accumulation: iteration k+1 reads what iteration k wrote, so pointize
# refuses (the manual's "boundary of the method" example).
TMP=$(mktemp -d)
cat > "$TMP/kernels.toml" <<EOF
[fortran]
dumps = "$REPO/tests/f90"
generated = "$TMP/Generated.lean"
namespace = "Demo"

[[kernel]]
name = "accumulate"
fortran = { dump = "test_kernel_recurrence_ptree", subroutine = "accumulate" }
pointize = true
EOF
( groundline kernel show accumulate --kernels "$TMP/kernels.toml" 2>&1 || true ) \
    | elide | sed "s|$TMP|/tmp/demo|g" > "$SNIP/refusal_recurrence.txt"
rm -rf "$TMP"

# --- Axioms audit (needs lake + the built Lean project) ---------------------
if command -v lake >/dev/null; then
  # Write through a temp file so a failed lake run (e.g. a bare elan shim
  # without a provisioned toolchain) can't truncate the committed snippet.
  AUD=$(mktemp)
  # lean renders messages at a fixed 120-column width, which wraps the longest
  # declaration names — rejoin continuation lines (indented) so the snippet
  # keeps one declaration per line, as in the build log's short lines.
  unwrap() { awk '{ if (sub(/^ +/, "")) buf = buf " " $0; else { if (buf != "") print buf; buf = $0 } } END { if (buf != "") print buf }'; }
  if ( cd lean/groundline && lake build >/dev/null 2>&1 \
        && lake env lean Groundline/AxiomsAudit.lean | unwrap ) > "$AUD"; then
    mv "$AUD" "$SNIP/axioms_audit.txt"
  else
    rm -f "$AUD"
    echo "note: lake failed (toolchain not provisioned?) — axioms_audit.txt kept as is" >&2
  fi
else
  echo "note: lake not on PATH — skipping axioms_audit.txt" >&2
fi

echo "snippets rendered into $SNIP"
