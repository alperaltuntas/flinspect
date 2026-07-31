"""Track B packaging tests: the kernel manifest (``kernels.toml``), the
uniform KernelFrontend spec API, and the ``flinspect kernel`` CLI.

Everything here runs everywhere (no corpus, no clang, no /glade paths): the
Fortran fixtures are the committed ``tests/f90`` dumps, and CLI tests drive
:func:`flinspect.cli.main` in-process against manifests built in ``tmp_path``.
The production golden tests stay in ``tests/test_kir_lean.py``; the quickstart
example's golden tests are in this file's quickstart section (the C++ side
gated on clang, like every clang-tier test).
"""

import shutil
from pathlib import Path

import pytest

from flinspect import kernel_bank as kb
from flinspect.cli import main as cli_main
from flinspect.frontend.flang_kernel import (
    FlangKernelFrontend, extract_kernel, extract_loop_kernel,
)
from flinspect.frontend.kernel_base import CppKernelSpec, FortranKernelSpec

F90_DIR = Path(__file__).parent / "f90"
REPO = Path(__file__).parent.parent
QUICKSTART = REPO / "examples" / "quickstart"

needs_clang = pytest.mark.skipif(
    shutil.which("clang++") is None,
    reason="clang++ not on PATH (source activate_llvm.sh)")


# =============================================================================
# Spec API: the KernelFrontend seam produces exactly what the functions do
# =============================================================================

class TestFortranSpecAPI:

    def test_whole_subroutine_spec(self):
        dump = F90_DIR / "test_kernel_doconcurrent_ptree"
        via_spec = FlangKernelFrontend().extract(
            FortranKernelSpec(dump=dump, subroutine="clamp_scale"))
        assert via_spec == extract_kernel(dump, "clamp_scale")

    def test_inline_loop_spec(self):
        dump = F90_DIR / "test_kernel_inline_nests_ptree"
        via_spec = FlangKernelFrontend().extract(
            FortranKernelSpec(dump=dump, subroutine="two_nests", nest=1,
                              def_name="scale_branch"))
        assert via_spec == extract_loop_kernel(dump, "two_nests", 1,
                                               "scale_branch")

    def test_nest_without_def_name_refused(self):
        with pytest.raises(ValueError, match="nest and def_name"):
            FortranKernelSpec(dump=Path("x"), subroutine="s", nest=1)

    def test_def_name_without_nest_refused(self):
        with pytest.raises(ValueError, match="nest and def_name"):
            FortranKernelSpec(dump=Path("x"), subroutine="s", def_name="d")


# =============================================================================
# Manifest loading (refuse-don't-guess: unknown keys, inconsistencies)
# =============================================================================

MINI_MANIFEST = """\
[fortran]
corpus = "${TEST_CORPUS_DIR}"
out = "Generated.lean"
namespace = "Mini.Generated"

[[kernel]]
name = "clamp_scale"
fortran = { dump = "test_kernel_doconcurrent_ptree", subroutine = "clamp_scale" }
"""


@pytest.fixture
def mini_manifest(tmp_path, monkeypatch):
    """A minimal fortran-only manifest over the committed f90 fixtures; the
    corpus travels through ${TEST_CORPUS_DIR} to pin env expansion."""
    monkeypatch.setenv("TEST_CORPUS_DIR", str(F90_DIR))
    path = tmp_path / "kernels.toml"
    path.write_text(MINI_MANIFEST)
    return path


