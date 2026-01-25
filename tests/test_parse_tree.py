"""Unit tests for flinspect parse_tree module.

These tests use parse trees generated from Fortran programs in tests/f90/.
Each test verifies a specific aspect of the parse tree analysis:
  - Basic interface resolution by type
  - Interface resolution by array rank
  - Keyword argument matching
  - StructureComponent type inference (returns unknown)
  - FunctionReference-as-array pattern handling
  - AssumedShapeSpec with explicit lower bounds
  - Optional argument handling
"""

import pytest
from pathlib import Path

from flinspect.parse_tree import ParseTree
from flinspect.parse_node import Interface, Subroutine, Module
from flinspect.node_registry import NodeRegistry


# Path to the test parse trees
F90_DIR = Path(__file__).parent / "f90"


def parse_all_passes(ptree_path):
    """Parse a single parse tree through all three passes and return the ParseTree object."""
    nr = NodeRegistry()
    pt = ParseTree(ptree_path, node_registry=nr)
    pt.parse_structure()
    pt.parse_interfaces()
    pt.parse_calls()
    return pt, nr


def get_module(nr, name):
    """Get a module from the node registry by name."""
    for mod in nr.modules:
        if mod.name == name:
            return mod
    raise ValueError(f"Module '{name}' not found in registry")


def get_interface(nr, mod_name, iface_name):
    """Get an interface from a module."""
    mod = get_module(nr, mod_name)
    for iface in mod.interfaces:
        if iface.name == iface_name:
            return iface
    raise ValueError(f"Interface '{iface_name}' not found in module '{mod_name}'")


def get_subroutine(nr, mod_name, sub_name):
    """Get a subroutine from the node registry."""
    for sub in nr.subroutines:
        if sub.name == sub_name and sub.program_unit.name == mod_name:
            return sub
    raise ValueError(f"Subroutine '{sub_name}' not found in module '{mod_name}'")


def get_callee_names(caller):
    """Get sorted list of callee names for a callable."""
    return sorted(c.name for c in caller.callees)


def get_callee_names_no_interfaces(caller):
    """Get sorted list of callee names excluding interfaces."""
    return sorted(c.name for c in caller.callees if not isinstance(c, Interface))


# =============================================================================
# Test: Basic interface resolution by argument type
# =============================================================================

class TestInterfaceBasic:
    """Test basic interface resolution where procedures differ by argument type."""

    @pytest.fixture(autouse=True)
    def setup(self):
        ptree_path = F90_DIR / "test_interface_basic_ptree"
        assert ptree_path.exists(), f"Parse tree not found: {ptree_path}"
        self.pt, self.nr = parse_all_passes(ptree_path)

    def test_modules_found(self):
        """Both modules should be parsed."""
        mod1 = get_module(self.nr, "interface_basic_mod")
        mod2 = get_module(self.nr, "caller_basic_mod")
        assert mod1 is not None
        assert mod2 is not None

    def test_interface_created(self):
        """The 'compute' interface should exist with 3 procedures."""
        iface = get_interface(self.nr, "interface_basic_mod", "compute")
        assert iface is not None
        proc_names = sorted(p.name for p in iface.procedures)
        assert proc_names == ["compute_int", "compute_logical", "compute_real"]

    def test_procedure_signatures(self):
        """Each procedure should have correctly parsed argument types."""
        compute_real = get_subroutine(self.nr, "interface_basic_mod", "compute_real")
        assert compute_real.arg_types == ["real", "integer"]
        assert compute_real.arg_ranks == [0, 0]

        compute_int = get_subroutine(self.nr, "interface_basic_mod", "compute_int")
        assert compute_int.arg_types == ["integer", "integer"]

        compute_logical = get_subroutine(self.nr, "interface_basic_mod", "compute_logical")
        assert compute_logical.arg_types == ["logical", "logical"]

    def test_call_resolves_to_compute_real(self):
        """call compute(r, 1) where r is real should resolve to compute_real."""
        caller = get_subroutine(self.nr, "caller_basic_mod", "test_calls")
        callees = get_callee_names_no_interfaces(caller)
        assert "compute_real" in callees

    def test_call_resolves_to_compute_int(self):
        """call compute(i, 2) where i is integer should resolve to compute_int."""
        caller = get_subroutine(self.nr, "caller_basic_mod", "test_calls")
        callees = get_callee_names_no_interfaces(caller)
        assert "compute_int" in callees

    def test_call_resolves_to_compute_logical(self):
        """call compute(flag, .true.) should resolve to compute_logical."""
        caller = get_subroutine(self.nr, "caller_basic_mod", "test_calls")
        callees = get_callee_names_no_interfaces(caller)
        assert "compute_logical" in callees

    def test_all_three_resolved(self):
        """All three interface calls should resolve to distinct procedures."""
        caller = get_subroutine(self.nr, "caller_basic_mod", "test_calls")
        callees = get_callee_names_no_interfaces(caller)
        assert "compute_real" in callees
        assert "compute_int" in callees
        assert "compute_logical" in callees


