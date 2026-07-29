#!/usr/bin/env bash
#
# Regenerate the *_ptree fixtures from the *.f90 sources in this directory using
# flang's WITH-SEMA parse-tree dump:
#
#     flang -fc1 -fdebug-dump-parse-tree FILE.f90 > FILE_ptree
#
# With-sema is what the production pipeline emits (VISION D4), so tests and
# production parse the same dump variant. Two consequences for anyone adding a
# fixture here:
#
#   * It must be *valid* Fortran, not merely parseable — on a semantic error flang
#     emits no dump at all. An ambiguous generic interface, for instance, is fatal.
#   * It must be self-contained. A fixture that USEd a module defined in another
#     file would need that module's .mod file built first (DEVLOG 2026-05-28);
#     every fixture here keeps its modules in one file to avoid that.
#
# Requires flang on PATH (on Derecho: `source /glade/work/.../activate_llvm.sh`).

set -uo pipefail

cd "$(dirname "$0")" || exit 1

if ! command -v flang >/dev/null 2>&1; then
    echo "error: flang not found on PATH" >&2
    exit 1
fi

status=0
for file in *.f90; do
    [ -f "$file" ] || continue
    output_file="${file%.f90}_ptree"
    tmp="${output_file}.tmp"
    if flang -fc1 -fdebug-dump-parse-tree "$file" > "$tmp" 2> "${tmp}.err"; then
        mv "$tmp" "$output_file"
        echo "Generated $output_file from $file"
    else
        # Leave the existing fixture alone rather than replacing it with an empty
        # file — a sema failure means the fixture is broken, not that it changed.
        echo "FAILED: $file — flang rejected it, $output_file left unchanged:" >&2
        sed 's/^/    /' "${tmp}.err" >&2
        rm -f "$tmp"
        status=1
    fi
    rm -f "${tmp}.err"
done

# flang writes a .mod per module as a side effect of the dump; fixtures don't need them.
rm -f ./*.mod

# The dump format carries no stability contract (DESIGN Q1), so record which flang
# produced these fixtures — a format change shows up as a version delta here.
{
    echo "Provenance of the *_ptree fixtures in this directory."
    echo "Regenerate with ./gen_ptree_files.sh (with-sema dump, VISION D4)."
    echo
    echo "Generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    echo "Command:   flang -fc1 -fdebug-dump-parse-tree <file>.f90"
    echo
    flang --version
} > PROVENANCE

echo "Wrote PROVENANCE"
exit $status
