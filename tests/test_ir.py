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
# Confidence strata: the may/must lattice views (D3)
# =============================================================================

class TestConfidenceViews:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = extract("test_interface_basic_ptree")

    def test_calls_is_the_union_of_the_strata(self):
        assert self.ir.calls == (
            self.ir.calls_resolved | self.ir.calls_assumed | self.ir.calls_unresolved
        )

    def test_calls_must_is_the_resolved_stratum(self):
        assert self.ir.calls_must == self.ir.calls_resolved


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

    def test_generic_calls_land_in_the_resolved_stratum(self):
        # sema names the specific for each call, so every edge — the three
        # specifics and the caller->interface edge — is `resolved`; nothing is
        # left to guess.
        caller = get_subroutine(self.ir, "caller_basic_mod", "test_calls")
        iface = get_interface(self.ir, "interface_basic_mod", "compute")
        expected = {
            (caller.id, iface.id),
            (caller.id, get_subroutine(self.ir, "interface_basic_mod", "compute_real").id),
            (caller.id, get_subroutine(self.ir, "interface_basic_mod", "compute_int").id),
            (caller.id, get_subroutine(self.ir, "interface_basic_mod", "compute_logical").id),
        }
        assert self.ir.calls_resolved == expected
        assert self.ir.calls_assumed == set()
        assert self.ir.calls_unresolved == set()


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
# Calls to targets defined nowhere in the parsed set (D3: unresolved)
# =============================================================================

class TestExternalCalls:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = extract("test_external_calls_ptree")
        self.caller = get_subroutine(self.ir, "ext_caller_mod", "test_external_calls")

    def test_unresolved_targets_are_first_class_entities(self):
        ext_sub = self.ir.get("ext_sub")
        ext_fun = self.ir.get("ext_fun")
        assert ext_sub is not None and not ext_sub.defined
        assert ext_fun is not None and not ext_fun.defined
        # the call context tells the frontend which flavour each target is
        assert ext_sub.kind == "subroutine"
        assert ext_fun.kind == "function"

    def test_edges_land_in_the_unresolved_stratum(self):
        assert self.ir.calls_unresolved == {
            (self.caller.id, "ext_sub"),
            (self.caller.id, "ext_fun"),
        }

    def test_resolvable_neighbor_is_unaffected(self):
        helper = get_subroutine(self.ir, "ext_provider_mod", "helper_sub")
        assert (self.caller.id, helper.id) in self.ir.calls_resolved

    def test_must_view_excludes_unresolved(self):
        assert not any(callee in ("ext_sub", "ext_fun")
                       for (_, callee) in self.ir.calls_must)
        # ... while the may view keeps them
        assert (self.caller.id, "ext_sub") in self.ir.calls


# =============================================================================
# Type-bound procedure calls, generic and `=>`-renamed (Phase 2 / DESIGN Q2)
# =============================================================================

class TestTypeBoundGeneric:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = extract("test_type_bound_generic_ptree")
        self.caller = get_subroutine(self.ir, "tbp_caller_mod", "test_type_bound_calls")

    def test_generic_binding_resolves_by_argument_type(self):
        go_r = get_subroutine(self.ir, "tbp_mod", "go_r")
        go_i = get_subroutine(self.ir, "tbp_mod", "go_i")
        assert (self.caller.id, go_r.id) in self.ir.calls_resolved
        assert (self.caller.id, go_i.id) in self.ir.calls_resolved

    def test_renamed_binding_resolves_to_the_implementation(self):
        # `procedure :: reset => reset_state`; the call is written obj%reset()
        reset = get_subroutine(self.ir, "tbp_mod", "reset_state")
        assert (self.caller.id, reset.id) in self.ir.calls_resolved

    def test_nothing_is_guessed(self):
        assert self.ir.calls_assumed == set()
        assert self.ir.calls_unresolved == set()

    def test_bindings_are_entity_facts(self):
        gadget = next(dt for dt in self.ir.derived_types if dt.name == "gadget_t")
        assert ("reset", "reset_state") in gadget.bindings