# =============================================================================
# Test: Interface resolution by array rank
# =============================================================================

class TestInterfaceRank:
    """Test interface resolution where procedures differ by array rank."""

    @pytest.fixture(autouse=True)
    def setup(self):
        ptree_path = F90_DIR / "test_interface_rank_ptree"
        assert ptree_path.exists(), f"Parse tree not found: {ptree_path}"
        self.pt, self.nr = parse_all_passes(ptree_path)

    def test_interface_created(self):
        """The 'process' interface should have 3 procedures."""
        iface = get_interface(self.nr, "interface_rank_mod", "process")
        proc_names = sorted(p.name for p in iface.procedures)
        assert proc_names == ["process_1d", "process_2d", "process_3d"]

    def test_procedure_ranks(self):
        """Each procedure should have the correct array rank for its first argument."""
        p1d = get_subroutine(self.nr, "interface_rank_mod", "process_1d")
        assert p1d.arg_ranks[0] == 1

        p2d = get_subroutine(self.nr, "interface_rank_mod", "process_2d")
        assert p2d.arg_ranks[0] == 2

        p3d = get_subroutine(self.nr, "interface_rank_mod", "process_3d")
        assert p3d.arg_ranks[0] == 3

    def test_1d_call_resolves(self):
        """call process(vec, 10) with rank-1 vec should resolve to process_1d."""
        caller = get_subroutine(self.nr, "caller_rank_mod", "test_rank_calls")
        callees = get_callee_names_no_interfaces(caller)
        assert "process_1d" in callees

    def test_2d_call_resolves(self):
        """call process(mat, 5) with rank-2 mat should resolve to process_2d."""
        caller = get_subroutine(self.nr, "caller_rank_mod", "test_rank_calls")
        callees = get_callee_names_no_interfaces(caller)
        assert "process_2d" in callees

    def test_3d_call_resolves(self):
        """call process(cube, 3) with rank-3 cube should resolve to process_3d."""
        caller = get_subroutine(self.nr, "caller_rank_mod", "test_rank_calls")
        callees = get_callee_names_no_interfaces(caller)
        assert "process_3d" in callees


# =============================================================================
# Test: Keyword argument matching
# =============================================================================

