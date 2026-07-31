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
    Assign, BinOp, ComponentRef, Do, DoConcurrent, If, IntLit, Kernel, Param,
    RealLit, Tuple_, UnsupportedConstruct, Var, ArrayRef, functionalize,
    pointize,
)
from flinspect.frontend.flang_kernel import extract_kernel, extract_loop_kernel
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


class TestPlainDoFixture:
    """Rule A: a plain, perfectly nested do nest as a point kernel. The Python
    gate is the same array-index check as do concurrent; the semantic license
    is the Lean schema lemma (Pilot/SeqSchema.lean), not a source assertion."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.kernel = extract_kernel(F90_DIR / "test_kernel_plaindo_ptree",
                                     "scale_clip")

    def test_extraction_shape(self):
        assert len(self.kernel.body) == 1
        outer = self.kernel.body[0]
        assert isinstance(outer, Do) and outer.control[0] == "j"
        assert len(outer.body) == 1
        inner = outer.body[0]
        assert isinstance(inner, Do) and inner.control[0] == "i"

    def test_printed_lean(self):
        expected = """\
def scale_clip (a b s : ℝ) : ℝ :=
  let w := s * a
  if w > b then
    w
  else b
"""
        assert print_kernel(pointize(self.kernel)) == expected


class TestRecurrenceRefusalFixture:
    """Rule A's load-bearing refusal, distilled from find_dz_for_eta's pressure
    accumulation: p(i,K+1) reads what the previous k-iteration wrote. The K+1
    offset fails the index gate; K vs k is NOT a name mismatch (the dump
    lowercases — Fortran is case-insensitive)."""

    def test_recurrence_refused(self):
        kernel = extract_kernel(F90_DIR / "test_kernel_recurrence_ptree",
                                "accumulate")
        with pytest.raises(UnsupportedConstruct, match="not indexed exactly"):
            pointize(kernel)

    def test_dump_lowercases_index_names(self):
        # The fixture spells the recurrence subscript K; the dump must have
        # lowercased it, so the refusal fires on the +1 offset, never on case.
        kernel = extract_kernel(F90_DIR / "test_kernel_recurrence_ptree",
                                "accumulate")
        inner = kernel.body[0].body[0]
        target = inner.body[0].target
        assert target.name == "p"
        assert target.subscripts[0] == Var("i")
        assert target.subscripts[1] == BinOp("add", Var("k"), IntLit("1"))


class TestInlineNestsFixture:
    """Rule B addressing: loop nest #N of a subroutine, by source-order
    ordinal (counting both do-concurrent and plain-DO nests), with the
    generated def's name supplied by the caller."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ptree = F90_DIR / "test_kernel_inline_nests_ptree"

    def test_nest1_do_concurrent(self):
        k = extract_loop_kernel(self.ptree, "two_nests", 1, "scale_branch")
        expected = """\
def scale_branch (a b q : ℝ) : ℝ :=
  q * a
"""
        assert print_kernel(pointize(k)) == expected

    def test_nest2_plain_do(self):
        k = extract_loop_kernel(self.ptree, "two_nests", 2, "shift_branch")
        expected = """\
def shift_branch (a c q : ℝ) : ℝ :=
  a - q
"""
        assert print_kernel(pointize(k)) == expected

    def test_ordinal_addressing_is_deterministic(self):
        for nest, name in ((1, "scale_branch"), (2, "shift_branch")):
            first = print_kernel(pointize(
                extract_loop_kernel(self.ptree, "two_nests", nest, name)))
            second = print_kernel(pointize(
                extract_loop_kernel(self.ptree, "two_nests", nest, name)))
            assert first == second

    def test_out_of_range_ordinal_refused(self):
        with pytest.raises(UnsupportedConstruct, match="has 2 do-construct"):
            extract_loop_kernel(self.ptree, "two_nests", 3, "x")
        with pytest.raises(UnsupportedConstruct, match="has 2 do-construct"):
            extract_loop_kernel(self.ptree, "two_nests", 0, "x")

    def test_whole_subroutine_mode_still_refuses(self):
        # The subroutine's body is an IfConstruct, not a single nest — the
        # unchanged whole-subroutine mode must keep refusing it.
        kernel = extract_kernel(self.ptree, "two_nests")
        with pytest.raises(UnsupportedConstruct, match="exactly one"):
            pointize(kernel)


class TestComponentFixture:
    """Rule B component reads: cfg%fac (loop-invariant scalar) and cfg%w(i)
    (component array at the own index) become synthesized scalar in-params,
    named after the component, appended after the real params in first-use
    order. The collide subroutine pins the naming-collision refusal."""

    def test_printed_lean_with_synthesized_params(self):
        k = extract_kernel(F90_DIR / "test_kernel_component_ptree", "apply_cfg")
        expected = """\
def apply_cfg (a b fac w : ℝ) : ℝ :=
  fac * a + w
"""
        assert print_kernel(pointize(k)) == expected

    def test_synthesized_params_are_in_intent(self):
        pk = pointize(extract_kernel(F90_DIR / "test_kernel_component_ptree",
                                     "apply_cfg"))
        by_name = {p.name: p for p in pk.params}
        assert by_name["fac"].intent == "in" and by_name["w"].intent == "in"

    def test_name_collision_refused(self):
        k = extract_kernel(F90_DIR / "test_kernel_component_ptree", "collide")
        with pytest.raises(UnsupportedConstruct, match="collides"):
            pointize(k)


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