# =============================================================================
# Derived-type EXTENDS: inherited bindings and module-dependency edges
# =============================================================================

class TestTypeExtends:

    @pytest.fixture(autouse=True)
    def setup(self):
        from flinspect.parse_forest import ParseForest
        self.forest = ParseForest(["tests/f90/test_type_extends_ptree"])
        self.ir = self.forest.ir

    def test_parent_type_recorded(self):
        by_name = {dt.name: dt for dt in self.ir.derived_types}
        assert by_name["tagged_shape_t"].parent_type == "shape_t"
        assert by_name["circle_t"].parent_type == "shape_t"

    def test_inherited_binding_static_dispatch_is_resolved(self):
        # `type(circle_t) :: c; call c%describe()` — sema hoists the object and
        # names the parent's impl
        caller = get_subroutine(self.ir, "shape_ext_mod", "use_circle")
        impl = get_subroutine(self.ir, "shape_base_mod", "describe_shape")
        assert (caller.id, impl.id) in self.ir.calls_resolved

    def test_inherited_binding_dynamic_dispatch_is_assumed(self):
        # `class(circle_t) :: c; call c%describe()` — dispatch may pick an
        # override at runtime, so the declared type's impl (found by walking the
        # EXTENDS chain: circle_t has no own binding) is a guess
        caller = get_subroutine(self.ir, "shape_ext_mod", "describe_any")
        impl = get_subroutine(self.ir, "shape_base_mod", "describe_shape")
        assert (caller.id, impl.id) in self.ir.calls_assumed
        assert (caller.id, impl.id) not in self.ir.calls_must

    def test_cross_module_extension_is_a_module_dependency(self):
        g = self.forest.get_module_dependency_graph()
        assert ("shape_ext_mod", "shape_base_mod") in g.edges()

    def test_same_module_extension_draws_no_self_loop(self):
        # tagged_shape_t extends shape_t inside shape_base_mod: a self-loop here
        # would make every acyclicity/topological analysis trivially fail (the
        # real-corpus case is MOM_io_file's file types)
        g = self.forest.get_module_dependency_graph()
        assert not [e for e in g.edges() if e[0] == e[1]]


# =============================================================================
# A public generic with PRIVATE specifics: the mangled sema answer (Q1/Q2, W4)
# =============================================================================

class TestPrivateSpecifics:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = extract("test_private_specifics_ptree")
        self.caller = get_subroutine(self.ir, "priv_caller_mod", "test_private_calls")

    def test_mangled_answers_demangle_to_scope_qualified_targets(self):
        # sema prints `priv_mod$priv_mod$compute_r(...)`; the edge must land on
        # the entity `priv_mod::compute_r`, not on a bare-name atom
        compute_r = get_subroutine(self.ir, "priv_mod", "compute_r")
        compute_i = get_subroutine(self.ir, "priv_mod", "compute_i")
        assert (self.caller.id, compute_r.id) in self.ir.calls_resolved
        assert (self.caller.id, compute_i.id) in self.ir.calls_resolved

    def test_generic_edge_kept_alongside_the_specifics(self):
        iface = get_interface(self.ir, "priv_mod", "compute")
        assert (self.caller.id, iface.id) in self.ir.calls_resolved

    def test_all_edges_are_resolved(self):
        assert self.ir.calls_assumed == set()
        assert self.ir.calls_unresolved == set()


# =============================================================================
# StructureComponent actual arguments (e.g. `call update(cs%mode, 2)`)
#
# The component's type is invisible to a structural scrape, which is why the
# retired heuristic engine had to fall back to full fan-out here; sema's unparse
# names each call's specific regardless.
# =============================================================================