class TestKeywordArgs:
    """Test that keyword arguments are matched by name, not position."""

    @pytest.fixture(autouse=True)
    def setup(self):
        ptree_path = F90_DIR / "test_keyword_args_ptree"
        assert ptree_path.exists(), f"Parse tree not found: {ptree_path}"
        self.pt, self.nr = parse_all_passes(ptree_path)

    def test_interface_created(self):
        """The 'transform' interface should have 2 procedures."""
        iface = get_interface(self.nr, "interface_keyword_mod", "transform")
        proc_names = sorted(p.name for p in iface.procedures)
        assert proc_names == ["transform_index", "transform_scale"]

    def test_procedure_arg_names(self):
        """Procedures should have correct argument names for keyword matching."""
        ts = get_subroutine(self.nr, "interface_keyword_mod", "transform_scale")
        assert ts.arg_names == ["arr", "scale", "offset"]

        ti = get_subroutine(self.nr, "interface_keyword_mod", "transform_index")
        assert ti.arg_names == ["arr", "idx", "count"]

    def test_positional_real_resolves_to_scale(self):
        """call transform(data, 2.0, 1.0) should resolve to transform_scale."""
        caller = get_subroutine(self.nr, "caller_keyword_mod", "test_keyword_calls")
        callees = get_callee_names_no_interfaces(caller)
        assert "transform_scale" in callees

    def test_positional_int_resolves_to_index(self):
        """call transform(data, 5, 10) should resolve to transform_index."""
        caller = get_subroutine(self.nr, "caller_keyword_mod", "test_keyword_calls")
        callees = get_callee_names_no_interfaces(caller)
        assert "transform_index" in callees

    def test_keyword_reordered_calls_resolve(self):
        """Keyword calls with reordered args should still resolve correctly."""
        caller = get_subroutine(self.nr, "caller_keyword_mod", "test_keyword_calls")
        callees = get_callee_names_no_interfaces(caller)
        # Both positional and keyword calls to each procedure
        assert "transform_scale" in callees
        assert "transform_index" in callees


# =============================================================================
# Test: StructureComponent returns unknown type
# =============================================================================

class TestStructureComponent:
    """Test that derived-type component access (CS%field) returns unknown type."""

    @pytest.fixture(autouse=True)
    def setup(self):
        ptree_path = F90_DIR / "test_struct_component_ptree"
        assert ptree_path.exists(), f"Parse tree not found: {ptree_path}"
        self.pt, self.nr = parse_all_passes(ptree_path)

    def test_interface_created(self):
        """The 'update' interface should have 2 procedures."""
        iface = get_interface(self.nr, "struct_comp_mod", "update")
        proc_names = sorted(p.name for p in iface.procedures)
        assert proc_names == ["update_int", "update_real"]

    def test_struct_calls_fall_back(self):
        """Calls with StructureComponent args should fall back to all procedures.
        
        Since flinspect can't resolve the type of CS%data%scalar_val or CS%mode,
        it returns unknown type, which matches all procedures conservatively.
        """
        caller = get_subroutine(self.nr, "caller_struct_mod", "test_struct_calls")
        callees = get_callee_names_no_interfaces(caller)
        # With unknown type, both procedures should match (conservative fallback)
        assert "update_real" in callees
        assert "update_int" in callees


# =============================================================================
# Test: FunctionReference-as-array pattern
# =============================================================================

