"""Manual honesty checks: the pre-rendered outputs committed under
``manual/snippets/`` (and embedded in the MkDocs site) must keep matching what
the real pipeline produces — the manual must not rot silently.

Every snippet is produced by ``manual/snippets/render_snippets.sh``; these
tests re-derive the representative ones in-process and byte-compare. Gating
mirrors the rest of the suite: the quickstart is all source mode, so its
Fortran half needs ``flang`` on PATH exactly as its C++ half needs
``clang++``; the recurrence refusal runs everywhere (committed fixture).
"""

import shutil
from pathlib import Path

import pytest

from groundline import kernel_bank as kb
from groundline.cli import main as cli_main
from groundline.lean_printer import print_kernel

REPO = Path(__file__).parent.parent
SNIPPETS = REPO / "manual" / "snippets"
QUICKSTART = REPO / "examples" / "quickstart"
QUICKSTART_MANIFEST = QUICKSTART / "kernels.toml"

needs_clang = pytest.mark.skipif(
    shutil.which("clang++") is None,
    reason="clang++ not on PATH (source activate_llvm.sh)")
needs_flang = pytest.mark.skipif(
    shutil.which("flang") is None,
    reason="flang not on PATH (source activate_llvm.sh)")


def _show_fortran() -> str:
    m = kb.load_manifest(QUICKSTART_MANIFEST)
    e = m.kernel("scale_clip_acc")
    return print_kernel(kb.extract_fortran_entry(e),
                        provenance=kb.fortran_provenance(e))


def _show_cpp() -> str:
    m = kb.load_manifest(QUICKSTART_MANIFEST)
    e = m.kernel("scale_clip_acc")
    return print_kernel(kb.extract_cpp_entry(e),
                        provenance=kb.cpp_provenance(e))


class TestQuickstartShowSnippet:
    """The manual's `groundline kernel show scale_clip_acc` output
    (quickstart_show.txt) matches a fresh run. The snippet is both defs
    joined by a blank line — exactly what `_cmd_show` prints."""

    @needs_flang
    def test_fortran_half_matches(self):
        committed = (SNIPPETS / "quickstart_show.txt").read_text()
        fresh = _show_fortran()
        assert committed.startswith(fresh), (
            "manual/snippets/quickstart_show.txt has rotted (Fortran half) — "
            "rerun manual/snippets/render_snippets.sh")

    @needs_flang
    @needs_clang
    def test_full_snippet_matches(self):
        committed = (SNIPPETS / "quickstart_show.txt").read_text()
        fresh = "\n".join([_show_fortran(), _show_cpp()])
        assert committed == fresh, (
            "manual/snippets/quickstart_show.txt has rotted — "
            "rerun manual/snippets/render_snippets.sh")


class TestRefusalSnippet:
    """The manual's k-recurrence refusal (refusal_recurrence.txt) is the real
    CLI error line, reproduced against the committed fixture."""

    def test_refusal_line_matches(self, tmp_path, capsys):
        manifest = tmp_path / "kernels.toml"
        manifest.write_text(
            f'[fortran]\n'
            f'dumps = "{REPO / "tests" / "f90"}"\n'
            f'generated = "{tmp_path / "Generated.lean"}"\n'
            f'namespace = "Demo"\n\n'
            f'[[kernel]]\n'
            f'name = "accumulate"\n'
            f'fortran = {{ dump = "test_kernel_recurrence_ptree", '
            f'subroutine = "accumulate" }}\n'
            f'pointize = true\n')
        rc = cli_main(["kernel", "show", "accumulate",
                       "--kernels", str(manifest)])
        assert rc == 2
        err = capsys.readouterr().err
        committed = (SNIPPETS / "refusal_recurrence.txt").read_text()
        assert committed.strip() == err.strip(), (
            "manual/snippets/refusal_recurrence.txt has rotted — "
            "rerun manual/snippets/render_snippets.sh")


class TestQuickstartLoopSection:
    """The quickstart's closing loop section: the loop/point refusal
    (quickstart_pointize_refusal.txt) and the pointized loop's def
    (quickstart_show_loop.txt) are the real CLI outputs, reproduced against
    the quickstart's toy_kernel_loop.f90 (source mode, so flang-gated)."""

    def _manifest(self, tmp_path, pointize: bool) -> Path:
        manifest = tmp_path / "kernels.toml"
        manifest.write_text(
            f'[fortran]\n'
            f'sources = "{QUICKSTART}"\n'
            f'generated = "{tmp_path / "G.lean"}"\n'
            f'namespace = "Demo"\n\n'
            f'[[kernel]]\n'
            f'name = "scale_clip_acc_loop"\n'
            f'fortran = {{ source = "toy_kernel_loop.f90", '
            f'subroutine = "scale_clip_acc_loop" }}\n'
            + ('pointize = true\n' if pointize else ''))
        return manifest

    @needs_flang
    def test_refusal_line_matches(self, tmp_path, capsys):
        rc = cli_main(["kernel", "show", "scale_clip_acc_loop",
                       "--kernels", str(self._manifest(tmp_path, False))])
        assert rc == 2
        err = capsys.readouterr().err
        committed = (SNIPPETS / "quickstart_pointize_refusal.txt").read_text()
        assert committed.strip() == err.strip(), (
            "manual/snippets/quickstart_pointize_refusal.txt has rotted — "
            "rerun manual/snippets/render_snippets.sh")

    @needs_flang
    def test_pointized_show_matches(self, tmp_path, capsys):
        rc = cli_main(["kernel", "show", "scale_clip_acc_loop",
                       "--kernels", str(self._manifest(tmp_path, True))])
        assert rc == 0
        out = capsys.readouterr().out
        committed = (SNIPPETS / "quickstart_show_loop.txt").read_text()
        assert committed == out, (
            "manual/snippets/quickstart_show_loop.txt has rotted — "
            "rerun manual/snippets/render_snippets.sh")


class TestAxiomsAuditSnippet:
    """The manual's axioms-audit quote (axioms_audit.txt) stays consistent
    with Groundline/AxiomsAudit.lean: same declarations, in the audit file's
    order, and only the three standard axioms (or subsets, which the audit
    file documents for the SeqSchema block). Re-running Lean is the verify
    gate's job; this pins manual ↔ audit-file consistency everywhere."""

    def test_snippet_covers_exactly_the_audited_declarations(self):
        audit_src = (REPO / "lean" / "groundline" / "Groundline" /
                     "AxiomsAudit.lean").read_text()
        audited = [line.split()[-1] for line in audit_src.splitlines()
                   if line.startswith("#print axioms ")]
        snippet = (SNIPPETS / "axioms_audit.txt").read_text().strip()
        quoted = [line.split("'")[1] for line in snippet.splitlines()]
        assert quoted == audited, (
            "manual/snippets/axioms_audit.txt lists different declarations "
            "than Groundline/AxiomsAudit.lean — rerun render_snippets.sh with the "
            "Lean toolchain active")

    def test_snippet_reports_only_the_standard_axioms(self):
        allowed = {"propext", "Classical.choice", "Quot.sound"}
        for line in (SNIPPETS / "axioms_audit.txt").read_text().strip().splitlines():
            if "does not depend on any axioms" in line:
                continue
            axioms = line.split("[")[1].rstrip("]").split(", ")
            assert set(axioms) <= allowed, f"unexpected axiom in: {line}"