class TestManifestLoading:

    def test_load_expands_env_and_resolves_paths(self, mini_manifest, tmp_path):
        m = kb.load_manifest(mini_manifest)
        assert m.fortran.corpus == F90_DIR
        assert m.fortran.out == tmp_path / "Generated.lean"   # manifest-relative
        e = m.kernel("clamp_scale")
        assert e.fortran.dump == F90_DIR / "test_kernel_doconcurrent_ptree"
        assert e.fortran_dump_label == "test_kernel_doconcurrent_ptree"
        assert e.cpp is None

    def test_unset_env_var_refused(self, mini_manifest, monkeypatch):
        monkeypatch.delenv("TEST_CORPUS_DIR")
        with pytest.raises(kb.ManifestError, match="TEST_CORPUS_DIR"):
            kb.load_manifest(mini_manifest)

    def test_unknown_key_refused(self, mini_manifest):
        text = mini_manifest.read_text().replace("corpus =", "corpsu =")
        mini_manifest.write_text(text)
        with pytest.raises(kb.ManifestError, match="corpsu"):
            kb.load_manifest(mini_manifest)

    def test_missing_manifest_refused(self, tmp_path):
        with pytest.raises(kb.ManifestError, match="not found"):
            kb.load_manifest(tmp_path / "nope.toml")

    def test_whole_subroutine_name_mismatch_refused(self, mini_manifest):
        text = mini_manifest.read_text().replace('name = "clamp_scale"',
                                                 'name = "wrong_name"')
        mini_manifest.write_text(text)
        with pytest.raises(kb.ManifestError, match="named after its"):
            kb.load_manifest(mini_manifest)

    def test_def_name_without_nest_refused(self, mini_manifest):
        text = mini_manifest.read_text().replace(
            'subroutine = "clamp_scale" }',
            'subroutine = "clamp_scale", def_name = "x" }')
        mini_manifest.write_text(text)
        with pytest.raises(kb.ManifestError, match="def_name"):
            kb.load_manifest(mini_manifest)

    def test_duplicate_kernel_names_refused(self, mini_manifest):
        text = mini_manifest.read_text()
        text += ('\n[[kernel]]\nname = "clamp_scale"\n'
                 'fortran = { dump = "test_kernel_doconcurrent_ptree", '
                 'subroutine = "clamp_scale" }\n')
        mini_manifest.write_text(text)
        with pytest.raises(kb.ManifestError, match="duplicate"):
            kb.load_manifest(mini_manifest)

    def test_cpp_side_without_cpp_section_refused(self, mini_manifest):
        text = mini_manifest.read_text()
        text = text.replace(
            'fortran = { dump = "test_kernel_doconcurrent_ptree", '
            'subroutine = "clamp_scale" }',
            'fortran = { dump = "test_kernel_doconcurrent_ptree", '
            'subroutine = "clamp_scale" }\ncpp = { header = "x.hpp", '
            'function = "f" }')
        mini_manifest.write_text(text)
        with pytest.raises(kb.ManifestError, match=r"no \[cpp\] section"):
            kb.load_manifest(mini_manifest)

    def test_unknown_kernel_name_lookup_refused(self, mini_manifest):
        m = kb.load_manifest(mini_manifest)
        with pytest.raises(kb.ManifestError, match="no kernel named"):
            m.kernel("nonexistent")


class TestManifestResolutionOrder:
    """CLI flag > $FLINSPECT_KERNELS > ./kernels.toml — and nothing else."""

    def test_explicit_beats_env(self, monkeypatch):
        monkeypatch.setenv(kb.MANIFEST_ENV, "/env/kernels.toml")
        assert kb.resolve_manifest_path("/cli/kernels.toml") == \
            Path("/cli/kernels.toml")

    def test_env_beats_cwd(self, monkeypatch, tmp_path):
        monkeypatch.setenv(kb.MANIFEST_ENV, "/env/kernels.toml")
        monkeypatch.chdir(tmp_path)
        (tmp_path / kb.MANIFEST_FILENAME).write_text("")
        assert kb.resolve_manifest_path(None) == Path("/env/kernels.toml")

    def test_cwd_fallback(self, monkeypatch, tmp_path):
        monkeypatch.delenv(kb.MANIFEST_ENV, raising=False)
        monkeypatch.chdir(tmp_path)
        (tmp_path / kb.MANIFEST_FILENAME).write_text("")
        assert kb.resolve_manifest_path(None) == Path(kb.MANIFEST_FILENAME)

    def test_no_manifest_anywhere_refused(self, monkeypatch, tmp_path):
        monkeypatch.delenv(kb.MANIFEST_ENV, raising=False)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(kb.ManifestError, match="--kernels"):
            kb.resolve_manifest_path(None)


# =============================================================================
# Rendering + CLI (in-process, fortran-only: runs everywhere)
# =============================================================================

EXPECTED_CLAMP_SCALE_DEF = """\
def clamp_scale (x_in x_out lo : ℝ) : ℝ :=
  let w := 2 * x_in - x_out
  if |w| < lo then
    lo
  else if w ^ 2 > 4 * lo then
    x_in + w / 2
  else (w + lo) * 0.5
"""