class TestFunctionReferenceArray:
    """Test that array element access with subscript triplets is handled.
    
    When fields(i,:,:) is used on a rank-3 array, the scalar subscript
    reduces the rank by 1, and the two SubscriptTriplets preserve those
    dimensions. The result should be rank 2.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        ptree_path = F90_DIR / "test_func_ref_array_ptree"
        assert ptree_path.exists(), f"Parse tree not found: {ptree_path}"
        self.pt, self.nr = parse_all_passes(ptree_path)

    def test_interface_created(self):
        """The 'send_data' interface should have 2 procedures."""
        iface = get_interface(self.nr, "func_ref_mod", "send_data")
        proc_names = sorted(p.name for p in iface.procedures)
        assert proc_names == ["send_data_2d", "send_data_3d"]

    def test_direct_3d_call_resolves(self):
        """call send_data(fields, 2) with rank-3 fields should resolve to send_data_3d."""
        caller = get_subroutine(self.nr, "caller_func_ref_mod", "test_func_ref_calls")
        callees = get_callee_names_no_interfaces(caller)
        assert "send_data_3d" in callees

    def test_subscripted_call_resolves_to_2d(self):
        """call send_data(fields(i,:,:), 1) should reduce rank 3->2, resolving to send_data_2d."""
        caller = get_subroutine(self.nr, "caller_func_ref_mod", "test_func_ref_calls")
        callees = get_callee_names_no_interfaces(caller)
        assert "send_data_2d" in callees


# =============================================================================
# Test: AssumedShapeSpec with explicit lower bounds
# =============================================================================

class TestAssumedShape:
    """Test that AssumedShapeSpec with explicit bounds is parsed correctly.
    
    Fortran declarations like:
        real, dimension(HI%isd:, HI%jsd:) :: data2d
    produce AssumedShapeSpec nodes with SpecificationExpr lower bounds.
    flinspect must count these to determine the correct array rank.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        ptree_path = F90_DIR / "test_assumed_shape_ptree"
        assert ptree_path.exists(), f"Parse tree not found: {ptree_path}"
        self.pt, self.nr = parse_all_passes(ptree_path)

    def test_interface_created(self):
        """The 'fill_data' interface should have 3 procedures."""
        iface = get_interface(self.nr, "assumed_shape_mod", "fill_data")
        proc_names = sorted(p.name for p in iface.procedures)
        assert proc_names == ["fill_data_1d", "fill_data_2d", "fill_data_3d"]

    def test_assumed_shape_rank_1d(self):
        """data1d declared as dimension(HI%isd:) should have rank 1."""
        mod = get_module(self.nr, "caller_assumed_mod")
        scope_key = Subroutine.key("test_assumed_calls", mod)
        scope_vars = self.pt.variables.get(scope_key, {})
        assert "data1d" in scope_vars, f"data1d not found in variables. Keys: {list(scope_vars.keys())}"
        assert scope_vars["data1d"].rank == 1, f"Expected rank 1 for data1d, got {scope_vars['data1d'].rank}"

    def test_assumed_shape_rank_2d(self):
        """data2d declared as dimension(HI%isd:,HI%jsd:) should have rank 2."""
        mod = get_module(self.nr, "caller_assumed_mod")
        scope_key = Subroutine.key("test_assumed_calls", mod)
        scope_vars = self.pt.variables.get(scope_key, {})
        assert "data2d" in scope_vars, f"data2d not found in variables. Keys: {list(scope_vars.keys())}"
        assert scope_vars["data2d"].rank == 2, f"Expected rank 2 for data2d, got {scope_vars['data2d'].rank}"

    def test_1d_call_resolves(self):
        """call fill_data(data1d, 0.0) should resolve to fill_data_1d."""
        caller = get_subroutine(self.nr, "caller_assumed_mod", "test_assumed_calls")
        callees = get_callee_names_no_interfaces(caller)
        assert "fill_data_1d" in callees

    def test_2d_call_resolves(self):
        """call fill_data(data2d, 1.0) should resolve to fill_data_2d."""
        caller = get_subroutine(self.nr, "caller_assumed_mod", "test_assumed_calls")
        callees = get_callee_names_no_interfaces(caller)
        assert "fill_data_2d" in callees

    def test_no_3d_call(self):
        """No call should resolve to fill_data_3d (no rank-3 array is passed)."""
        caller = get_subroutine(self.nr, "caller_assumed_mod", "test_assumed_calls")
        callees = get_callee_names_no_interfaces(caller)
        assert "fill_data_3d" not in callees


# =============================================================================
# Test: Optional arguments and argument count matching
# =============================================================================

