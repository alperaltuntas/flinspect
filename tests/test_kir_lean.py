"""Track B tests: kernel-IR extraction, passes, and the Lean printer.

Two tiers, per D7: fixture-based tests run everywhere (the
``test_kernel_doconcurrent`` conformance fixture); the production golden test —
regenerating ``lean/pilot/Pilot/Generated.lean`` byte-for-byte from the MOM6
corpus — is gated on ``FLINSPECT_CORPUS``. Semantic fidelity of the generated
Lean is checked *in Lean* (``lean/pilot/Pilot/Fidelity.lean``), not here.
"""

import os
from pathlib import Path

import pytest

from flinspect.kir import (
    Assign, BinOp, DoConcurrent, If, IntLit, Kernel, Param, RealLit,
    UnsupportedConstruct, Var, ArrayRef, pointize,
)
from flinspect.frontend.flang_kernel import extract_kernel
from flinspect.lean_printer import print_kernel, print_module

F90_DIR = Path(__file__).parent / "f90"
REPO = Path(__file__).parent.parent


# =============================================================================
# Fixture-based end-to-end: extract -> pointize -> print
# =============================================================================

class TestKernelFixture:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.kernel = extract_kernel(F90_DIR / "test_kernel_doconcurrent_ptree",
                                     "clamp_scale")

    def test_extraction_shape(self):
        assert [p.name for p in self.kernel.params] == ["x_in", "x_out", "lo", "n"]
        assert [p.name for p in self.kernel.locals] == ["w", "i"]
        assert len(self.kernel.body) == 1
        assert isinstance(self.kernel.body[0], DoConcurrent)

    def test_pointize_drops_loop_machinery(self):
        pk = pointize(self.kernel)
        assert [p.name for p in pk.params] == ["x_in", "x_out", "lo"]  # n dropped
        assert [p.name for p in pk.locals] == ["w"]                    # i dropped
        assert all(p.rank == 0 for p in pk.params)

    def test_printed_lean(self):
        text = print_kernel(pointize(self.kernel))
        expected = """\
def clamp_scale (x_in x_out lo : ℝ) : ℝ :=
  let w := 2 * x_in - x_out
  if |w| < lo then
    lo
  else if w ^ 2 > 4 * lo then
    x_in + w / 2
  else (w + lo) * 0.5
"""
        assert text == expected


# =============================================================================
# Pass-level refusals (trusted base: refuse, never guess)
# =============================================================================

def _mini_kernel(body_stmt):
    return Kernel(
        name="k",
        params=(Param("a", "real", "in", 1), Param("b", "real", "inout", 1),
                Param("n", "integer", "in", 0)),
        locals=(Param("i", "integer", None, 0),),
        body=(DoConcurrent((("i", IntLit("1"), Var("n")),), (body_stmt,)),),
    )


class TestPointizeRefusals:

    def test_offset_subscript_refused(self):
        stmt = Assign(ArrayRef("b", (Var("i"),)),
                      ArrayRef("a", (BinOp("add", Var("i"), IntLit("1")),)))
        with pytest.raises(UnsupportedConstruct, match="not indexed exactly"):
            pointize(_mini_kernel(stmt))

    def test_non_do_concurrent_body_refused(self):
        k = Kernel("k", (Param("b", "real", "inout", 0),), (),
                   (Assign(Var("b"), RealLit("1.0")),
                    Assign(Var("b"), RealLit("2.0"))))
        with pytest.raises(UnsupportedConstruct, match="do-concurrent"):
            pointize(k)

    def test_join_after_if_refused(self):
        good = Assign(ArrayRef("b", (Var("i"),)), ArrayRef("a", (Var("i"),)))
        cond_stmt = If(((Var("q"), (good,)),), ())
        k = Kernel(
            "k",
            (Param("a", "real", "in", 1), Param("b", "real", "inout", 1),
             Param("q", "real", "in", 0), Param("n", "integer", "in", 0)),
            (Param("i", "integer", None, 0),),
            body=(DoConcurrent((("i", IntLit("1"), Var("n")),),
                               (cond_stmt, good)),),
        )
        with pytest.raises(UnsupportedConstruct, match="join"):
            print_kernel(pointize(k))


# =============================================================================
# Production golden test (gated on the corpus)
# =============================================================================

CORPUS = os.environ.get("FLINSPECT_CORPUS")


@pytest.mark.skipif(not CORPUS, reason="FLINSPECT_CORPUS not set")
def test_generated_lean_is_current():
    """lean/pilot/Pilot/Generated.lean must match a fresh regeneration."""
    dump = Path(CORPUS) / "MOM6" / "MOM_continuity_PPM.o_ptree"
    kernel = pointize(extract_kernel(dump, "ppm_limit_pos"))
    text = print_module(
        [(kernel, "`ppm_limit_pos` in `MOM6/MOM_continuity_PPM.o_ptree` "
                  "(flang with-sema dump)")],
        namespace="TrackB.Generated")
    committed = (REPO / "lean" / "pilot" / "Pilot" / "Generated.lean").read_text()
    assert text == committed, "Generated.lean is stale — rerun lean/pilot/generate.py"
