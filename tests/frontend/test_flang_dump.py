"""Frontend-internal tests for the flang-dump parser.

These reach *below the seam* on purpose: they test the flang-dump frontend's
resolution engine (``resolve_interface_procedures``, ``_procedure_matches``), its
variable tracking, and its handling of the with-sema dump's line shapes —
implementation details that consumers never see. IR-observable behaviour is tested
in ``tests/test_ir.py``.
"""

import pytest
from pathlib import Path

from flinspect.frontend.flang_dump import ParseTree
from flinspect.frontend._flang_text import (
    node_path, unparse_text, splice_annotated_child,
)
from flinspect.frontend._nodes import Interface, Subroutine, Module
from flinspect.frontend._registry import NodeRegistry


F90_DIR = Path(__file__).parent.parent / "f90"


def parse_all_passes(ptree_path):
    """Parse a single fixture through all three passes; return (ParseTree, registry)."""
    nr = NodeRegistry()
    pt = ParseTree(ptree_path, node_registry=nr)
    pt.parse_structure()
    pt.parse_interfaces()
    pt.parse_calls()
    return pt, nr


def get_module(nr, name):
    for mod in nr.modules:
        if mod.name == name:
            return mod
    raise ValueError(f"Module '{name}' not found in registry")


def get_interface(nr, mod_name, iface_name):
    mod = get_module(nr, mod_name)
    for iface in mod.interfaces:
        if iface.name == iface_name:
            return iface
    raise ValueError(f"Interface '{iface_name}' not found in module '{mod_name}'")


def get_subroutine(nr, mod_name, sub_name):
    for sub in nr.subroutines:
        if sub.name == sub_name and sub.program_unit.name == mod_name:
            return sub
    raise ValueError(f"Subroutine '{sub_name}' not found in module '{mod_name}'")


# =============================================================================
# resolve_interface_procedures
# =============================================================================

class TestResolveInterfaceProcedures:

    @pytest.fixture(autouse=True)
    def setup(self):
        ptree_path = F90_DIR / "test_interface_basic_ptree"
        assert ptree_path.exists(), f"Parse tree not found: {ptree_path}"
        self.pt, self.nr = parse_all_passes(ptree_path)
        self.iface = get_interface(self.nr, "interface_basic_mod", "compute")

    def test_exact_type_match(self):
        result = self.pt.resolve_interface_procedures(
            self.iface, call_arg_types=["real", "integer"], call_arg_ranks=[0, 0],
        )
        names = sorted(r.name for r in result)
        assert "compute_real" in names
        assert "compute_int" in names
        assert "compute_logical" not in names

    def test_integer_type_match(self):
        result = self.pt.resolve_interface_procedures(
            self.iface, call_arg_types=["integer", "integer"], call_arg_ranks=[0, 0],
        )
        names = sorted(r.name for r in result)
        assert "compute_int" in names
        assert "compute_real" in names
        assert "compute_logical" not in names

    def test_unknown_type_matches_all(self):
        result = self.pt.resolve_interface_procedures(
            self.iface, call_arg_types=["unknown", "unknown"], call_arg_ranks=[-1, -1],
        )
        assert len(result) == 3

    def test_no_match_falls_back_to_all(self):
        result = self.pt.resolve_interface_procedures(
            self.iface,
            call_arg_types=["character", "character", "character", "character"],
            call_arg_ranks=[0, 0, 0, 0],
        )
        assert len(result) == 3


# =============================================================================
# _procedure_matches
# =============================================================================

class TestProcedureMatches:

    @pytest.fixture(autouse=True)
    def setup(self):
        ptree_path = F90_DIR / "test_keyword_args_ptree"
        assert ptree_path.exists(), f"Parse tree not found: {ptree_path}"
        self.pt, self.nr = parse_all_passes(ptree_path)

    def test_positional_match(self):
        proc = get_subroutine(self.nr, "interface_keyword_mod", "transform_scale")
        assert self.pt._procedure_matches(
            proc, call_arg_types=["real", "real", "real"], call_arg_ranks=[1, 0, 0],
        )

    def test_positional_mismatch(self):
        proc = get_subroutine(self.nr, "interface_keyword_mod", "transform_scale")
        assert not self.pt._procedure_matches(
            proc, call_arg_types=["real", "character", "character"], call_arg_ranks=[1, 0, 0],
        )

    def test_keyword_match_by_name(self):
        proc = get_subroutine(self.nr, "interface_keyword_mod", "transform_scale")
        assert self.pt._procedure_matches(
            proc, call_arg_types=["real", "real", "real"], call_arg_ranks=[1, 0, 0],
            call_arg_names=[None, "offset", "scale"],
        )

    def test_wrong_keyword_rejected(self):
        proc = get_subroutine(self.nr, "interface_keyword_mod", "transform_scale")
        assert not self.pt._procedure_matches(
            proc, call_arg_types=["real", "integer", "integer"], call_arg_ranks=[1, 0, 0],
            call_arg_names=[None, "idx", "count"],
        )

    def test_too_many_args_rejected(self):
        proc = get_subroutine(self.nr, "interface_keyword_mod", "transform_scale")
        assert not self.pt._procedure_matches(
            proc, call_arg_types=["real", "real", "real", "real"], call_arg_ranks=[1, 0, 0, 0],
        )

    def test_too_few_args_rejected(self):
        proc = get_subroutine(self.nr, "interface_keyword_mod", "transform_scale")
        assert not self.pt._procedure_matches(
            proc, call_arg_types=["real"], call_arg_ranks=[1],
        )