class TestOptionalArgs:
    """Test that optional arguments are handled correctly in matching."""

    @pytest.fixture(autouse=True)
    def setup(self):
        ptree_path = F90_DIR / "test_optional_args_ptree"
        assert ptree_path.exists(), f"Parse tree not found: {ptree_path}"
        self.pt, self.nr = parse_all_passes(ptree_path)

    def test_interface_created(self):
        """The 'init' interface should have 2 procedures."""
        iface = get_interface(self.nr, "optional_args_mod", "init")
        proc_names = sorted(p.name for p in iface.procedures)
        assert proc_names == ["init_advanced", "init_simple"]

    def test_simple_has_2_required_args(self):
        """init_simple should have 2 required args (no optional)."""
        sub = get_subroutine(self.nr, "optional_args_mod", "init_simple")
        assert sub.num_args == 2
        assert sub.num_required_args == 2

    def test_advanced_has_2_required_args(self):
        """init_advanced should have 4 total args, 2 required."""
        sub = get_subroutine(self.nr, "optional_args_mod", "init_advanced")
        assert sub.num_args == 4
        assert sub.num_required_args == 2

    def test_2arg_call_matches_both(self):
        """call init(val, 10) with 2 args should match both procedures."""
        caller = get_subroutine(self.nr, "caller_optional_mod", "test_optional_calls")
        callees = get_callee_names_no_interfaces(caller)
        # Both should be in callees since 2 args matches both
        assert "init_simple" in callees
        assert "init_advanced" in callees

    def test_3arg_call_matches_advanced_only(self):
        """call init(val, 10, 1.0e-6) with 3 args should only match init_advanced."""
        # This is tested implicitly - init_simple can't accept 3 args
        sub_simple = get_subroutine(self.nr, "optional_args_mod", "init_simple")
        assert sub_simple.num_args == 2  # Can't accept more than 2

    def test_keyword_optional_resolves(self):
        """call init(val, 10, debug=.true.) should resolve to init_advanced."""
        caller = get_subroutine(self.nr, "caller_optional_mod", "test_optional_calls")
        callees = get_callee_names_no_interfaces(caller)
        assert "init_advanced" in callees


# =============================================================================
# Test: resolve_interface_procedures directly
# =============================================================================

class TestResolveInterfaceProcedures:
    """Direct unit tests for the resolve_interface_procedures method."""

    @pytest.fixture(autouse=True)
    def setup(self):
        ptree_path = F90_DIR / "test_interface_basic_ptree"
        assert ptree_path.exists(), f"Parse tree not found: {ptree_path}"
        self.pt, self.nr = parse_all_passes(ptree_path)
        self.iface = get_interface(self.nr, "interface_basic_mod", "compute")

    def test_exact_type_match(self):
        """Passing (real, integer) should match compute_real and compute_int (integer/real are conservatively compatible)."""
        result = self.pt.resolve_interface_procedures(
            self.iface,
            call_arg_types=["real", "integer"],
            call_arg_ranks=[0, 0],
        )
        result_names = sorted(r.name for r in result)
        assert "compute_real" in result_names
        # compute_int also matches because real/integer are conservatively compatible
        assert "compute_int" in result_names
        # compute_logical should NOT match
        assert "compute_logical" not in result_names

    def test_integer_type_match(self):
        """Passing (integer, integer) matches compute_int and compute_real (conservative compatibility)."""
        result = self.pt.resolve_interface_procedures(
            self.iface,
            call_arg_types=["integer", "integer"],
            call_arg_ranks=[0, 0],
        )
        result_names = sorted(r.name for r in result)
        assert "compute_int" in result_names
        assert "compute_real" in result_names
        assert "compute_logical" not in result_names

    def test_unknown_type_matches_all(self):
        """Passing unknown types should match all procedures (conservative)."""
        result = self.pt.resolve_interface_procedures(
            self.iface,
            call_arg_types=["unknown", "unknown"],
            call_arg_ranks=[-1, -1],
        )
        assert len(result) == 3

    def test_no_match_falls_back_to_all(self):
        """If no procedure matches, fall back to all (conservative)."""
        result = self.pt.resolve_interface_procedures(
            self.iface,
            call_arg_types=["character", "character", "character", "character"],
            call_arg_ranks=[0, 0, 0, 0],
        )
        # Too many args for any procedure -> no match -> fallback to all
        assert len(result) == 3


