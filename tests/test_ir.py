"""IR-level tests for flinspect.

These exercise the *seam*: a frontend extracts an IR from a parse-tree fixture and
we assert on the IR (entities, signatures, relations) — never on flang strings or
frontend internals. Internals (the resolution engine, variable tracking) are tested
separately under ``tests/frontend/``.
"""

import pytest
from pathlib import Path

from flinspect.frontend import FlangDumpFrontend
from flinspect.ir import INTERFACE


F90_DIR = Path(__file__).parent / "f90"


def extract(fixture):
    """Extract an IR from a single parse-tree fixture."""
    path = F90_DIR / fixture
    assert path.exists(), f"Parse tree not found: {path}"
    return FlangDumpFrontend().extract([path])


def get_interface(ir, mod, name):
    for i in ir.interfaces:
        if i.name == name and i.scope == mod:
            return i
    raise ValueError(f"Interface '{name}' not found in module '{mod}'")


def get_subroutine(ir, mod, name):
    for s in ir.subroutines:
        if s.name == name and s.scope == mod:
            return s
    raise ValueError(f"Subroutine '{name}' not found in module '{mod}'")


def get_function(ir, mod, name):
    for f in ir.functions:
        if f.name == name and f.scope == mod:
            return f
    raise ValueError(f"Function '{name}' not found in module '{mod}'")


def member_names(ir, iface):
    return sorted(m.name for m in ir.members(iface.id))


def callee_names(ir, caller, with_interfaces=False):
    return sorted(c.name for c in ir.callees(caller.id)
                  if with_interfaces or c.kind != INTERFACE)


# =============================================================================
# Basic interface resolution by argument type
# =============================================================================

class TestInterfaceBasic:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = extract("test_interface_basic_ptree")

    def test_modules_found(self):
        names = {m.name for m in self.ir.modules}
        assert "interface_basic_mod" in names
        assert "caller_basic_mod" in names

    def test_interface_created(self):
        iface = get_interface(self.ir, "interface_basic_mod", "compute")
        assert member_names(self.ir, iface) == ["compute_int", "compute_logical", "compute_real"]

    def test_procedure_signatures(self):
        compute_real = get_subroutine(self.ir, "interface_basic_mod", "compute_real")
        assert compute_real.signature.arg_types == ("real", "integer")
        assert compute_real.signature.arg_ranks == (0, 0)

        compute_int = get_subroutine(self.ir, "interface_basic_mod", "compute_int")
        assert compute_int.signature.arg_types == ("integer", "integer")

        compute_logical = get_subroutine(self.ir, "interface_basic_mod", "compute_logical")
        assert compute_logical.signature.arg_types == ("logical", "logical")

    def test_all_three_resolved(self):
        caller = get_subroutine(self.ir, "caller_basic_mod", "test_calls")
        callees = callee_names(self.ir, caller)
        assert "compute_real" in callees
        assert "compute_int" in callees
        assert "compute_logical" in callees


# =============================================================================
# Interface resolution by array rank
# =============================================================================

class TestInterfaceRank:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = extract("test_interface_rank_ptree")

    def test_interface_created(self):
        iface = get_interface(self.ir, "interface_rank_mod", "process")
        assert member_names(self.ir, iface) == ["process_1d", "process_2d", "process_3d"]

    def test_procedure_ranks(self):
        assert get_subroutine(self.ir, "interface_rank_mod", "process_1d").signature.arg_ranks[0] == 1
        assert get_subroutine(self.ir, "interface_rank_mod", "process_2d").signature.arg_ranks[0] == 2
        assert get_subroutine(self.ir, "interface_rank_mod", "process_3d").signature.arg_ranks[0] == 3

    def test_calls_resolve_by_rank(self):
        caller = get_subroutine(self.ir, "caller_rank_mod", "test_rank_calls")
        callees = callee_names(self.ir, caller)
        assert "process_1d" in callees
        assert "process_2d" in callees
        assert "process_3d" in callees


# =============================================================================
# Keyword argument matching
# =============================================================================

class TestKeywordArgs:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = extract("test_keyword_args_ptree")

    def test_interface_created(self):
        iface = get_interface(self.ir, "interface_keyword_mod", "transform")
        assert member_names(self.ir, iface) == ["transform_index", "transform_scale"]

    def test_procedure_arg_names(self):
        ts = get_subroutine(self.ir, "interface_keyword_mod", "transform_scale")
        assert ts.signature.arg_names == ("arr", "scale", "offset")
        ti = get_subroutine(self.ir, "interface_keyword_mod", "transform_index")
        assert ti.signature.arg_names == ("arr", "idx", "count")

    def test_keyword_calls_resolve(self):
        caller = get_subroutine(self.ir, "caller_keyword_mod", "test_keyword_calls")
        callees = callee_names(self.ir, caller)
        assert "transform_scale" in callees
        assert "transform_index" in callees


# =============================================================================
# StructureComponent returns unknown type -> conservative fallback
# =============================================================================

class TestStructureComponent:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = extract("test_struct_component_ptree")

    def test_interface_created(self):
        iface = get_interface(self.ir, "struct_comp_mod", "update")
        assert member_names(self.ir, iface) == ["update_int", "update_real"]

    def test_struct_calls_fall_back(self):
        caller = get_subroutine(self.ir, "caller_struct_mod", "test_struct_calls")
        callees = callee_names(self.ir, caller)
        assert "update_real" in callees
        assert "update_int" in callees


