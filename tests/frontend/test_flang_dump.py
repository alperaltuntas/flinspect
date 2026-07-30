"""Frontend-internal tests for the flang-dump parser.

These reach *below the seam* on purpose: they test how the frontend reads sema's
resolution out of unparse annotations (`demangle`, `call_candidates`, the
recorded `CallEvent`s), its variable tracking, and its scope/visibility-correct
name lookup — implementation details that consumers never see. IR-observable
behaviour (the stratified call relation) is tested in ``tests/test_ir.py``.
"""

import pytest
from pathlib import Path

from flinspect.frontend.flang_dump import ParseTree
from flinspect.frontend._flang_text import (
    node_path, unparse_text, demangle, call_candidates,
)
from flinspect.frontend._nodes import Subroutine
from flinspect.frontend._registry import NodeRegistry


F90_DIR = Path(__file__).parent.parent / "f90"


def parse_all_passes(ptree_path):
    """Parse a single fixture through all recording passes; return (ParseTree, registry)."""
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


# =============================================================================
# with-sema dump line shapes
#
# The fixtures are with-sema dumps, so the matchers must cope with unparse
# annotations. These pin the two line helpers, using real lines from the dump.
# =============================================================================

class TestSemaLineShapes:

    # the same CALL, with and without its unparse annotation
    SEMA_CALL = "| | | | ActionStmt -> CallStmt = 'CALL compute_real(r,1_4)'"
    BARE_CALL = "| | | | ActionStmt -> CallStmt"

    def test_node_path_ignores_unparse_annotation(self):
        assert node_path(self.SEMA_CALL) == self.BARE_CALL
        assert node_path(self.BARE_CALL) == self.BARE_CALL

    def test_node_path_strips_leaf_values_too(self):
        assert node_path("| | Name = 'compute'") == "| | Name"

    def test_unparse_text(self):
        assert unparse_text(self.SEMA_CALL) == "CALL compute_real(r,1_4)"
        assert unparse_text(self.BARE_CALL) is None


# =============================================================================
# Reading sema's resolution out of unparse text (Phase 2, DESIGN Q1/Q2)
# =============================================================================

class TestDemangle:

    def test_plain_name_is_not_mangled(self):
        assert demangle("compute_real") is None

    def test_doubled_module_form(self):
        # the common case: imported through the module that defines it
        assert demangle("mpp_mod$mpp_mod$mpp_error_basic") == (
            "mpp_mod", "mpp_mod", "mpp_error_basic")

    def test_reexport_form_carries_the_defining_module(self):
        # fms_mod re-exports mpp_mod's generic; the specific lives in mpp_mod
        assert demangle("fms_mod$mpp_mod$mpp_error_basic") == (
            "fms_mod", "mpp_mod", "mpp_error_basic")


class TestCallCandidates:

    def test_simple_call(self):
        assert call_candidates("compute_real(r,1_4)") == [(0, False, "compute_real")]

    def test_keyword_arguments_are_not_candidates(self):
        assert call_candidates("mpp_send_int8(ptr,pe,tag=1_4)") == [
            (0, False, "mpp_send_int8")]

    def test_nested_calls_in_order(self):
        cands = call_candidates("outer(inner(x),y(i))")
        assert [c[2] for c in cands] == ["outer", "inner", "y"]
        assert cands[0][0] == 0

    def test_mangled_name(self):
        assert call_candidates("mpp_mod$mpp_mod$mpp_error_basic(2_4,text)") == [
            (0, False, "mpp_mod$mpp_mod$mpp_error_basic")]

    def test_type_bound_call_is_flagged(self):
        cands = call_candidates("time_redux%initialize(dt,out_frequency)")
        assert (11, True, "initialize") in cands

    def test_parenthesis_inside_string_is_not_a_call(self):
        # real corpus shape: a diagnostic message that names a procedure
        text = 'mpp_error_basic(2_4,"deallocate before calling fms_find_my_string(x)")'
        assert [c[2] for c in call_candidates(text)] == ["mpp_error_basic"]

    def test_escaped_quotes_do_not_unbalance_the_string(self):
        text = 'log_it("can""t open f(x)",handler(y))'
        assert [c[2] for c in call_candidates(text)] == ["log_it", "handler"]


# =============================================================================
# CallEvents: what the call pass records (per-call sema text, not per-statement)
# =============================================================================