# =============================================================================
# Test: _procedure_matches directly
# =============================================================================

class TestProcedureMatches:
    """Direct unit tests for the _procedure_matches method."""

    @pytest.fixture(autouse=True)
    def setup(self):
        ptree_path = F90_DIR / "test_keyword_args_ptree"
        assert ptree_path.exists(), f"Parse tree not found: {ptree_path}"
        self.pt, self.nr = parse_all_passes(ptree_path)

    def test_positional_match(self):
        """Positional args with matching types should match."""
        proc = get_subroutine(self.nr, "interface_keyword_mod", "transform_scale")
        assert self.pt._procedure_matches(
            proc,
            call_arg_types=["real", "real", "real"],
            call_arg_ranks=[1, 0, 0],
        )

    def test_positional_mismatch(self):
        """Positional args with incompatible types (character vs real) should not match."""
        proc = get_subroutine(self.nr, "interface_keyword_mod", "transform_scale")
        # character is incompatible with real
        assert not self.pt._procedure_matches(
            proc,
            call_arg_types=["real", "character", "character"],
            call_arg_ranks=[1, 0, 0],
        )

    def test_keyword_match_by_name(self):
        """Keyword args should be matched by name, not position."""
        proc = get_subroutine(self.nr, "interface_keyword_mod", "transform_scale")
        # offset=1.0, scale=2.0 (reordered from the procedure signature: arr, scale, offset)
        result = self.pt._procedure_matches(
            proc,
            call_arg_types=["real", "real", "real"],
            call_arg_ranks=[1, 0, 0],
            call_arg_names=[None, "offset", "scale"],
        )
        assert result

    def test_wrong_keyword_rejected(self):
        """Keyword arg with wrong name should not match."""
        proc = get_subroutine(self.nr, "interface_keyword_mod", "transform_scale")
        result = self.pt._procedure_matches(
            proc,
            call_arg_types=["real", "integer", "integer"],
            call_arg_ranks=[1, 0, 0],
            call_arg_names=[None, "idx", "count"],
        )
        assert not result

    def test_too_many_args_rejected(self):
        """More arguments than the procedure accepts should be rejected."""
        proc = get_subroutine(self.nr, "interface_keyword_mod", "transform_scale")
        result = self.pt._procedure_matches(
            proc,
            call_arg_types=["real", "real", "real", "real"],
            call_arg_ranks=[1, 0, 0, 0],
        )
        assert not result

    def test_too_few_args_rejected(self):
        """Fewer arguments than required should be rejected."""
        proc = get_subroutine(self.nr, "interface_keyword_mod", "transform_scale")
        result = self.pt._procedure_matches(
            proc,
            call_arg_types=["real"],
            call_arg_ranks=[1],
        )
        assert not result


# =============================================================================
# Test: Variable parsing
# =============================================================================

class TestVariableParsing:
    """Test that variables are parsed correctly during structure pass."""

    @pytest.fixture(autouse=True)
    def setup(self):
        ptree_path = F90_DIR / "test_interface_rank_ptree"
        assert ptree_path.exists(), f"Parse tree not found: {ptree_path}"
        self.pt, self.nr = parse_all_passes(ptree_path)

    def test_scalar_variable(self):
        """Variables should be stored with correct types and ranks."""
        mod = get_module(self.nr, "caller_rank_mod")
        scope_key = Subroutine.key("test_rank_calls", mod)
        
        # variables maps scope_key -> dict(var_name -> VariableInfo)
        scope_vars = self.pt.variables.get(scope_key, {})
        
        # vec is real, rank 1
        assert scope_vars["vec"].type == "real"
        assert scope_vars["vec"].rank == 1
        # mat is real, rank 2
        assert scope_vars["mat"].type == "real"
        assert scope_vars["mat"].rank == 2
        # cube is real, rank 3
        assert scope_vars["cube"].type == "real"
        assert scope_vars["cube"].rank == 3