# =============================================================================
# Generic FUNCTION reference inside an expression
#
# Every other fixture calls generics through CALL statements; this one is the only
# coverage of the FunctionReference path. Note what sema does here: the dump's
# structure still names the generic (`ProcedureDesignator -> Name = 'area'`) while
# the statement's unparse annotation reads `a=area_r(y)+area_i(k)` — already
# resolved. The frontend's own heuristic is coarser: it treats real and integer as
# mutually compatible, so both specifics show up as callees. Consuming sema's
# resolution instead (and dropping to one edge per reference) is Phase 2.
# =============================================================================

class TestGenericFunction:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = extract("test_generic_function_ptree")

    def test_interface_created(self):
        iface = get_interface(self.ir, "area_mod", "area")
        assert member_names(self.ir, iface) == ["area_i", "area_r"]

    def test_function_signatures(self):
        assert get_function(self.ir, "area_mod", "area_r").signature.arg_types == ("real",)
        assert get_function(self.ir, "area_mod", "area_i").signature.arg_types == ("integer",)

    def test_function_reference_is_a_call(self):
        caller = get_subroutine(self.ir, "caller_area_mod", "test_generic_function_calls")
        callees = callee_names(self.ir, caller)
        assert "area_r" in callees
        assert "area_i" in callees

    def test_generic_recorded_as_callee(self):
        caller = get_subroutine(self.ir, "caller_area_mod", "test_generic_function_calls")
        assert "area" in callee_names(self.ir, caller, with_interfaces=True)


# =============================================================================
# Rank reduction by scalar subscript in an actual argument
#
# Named for flang's habit of parsing `fields(i)` as a FunctionReference; in this
# fixture flang (either dump variant) resolves it to an ArrayElement, so what is
# actually covered here is rank reduction by a scalar subscript — `fields(i,:,:)`
# passed to a 2-d specific. Genuine FunctionReference coverage is
# TestGenericFunction above.
# =============================================================================

class TestFunctionReferenceArray:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = extract("test_func_ref_array_ptree")

    def test_interface_created(self):
        iface = get_interface(self.ir, "func_ref_mod", "send_data")
        assert member_names(self.ir, iface) == ["send_data_2d", "send_data_3d"]

    def test_direct_3d_call_resolves(self):
        caller = get_subroutine(self.ir, "caller_func_ref_mod", "test_func_ref_calls")
        assert "send_data_3d" in callee_names(self.ir, caller)

    def test_subscripted_call_resolves_to_2d(self):
        caller = get_subroutine(self.ir, "caller_func_ref_mod", "test_func_ref_calls")
        assert "send_data_2d" in callee_names(self.ir, caller)


# =============================================================================
# AssumedShapeSpec with explicit lower bounds (call-resolution side)
# =============================================================================

class TestAssumedShape:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = extract("test_assumed_shape_ptree")

    def test_interface_created(self):
        iface = get_interface(self.ir, "assumed_shape_mod", "fill_data")
        assert member_names(self.ir, iface) == ["fill_data_1d", "fill_data_2d", "fill_data_3d"]

    def test_1d_call_resolves(self):
        caller = get_subroutine(self.ir, "caller_assumed_mod", "test_assumed_calls")
        assert "fill_data_1d" in callee_names(self.ir, caller)

    def test_2d_call_resolves(self):
        caller = get_subroutine(self.ir, "caller_assumed_mod", "test_assumed_calls")
        assert "fill_data_2d" in callee_names(self.ir, caller)

    def test_no_3d_call(self):
        caller = get_subroutine(self.ir, "caller_assumed_mod", "test_assumed_calls")
        assert "fill_data_3d" not in callee_names(self.ir, caller)


# =============================================================================
# Optional arguments and argument count matching
#
# The fixture's two specifics differ in their first argument's type — `init` would
# otherwise be an ambiguous generic, which sema rejects outright (Phase 1b: the
# fixture only ever compiled under -no-sema). The 3-/4-argument and keyword calls
# therefore still exercise argument-count and keyword matching against the optional
# dummies, while the 2-argument call exercises the fan-out below.
# =============================================================================

class TestOptionalArgs:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = extract("test_optional_args_ptree")

    def test_interface_created(self):
        iface = get_interface(self.ir, "optional_args_mod", "init")
        assert member_names(self.ir, iface) == ["init_advanced", "init_simple"]

    def test_simple_signature(self):
        sub = get_subroutine(self.ir, "optional_args_mod", "init_simple")
        assert sub.signature.num_args == 2
        assert sub.signature.num_required == 2

    def test_advanced_signature(self):
        sub = get_subroutine(self.ir, "optional_args_mod", "init_advanced")
        assert sub.signature.num_args == 4
        assert sub.signature.num_required == 2

    def test_2arg_call_matches_both(self):
        caller = get_subroutine(self.ir, "caller_optional_mod", "test_optional_calls")
        callees = callee_names(self.ir, caller)
        assert "init_simple" in callees
        assert "init_advanced" in callees

    def test_keyword_optional_resolves(self):
        caller = get_subroutine(self.ir, "caller_optional_mod", "test_optional_calls")
        assert "init_advanced" in callee_names(self.ir, caller)