class TestStructureComponent:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = extract("test_struct_component_ptree")

    def test_interface_created(self):
        iface = get_interface(self.ir, "struct_comp_mod", "update")
        assert member_names(self.ir, iface) == ["update_int", "update_real"]

    def test_struct_component_args_resolve(self):
        caller = get_subroutine(self.ir, "caller_struct_mod", "test_struct_calls")
        callees = callee_names(self.ir, caller)
        assert "update_real" in callees
        assert "update_int" in callees
        assert self.ir.calls_assumed == set()


# =============================================================================
# Generic FUNCTION reference inside an expression
#
# Every other fixture calls generics through CALL statements; this one is the only
# coverage of the FunctionReference path. The dump's structure still names the
# generic (`ProcedureDesignator -> Name = 'area'`) while each reference's
# enclosing Expr annotation carries its resolved text (`area_r(y)`, `area_i(k)`)
# — consumed since Phase 2, so each reference yields exactly one resolved edge
# even though both calls share one statement.
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

    def test_each_reference_resolves_to_exactly_its_specific(self):
        # `a = area(y) + area(k)`: two calls in one statement, each resolved to
        # its own specific — all edges in the resolved stratum, none guessed.
        caller = get_subroutine(self.ir, "caller_area_mod", "test_generic_function_calls")
        iface = get_interface(self.ir, "area_mod", "area")
        assert self.ir.calls_resolved == {
            (caller.id, iface.id),
            (caller.id, get_function(self.ir, "area_mod", "area_r").id),
            (caller.id, get_function(self.ir, "area_mod", "area_i").id),
        }
        assert self.ir.calls_assumed == set()


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
# Optional arguments (signature facts) and calls that omit/keyword them
#
# The fixture's two specifics differ in their first argument's type — `init` would
# otherwise be an ambiguous generic, which sema rejects outright (Phase 1b: the
# fixture only ever compiled under -no-sema). The optional dummies are entity
# metadata (num_required in the Signature); the 2-/3-/4-argument and keyword
# calls each resolve to exactly one specific via sema.
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

    def test_every_call_form_resolves(self):
        # positional-with-omitted-optionals and keyword calls alike
        caller = get_subroutine(self.ir, "caller_optional_mod", "test_optional_calls")
        callees = callee_names(self.ir, caller)
        assert "init_simple" in callees
        assert "init_advanced" in callees
        assert self.ir.calls_assumed == set()
        assert self.ir.calls_unresolved == set()


# =============================================================================
# Same-named routines in different modules stay distinct (W5, principle #7)
# =============================================================================

class TestNameCollision:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = extract("test_name_collision_ptree")
        self.caller = get_subroutine(self.ir, "collide_caller_mod", "drive")

    def test_three_distinct_atoms_share_the_name(self):
        same_named = [s for s in self.ir.subroutines if s.name == "apply_bc"]
        assert len(same_named) == 3
        assert {s.id for s in same_named} == {
            "collide_a_mod::apply_bc",
            "collide_b_mod::apply_bc",
            "collide_c_mod::apply_bc",
        }

    def test_each_call_resolves_to_its_own_module(self):
        # One edge per USE form (wildcard rename / only-list / only-list rename),
        # each to a *different* atom — a bare-name model would collapse these
        # three into one edge.
        assert self.ir.calls_resolved == {
            (self.caller.id, "collide_a_mod::apply_bc"),
            (self.caller.id, "collide_b_mod::apply_bc"),
            (self.caller.id, "collide_c_mod::apply_bc"),
        }
        assert len(self.ir.callees(self.caller.id)) == 3

    def test_use_renames_are_recorded(self):
        # Both rename forms: bare (wildcard USE) and inside an only-list.
        renames = {(u.module, u.renames) for u in self.ir.uses
                   if u.scope == "collide_caller_mod" and u.renames}
        assert renames == {
            ("collide_a_mod", (("bc_a", "apply_bc"),)),
            ("collide_c_mod", (("bc_c", "apply_bc"),)),
        }