# =============================================================================
# Variable tracking
# =============================================================================

class TestVariableParsing:

    @pytest.fixture(autouse=True)
    def setup(self):
        ptree_path = F90_DIR / "test_interface_rank_ptree"
        assert ptree_path.exists(), f"Parse tree not found: {ptree_path}"
        self.pt, self.nr = parse_all_passes(ptree_path)

    def test_scalar_variable(self):
        mod = get_module(self.nr, "caller_rank_mod")
        scope_key = Subroutine.key("test_rank_calls", mod)
        scope_vars = self.pt.variables.get(scope_key, {})
        assert scope_vars["vec"].type == "real"
        assert scope_vars["vec"].rank == 1
        assert scope_vars["mat"].type == "real"
        assert scope_vars["mat"].rank == 2
        assert scope_vars["cube"].type == "real"
        assert scope_vars["cube"].rank == 3


class TestAssumedShapeVariables:

    @pytest.fixture(autouse=True)
    def setup(self):
        ptree_path = F90_DIR / "test_assumed_shape_ptree"
        assert ptree_path.exists(), f"Parse tree not found: {ptree_path}"
        self.pt, self.nr = parse_all_passes(ptree_path)

    def test_assumed_shape_rank_1d(self):
        mod = get_module(self.nr, "caller_assumed_mod")
        scope_key = Subroutine.key("test_assumed_calls", mod)
        scope_vars = self.pt.variables.get(scope_key, {})
        assert scope_vars["data1d"].rank == 1

    def test_assumed_shape_rank_2d(self):
        mod = get_module(self.nr, "caller_assumed_mod")
        scope_key = Subroutine.key("test_assumed_calls", mod)
        scope_vars = self.pt.variables.get(scope_key, {})
        assert scope_vars["data2d"].rank == 2


# =============================================================================
# with-sema dump line shapes (Phase 1b)
#
# The fixtures are with-sema dumps, so the matchers must cope with unparse
# annotations and the extra `Expr` nesting they introduce. These pin the two
# helpers that absorb the difference, using real lines from both dump variants.
# =============================================================================

class TestSemaLineShapes:

    # the same CALL, as each dump variant renders it
    SEMA_CALL = "| | | | ActionStmt -> CallStmt = 'CALL compute_real(r,1_4)'"
    NOSEMA_CALL = "| | | | ActionStmt -> CallStmt"

    def test_node_path_ignores_unparse_annotation(self):
        assert node_path(self.SEMA_CALL) == self.NOSEMA_CALL
        assert node_path(self.NOSEMA_CALL) == self.NOSEMA_CALL

    def test_node_path_strips_leaf_values_too(self):
        assert node_path("| | Name = 'compute'") == "| | Name"

    def test_unparse_text(self):
        assert unparse_text(self.SEMA_CALL) == "CALL compute_real(r,1_4)"
        assert unparse_text(self.NOSEMA_CALL) is None

    def test_splice_reproduces_the_nosema_line(self):
        # An annotated Expr pushes its structure one level down; splicing the two
        # back together must yield exactly what -no-sema would have emitted.
        sema_expr = "| | | | | | | ActualArg -> Expr = '1_4'"
        sema_child = "| | | | | | | | LiteralConstant -> IntLiteralConstant = '1'"
        assert splice_annotated_child(sema_expr, sema_child) == (
            "| | | | | | | ActualArg -> Expr -> LiteralConstant -> IntLiteralConstant = '1'"
        )

    def test_expr_structure_line_collapses_annotated_expr(self):
        lines = [
            "| | | | | | | ActualArg -> Expr = 'j+1_4'",
            "| | | | | | | | Add",
            "| | | | | | | | | Expr = 'j'",
        ]
        # the operator sits on the child line, so type inference only sees it
        # after the splice
        assert ParseTree._expr_structure_line(lines, 0).endswith("Expr -> Add")

    def test_expr_structure_line_passes_nosema_through(self):
        lines = ["| | | ActualArg -> Expr -> LiteralConstant -> IntLiteralConstant = '1'"]
        assert ParseTree._expr_structure_line(lines, 0) == lines[0]