class TestRenderAndCli:

    def test_render_fortran_contains_the_fixture_def(self, mini_manifest):
        text = kb.render_fortran(kb.load_manifest(mini_manifest))
        assert EXPECTED_CLAMP_SCALE_DEF in text
        assert "namespace Mini.Generated" in text
        assert "flinspect kernel generate" in text       # provenance names the CLI
        assert f"manifest: `{mini_manifest.name}`" in text

    def test_cli_list(self, mini_manifest, capsys):
        assert cli_main(["kernel", "list", "--kernels",
                         str(mini_manifest)]) == 0
        out = capsys.readouterr().out
        assert "clamp_scale" in out and "[ok]" in out
        assert "not yet generated" in out

    def test_cli_show(self, mini_manifest, capsys):
        assert cli_main(["kernel", "show", "clamp_scale", "--kernels",
                         str(mini_manifest)]) == 0
        out = capsys.readouterr().out
        assert EXPECTED_CLAMP_SCALE_DEF.splitlines()[0] in out

    def test_cli_show_unknown_kernel_exits_2(self, mini_manifest, capsys):
        assert cli_main(["kernel", "show", "nope", "--kernels",
                         str(mini_manifest)]) == 2
        assert "no kernel named" in capsys.readouterr().err

    def test_cli_generate_verify_roundtrip(self, mini_manifest, tmp_path,
                                           capsys):
        assert cli_main(["kernel", "generate", "--kernels",
                         str(mini_manifest)]) == 0
        out_file = tmp_path / "Generated.lean"
        assert EXPECTED_CLAMP_SCALE_DEF in out_file.read_text()
        assert cli_main(["kernel", "verify", "--kernels",
                         str(mini_manifest)]) == 0
        assert "matches a fresh regeneration" in capsys.readouterr().out

    def test_cli_verify_detects_drift(self, mini_manifest, tmp_path, capsys):
        assert cli_main(["kernel", "generate", "--kernels",
                         str(mini_manifest)]) == 0
        out_file = tmp_path / "Generated.lean"
        out_file.write_text(out_file.read_text().replace("2 *", "3 *"))
        assert cli_main(["kernel", "verify", "--kernels",
                         str(mini_manifest)]) == 1
        assert "DRIFT" in capsys.readouterr().out

    def test_cli_verify_missing_output_is_drift(self, mini_manifest, capsys):
        assert cli_main(["kernel", "verify", "--kernels",
                         str(mini_manifest)]) == 1
        assert "does not exist" in capsys.readouterr().out

    def test_cli_missing_manifest_exits_2(self, monkeypatch, tmp_path, capsys):
        monkeypatch.delenv(kb.MANIFEST_ENV, raising=False)
        monkeypatch.chdir(tmp_path)
        assert cli_main(["kernel", "list"]) == 2
        assert "no kernel manifest" in capsys.readouterr().err

    def test_cli_import_path_is_widget_free(self):
        """The CLI must work in a bare venv: importing it may not pull in the
        widget stack (ipywidgets/ipycytoscape/jupyter)."""
        import subprocess
        import sys
        code = ("import sys; import flinspect.cli; "
                "bad = [m for m in sys.modules "
                "if 'ipywidgets' in m or 'ipycytoscape' in m or 'jupyter' in m]; "
                "sys.exit(1 if bad else 0)")
        assert subprocess.run([sys.executable, "-c", code]).returncode == 0


# =============================================================================
# Quickstart example (the committed portability proof)
# =============================================================================

class TestQuickstart:
    """The committed toy pair in examples/quickstart: the Fortran side runs
    everywhere (its with-sema dump is committed), the C++ side needs clang
    (its header is standalone — no AMReX, no MPI)."""

    @pytest.fixture
    def manifest(self):
        return kb.load_manifest(QUICKSTART / "kernels.toml")

    def test_fortran_golden(self, manifest):
        assert kb.render_fortran(manifest) == manifest.fortran.out.read_text(), \
            "quickstart Generated.lean is stale — rerun `flinspect kernel generate`"

    @needs_clang
    def test_cpp_golden(self, manifest):
        # The module header stamps the LOCAL clang version (provenance), which
        # legitimately varies across machines — the golden pins the defs.
        def defs(text: str) -> str:
            return text.split("-/\n", 1)[1]
        assert defs(kb.render_cpp(manifest)) == \
            defs(manifest.cpp.out.read_text()), \
            "quickstart GeneratedCpp.lean is stale — rerun `flinspect kernel generate`"
