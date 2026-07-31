"""Track B tests: kernel-IR extraction, passes, and the Lean printer.

Two tiers, per D7: fixture-based tests run everywhere (the
``test_kernel_doconcurrent`` / ``test_kernel_ifstmt_join`` /
``test_kernel_negate`` conformance fixtures); the production golden test —
regenerating ``lean/pilot/Pilot/Generated.lean`` byte-for-byte from the MOM6
corpus — is gated on ``FLINSPECT_CORPUS``. Semantic fidelity of the generated
Lean is checked *in Lean* (``lean/pilot/Pilot/Fidelity.lean``), not here.
"""

import os
import shutil
from pathlib import Path

import pytest

from flinspect.kir import (
    Assign, BinOp, DoConcurrent, If, IntLit, Kernel, Param, RealLit, Tuple_,
    UnsupportedConstruct, Var, ArrayRef, functionalize, pointize,
)
from flinspect.frontend.flang_kernel import extract_kernel
from flinspect.lean_printer import print_kernel

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


class TestIfStmtJoinFixture:
    """Logical IF statements (R1139) + the sequential guarded join: the loop
    ends with two guarded assignments to state, and the second guard's RHS
    reads b, which the first IF may have just updated."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.kernel = extract_kernel(F90_DIR / "test_kernel_ifstmt_join_ptree",
                                     "guard_pair")

    def test_ifstmt_extracted_as_single_branch_if(self):
        loop = self.kernel.body[0]
        assert isinstance(loop, DoConcurrent)
        for stmt in loop.body[1:]:
            assert isinstance(stmt, If)
            assert len(stmt.branches) == 1 and stmt.orelse == ()

    def test_printed_lean_threads_merged_state(self):
        # The load-bearing assertion: c's new value reads the MERGED b —
        # `(if t > b then t - 1 else b) + t` — not the input b.
        text = print_kernel(pointize(self.kernel))
        expected = """\
def guard_pair (a b c : ℝ) : ℝ × ℝ :=
  let t := 2 * a
  if t < c then
    (if t > b then t - 1 else b, (if t > b then t - 1 else b) + t)
  else (if t > b then t - 1 else b, c)
"""
        assert text == expected


class TestNegateFixture:
    """Unary minus: bare leaf (-y), compound operand needing printer parens
    (-(2 * x)), and negated source parentheses (-(x + y))."""

    def test_printed_lean(self):
        kernel = extract_kernel(F90_DIR / "test_kernel_negate_ptree", "neg_clip")
        expected = """\
def neg_clip (x y : ℝ) : ℝ :=
  if x < -y then
    -(2 * x)
  else -(x + y)
"""
        assert print_kernel(pointize(kernel)) == expected


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


class TestJoinRefusals:
    """The control-flow join is supported in exactly one shape (single-branch
    If whose branches assign only to state variables); everything else refuses.
    The supported shape itself is pinned by TestIfStmtJoinFixture."""

    def _kernel(self, if_stmt):
        after = Assign(ArrayRef("b", (Var("i"),)), ArrayRef("a", (Var("i"),)))
        return Kernel(
            "k",
            (Param("a", "real", "in", 1), Param("b", "real", "inout", 1),
             Param("q", "real", "in", 0), Param("n", "integer", "in", 0)),
            (Param("w", "real", None, 0), Param("i", "integer", None, 0)),
            body=(DoConcurrent((("i", IntLit("1"), Var("n")),),
                               (if_stmt, after)),),
        )

    def test_local_assignment_in_joined_branch_refused(self):
        # w is a local: merging it would need a Let to escape the branch.
        stmt = If(((Var("q"), (Assign(Var("w"), RealLit("1.0")),)),), ())
        with pytest.raises(UnsupportedConstruct, match="Let may not escape"):
            print_kernel(pointize(self._kernel(stmt)))

    def test_nested_if_in_joined_branch_refused(self):
        assign_b = Assign(ArrayRef("b", (Var("i"),)), Var("q"))
        stmt = If(((Var("q"), (If(((Var("q"), (assign_b,)),), ()),)),), ())
        with pytest.raises(UnsupportedConstruct, match="only assignments"):
            print_kernel(pointize(self._kernel(stmt)))

    def test_elseif_chain_join_refused(self):
        assign_b = Assign(ArrayRef("b", (Var("i"),)), Var("q"))
        stmt = If(((Var("q"), (assign_b,)), (Var("q"), (assign_b,))), ())
        with pytest.raises(UnsupportedConstruct, match="elseif"):
            print_kernel(pointize(self._kernel(stmt)))


def test_sequential_alias_read_threads_current_value():
    """After `b = a`, a read of b must see a (its current value), not the
    input b — even though the current value is a plain Var. Pins the
    unconditional substitution in functionalize.subst."""
    k = Kernel(
        "k",
        (Param("a", "real", "in", 0), Param("b", "real", "inout", 0),
         Param("c", "real", "inout", 0)),
        (),
        (Assign(Var("b"), Var("a")), Assign(Var("c"), Var("b"))),
    )
    _, outputs, expr = functionalize(k)
    assert outputs == ("b", "c")
    assert expr == Tuple_((Var("a"), Var("a")))


# =============================================================================
# Production golden test (gated on the corpus)
# =============================================================================

CORPUS = os.environ.get("FLINSPECT_CORPUS")


def _load_generate():
    """Import lean/pilot/generate.py so the kernel lists and rendering come
    from the driver itself — the golden tests can't drift from it."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "pilot_generate", REPO / "lean" / "pilot" / "generate.py")
    generate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generate)
    return generate


@pytest.mark.skipif(not CORPUS, reason="FLINSPECT_CORPUS not set")
def test_generated_lean_is_current():
    """lean/pilot/Pilot/Generated.lean must match a fresh regeneration."""
    generate = _load_generate()
    text = generate.render(CORPUS)
    committed = (REPO / "lean" / "pilot" / "Pilot" / "Generated.lean").read_text()
    assert text == committed, "Generated.lean is stale — rerun lean/pilot/generate.py"


@pytest.mark.skipif(shutil.which("clang++") is None,
                    reason="clang++ not on PATH (source activate_llvm.sh)")
def test_generated_cpp_lean_is_current():
    """lean/pilot/Pilot/GeneratedCpp.lean must match a fresh regeneration —
    the C++ sibling of test_generated_lean_is_current (drift alarm for the
    committed file, the TIM header, AND the pinned clang itself, whose
    version line is stamped into the output)."""
    generate = _load_generate()
    if not Path(generate.DEFAULT_CPP_HEADER).exists():
        pytest.skip("TIM kernel header not present")
    if not all(Path(d).exists() for d in generate.DEFAULT_CPP_INCLUDE_DIRS):
        pytest.skip("pinned C++ include dirs not present")
    text = generate.render_cpp()
    committed = (REPO / "lean" / "pilot" / "Pilot" / "GeneratedCpp.lean").read_text()
    assert text == committed, \
        "GeneratedCpp.lean is stale — rerun lean/pilot/generate.py"