class TestCallEvents:

    def test_generic_subroutine_calls_carry_the_specific(self):
        pt, _ = parse_all_passes(F90_DIR / "test_interface_basic_ptree")
        # every call is written as the generic `compute` ...
        assert {ev.written_name for ev in pt.call_events} == {"compute"}
        # ... while sema's text names the specific it resolved to
        assert sorted(ev.call_text for ev in pt.call_events) == [
            "CALL compute_int(i,2_4)",
            "CALL compute_logical(flag,.true._4)",
            "CALL compute_real(r,1_4)",
        ]

    def test_function_references_get_their_own_call_text(self):
        # `a = area(y) + area(k)` — one statement, two calls: each event carries
        # the exact resolved text of ITS call (the enclosing Expr annotation),
        # not the shared statement text, so no cross-call attribution is needed.
        pt, _ = parse_all_passes(F90_DIR / "test_generic_function_ptree")
        assert [(ev.written_name, ev.call_text) for ev in pt.call_events] == [
            ("area", "area_r(y)"),
            ("area", "area_i(k)"),
        ]

    def test_type_bound_events_record_the_declared_type(self):
        pt, _ = parse_all_passes(F90_DIR / "test_type_bound_generic_ptree")
        bound = [ev for ev in pt.call_events if ev.is_type_bound]
        assert {ev.bound_type_name for ev in bound} == {"gadget_t"}
        # static dispatch: sema hoists the object and names the specific
        assert sorted(ev.call_text for ev in bound) == [
            "CALL go_i(obj,2_4)",
            "CALL go_r(obj,1._4)",
            "CALL reset_state(obj)",
        ]

    def test_mangled_answer_for_private_specifics(self):
        pt, _ = parse_all_passes(F90_DIR / "test_private_specifics_ptree")
        assert sorted(ev.call_text for ev in pt.call_events) == [
            "CALL priv_mod$priv_mod$compute_i(2_4)",
            "CALL priv_mod$priv_mod$compute_r(1._4)",
        ]


# =============================================================================
# Scope/visibility-correct lookup (W4)
# =============================================================================

class TestVisibility:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.pt, self.nr = parse_all_passes(F90_DIR / "test_private_specifics_ptree")

    def test_access_stmts_recorded(self):
        priv = get_module(self.nr, "priv_mod")
        assert priv.default_access == "private"
        assert priv.access_overrides == {"compute": "public"}

    def test_public_generic_is_visible_through_the_only_list(self):
        caller = get_module(self.nr, "priv_caller_mod")
        found = self.pt.find_named_entity(caller, "compute")
        assert found is not None and found.name == "compute"

    def test_private_specific_is_not_visible_from_the_caller(self):
        caller = get_module(self.nr, "priv_caller_mod")
        assert self.pt.find_named_entity(caller, "compute_r") is None

    def test_private_specific_is_visible_inside_its_own_module(self):
        priv = get_module(self.nr, "priv_mod")
        found = self.pt.find_named_entity(priv, "compute_r")
        assert found is not None and found.name == "compute_r"


class TestUseChainModule:
    """_use_chain_module scope-qualifies unresolved targets (hand-built registry,
    since a with-sema fixture cannot USE a module outside the parsed set)."""

    def setup_method(self):
        self.nr = NodeRegistry()
        self.caller_mod = self.nr.Module("caller_mod")
        self.caller = self.nr.Subroutine("do_work", self.caller_mod)
        self.ext = self.nr.Module("ext_mod")

    def test_only_list_pins_the_module(self):
        self.caller_mod.used_names_lists[self.ext] = ["only_sub"]
        assert ParseTree._use_chain_module(self.caller, "only_sub") == "ext_mod"

    def test_wildcard_pins_nothing(self):
        self.caller_mod.used_names_lists[self.ext] = ["*"]
        assert ParseTree._use_chain_module(self.caller, "only_sub") is None

    def test_rename_pins_through_the_alias(self):
        self.caller_mod.used_names_lists[self.ext] = []
        self.caller_mod.used_renames_lists[self.ext] = [("alias_sub", "real_sub")]
        assert ParseTree._use_chain_module(self.caller, "alias_sub") == "ext_mod"


# =============================================================================
# Variable tracking (kept for `obj%binding()` receiver types and signatures)
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

    def test_derived_type_variable(self):
        pt, nr = parse_all_passes(F90_DIR / "test_type_bound_generic_ptree")
        mod = get_module(nr, "tbp_caller_mod")
        scope_key = Subroutine.key("test_type_bound_calls", mod)
        assert pt.variables[scope_key]["obj"].type == "derived:gadget_t"


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