def _plain_do_kernel(*body_stmts, extra_params=()):
    """A `do i = 1, n` kernel over a(:) in / b(:) inout, with a scalar inout s
    and an intent(in) derived cfg available for the refusal shapes."""
    return Kernel(
        name="k",
        params=(Param("a", "real", "in", 1), Param("b", "real", "inout", 1),
                Param("s", "real", "inout", 0),
                Param("cfg", "derived:cfg_t", "in", 0),
                Param("n", "integer", "in", 0)) + tuple(extra_params),
        locals=(Param("i", "integer", None, 0),
                Param("j", "integer", None, 0)),
        body=(Do(("i", IntLit("1"), Var("n")), tuple(body_stmts)),),
    )


class TestPlainDoRefusals:
    """Rule A's write gate and nest-shape gates. Reductions and recurrences
    stay refused: they are not point-local, and their sequential-vs-unordered
    question is real mathematics reserved for a future step."""

    def test_scalar_reduction_refused(self):
        # s = s + a(i): every write must land in the iteration's own cell.
        stmt = Assign(Var("s"), BinOp("add", Var("s"), ArrayRef("a", (Var("i"),))))
        with pytest.raises(UnsupportedConstruct, match="reduction"):
            pointize(_plain_do_kernel(stmt))

    def test_imperfect_nest_refused(self):
        # A statement beside the inner do: not perfectly nested.
        inner = Do(("j", IntLit("1"), Var("n")),
                   (Assign(ArrayRef("b", (Var("j"),)), RealLit("1.0")),))
        beside = Assign(Var("s"), RealLit("0.0"))
        with pytest.raises(UnsupportedConstruct, match="not perfectly nested"):
            pointize(_plain_do_kernel(inner, beside))

    def test_duplicate_loop_index_refused(self):
        k = Kernel(
            "k",
            (Param("b", "real", "inout", 1), Param("n", "integer", "in", 0)),
            (Param("i", "integer", None, 0),),
            (Do(("i", IntLit("1"), Var("n")),
                (Do(("i", IntLit("1"), Var("n")),
                    (Assign(ArrayRef("b", (Var("i"),)), RealLit("1.0")),)),)),),
        )
        with pytest.raises(UnsupportedConstruct, match="duplicate loop index"):
            pointize(k)


class TestComponentRefusals:
    """Rule B: a component read that is neither a loop-invariant scalar nor a
    component array indexed exactly by the loop indices refuses, as do writes
    to components and reads through a base outside the supported shape."""

    def test_offset_component_subscript_refused(self):
        stmt = Assign(ArrayRef("b", (Var("i"),)),
                      ComponentRef("cfg", "w",
                                   (BinOp("add", Var("i"), IntLit("1")),)))
        with pytest.raises(UnsupportedConstruct, match="neither"):
            pointize(_plain_do_kernel(stmt))

    def test_non_intent_in_base_refused(self):
        stmt = Assign(ArrayRef("b", (Var("i"),)), ComponentRef("st", "fac", ()))
        k = _plain_do_kernel(stmt,
                             extra_params=(Param("st", "derived:cfg_t",
                                                 "inout", 0),))
        with pytest.raises(UnsupportedConstruct, match="intent\\(in\\)"):
            pointize(k)

    def test_component_assignment_target_refused(self):
        stmt = Assign(ComponentRef("cfg", "fac", ()), RealLit("1.0"))
        with pytest.raises(UnsupportedConstruct, match="assignment to derived-type"):
            pointize(_plain_do_kernel(stmt))


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
MANIFEST = REPO / "examples" / "turbo-stack.kernels.toml"


@pytest.mark.skipif(not CORPUS, reason="FLINSPECT_CORPUS not set")
def test_generated_lean_is_current():
    """lean/pilot/Pilot/Generated.lean must match a fresh regeneration from
    the committed production manifest — the kernel list and rendering come
    from the same kernel-bank path the CLI runs, so they can't drift apart."""
    from flinspect import kernel_bank
    m = kernel_bank.load_manifest(MANIFEST)
    if not m.fortran.corpus.is_dir():
        pytest.skip("manifest corpus not present")
    text = kernel_bank.render_fortran(m)
    assert text == m.fortran.out.read_text(), \
        ("Generated.lean is stale — rerun `flinspect kernel generate "
         "--kernels examples/turbo-stack.kernels.toml`")


@pytest.mark.skipif(shutil.which("clang++") is None,
                    reason="clang++ not on PATH (source activate_llvm.sh)")
def test_generated_cpp_lean_is_current():
    """lean/pilot/Pilot/GeneratedCpp.lean must match a fresh regeneration —
    the C++ sibling of test_generated_lean_is_current (drift alarm for the
    committed file, the TIM header, AND the pinned clang itself, whose
    version line is stamped into the output)."""
    from flinspect import kernel_bank
    m = kernel_bank.load_manifest(MANIFEST)
    if not all(e.cpp.header.exists() for e in kernel_bank.cpp_entries(m)):
        pytest.skip("TIM kernel headers not present")
    if not all(Path(d).exists() for d in m.cpp.include_dirs):
        pytest.skip("pinned C++ include dirs not present")
    text = kernel_bank.render_cpp(m)
    assert text == m.cpp.out.read_text(), \
        ("GeneratedCpp.lean is stale — rerun `flinspect kernel generate "
         "--kernels examples/turbo-stack.kernels.toml`")
