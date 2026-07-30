"""Tests for the pure graph-view builder (the testable half of the Explorer).

These are widget-free by construction: :mod:`flinspect.graph_view` imports no
ipywidgets/ipycytoscape, so no kernel or browser is involved and the visual
encoding (confidence strata, ghosted undefined targets, scope-qualified node
identity) is asserted on plain dicts.

One test instantiates the ``Explorer`` widget itself, as a smoke check that the
thin widget layer still consumes these elements. That pulls in ipycytoscape →
pandas, so run pytest with ``PYTHONNOUSERSITE=1`` if a broken user-site pandas
shadows the venv:

    PYTHONNOUSERSITE=1 .venv/bin/python -m pytest tests -q
"""

import pytest
from pathlib import Path

from flinspect.frontend import FlangDumpFrontend
from flinspect.ir import IR, Entity, MODULE, SUBROUTINE
from flinspect.graph_view import (
    ASSUMED, CALL, INTERFACE_MEMBER, RESOLVED, UNKNOWN_MODULE, UNRESOLVED,
    enclosing_module_name, gen_subgraph, subgraph_elements,
)


F90_DIR = Path(__file__).parent / "f90"


def extract(*fixtures):
    paths = [F90_DIR / f for f in fixtures]
    for p in paths:
        assert p.exists(), f"Parse tree not found: {p}"
    return FlangDumpFrontend().extract(paths)


def elements_for(ir, entity):
    return subgraph_elements(ir, gen_subgraph(ir, entity), entity)


def entity(ir, kind, mod, name):
    for e in ir.of_kind(kind):
        if e.name == name and e.scope == mod:
            return e
    raise ValueError(f"{kind} '{name}' not found in '{mod}'")


def by_id(nodes):
    return {n['data']['id']: n for n in nodes}


def edge_map(edges):
    return {(e['data']['source'], e['data']['target']): e['data'] for e in edges}


# =============================================================================
# Node identity: same name, different module, never merged (W5, principle #7)
# =============================================================================

class TestScopeQualifiedIdentity:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = extract("test_name_collision_ptree")
        self.center = entity(self.ir, "subroutine", "collide_caller_mod", "drive")
        self.nodes, self.edges = elements_for(self.ir, self.center)

    def test_nodes_are_keyed_by_scope_qualified_id(self):
        ids = by_id(self.nodes)
        assert "collide_a_mod::apply_bc" in ids
        assert "collide_b_mod::apply_bc" in ids
        assert "collide_c_mod::apply_bc" in ids
        # ... and never by the bare name
        assert "apply_bc" not in ids

    def test_the_bare_name_is_only_the_label(self):
        labels = [n['data']['label'] for n in self.nodes
                  if n['data']['id'].endswith("::apply_bc")]
        assert labels == ["apply_bc"] * 3

    def test_three_targets_stay_three_edges(self):
        call_edges = [e for e in self.edges if e['data']['relation'] == CALL]
        assert len(call_edges) == 3
        assert len(edge_map(call_edges)) == 3

    def test_each_target_lands_in_its_own_module_parent(self):
        ids = by_id(self.nodes)
        assert ids["collide_a_mod::apply_bc"]['data']['parent'] == "module_collide_a_mod"
        assert ids["collide_b_mod::apply_bc"]['data']['parent'] == "module_collide_b_mod"
        assert ids["collide_c_mod::apply_bc"]['data']['parent'] == "module_collide_c_mod"

    def test_center_node_carries_the_selected_class_not_a_data_key(self):
        center = by_id(self.nodes)[self.center.id]
        assert center['classes'] == 'selected'
        assert 'classes' not in center['data']


# =============================================================================
# Confidence strata surfaced on edges (D3) + ghosted undefined targets
# =============================================================================

class TestConfidenceEncoding:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = extract("test_external_calls_ptree")
        self.center = entity(self.ir, "subroutine", "ext_caller_mod",
                             "test_external_calls")
        self.nodes, self.edges = elements_for(self.ir, self.center)
        self.edges_by_pair = edge_map(self.edges)

    def test_resolved_edge_is_labelled_resolved(self):
        data = self.edges_by_pair[(self.center.id, "ext_provider_mod::helper_sub")]
        assert data['confidence'] == RESOLVED
        assert data['relation'] == CALL

    def test_unresolved_edges_are_labelled_unresolved(self):
        for target in ("ext_sub", "ext_fun"):
            data = self.edges_by_pair[(self.center.id, target)]
            assert data['confidence'] == UNRESOLVED

    def test_undefined_targets_are_ghosted(self):
        ids = by_id(self.nodes)
        assert ids["ext_sub"]['data']['defined'] == 'false'
        assert ids["ext_fun"]['data']['defined'] == 'false'
        # ... while parsed entities are not
        assert ids[self.center.id]['data']['defined'] == 'true'
        assert ids["ext_provider_mod::helper_sub"]['data']['defined'] == 'true'

    def test_direction_and_confidence_are_independent_encodings(self):
        # Both outgoing, different strata — colour and line style never collide.
        resolved = self.edges_by_pair[(self.center.id, "ext_provider_mod::helper_sub")]
        unresolved = self.edges_by_pair[(self.center.id, "ext_sub")]
        assert resolved['direction'] == unresolved['direction'] == 'outgoing'
        assert resolved['confidence'] != unresolved['confidence']

    def test_bare_name_targets_group_under_unknown_module(self):
        assert enclosing_module_name(self.ir, "ext_sub") == UNKNOWN_MODULE


class TestAssumedStratum:
    """The `assumed` stratum, over a hand-built IR.

    Only genuine dynamic type-bound dispatch produces `assumed` edges, and that
    construct has no self-contained fixture yet (see ``tests/f90/MANIFEST.md``
    gaps) — so the middle stratum is pinned here against an IR built by hand.
    Legitimate above the seam: ``graph_view`` consumes an IR, not a dump.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = IR()
        for eid, kind, name, scope in (
            ("m::caller", SUBROUTINE, "caller", "m"),
            ("m::sure", SUBROUTINE, "sure", "m"),
            ("m::maybe", SUBROUTINE, "maybe", "m"),
            ("nowhere", SUBROUTINE, "nowhere", None),
        ):
            self.ir.entities[eid] = Entity(
                id=eid, kind=kind, name=name, scope=scope,
                defined=(eid != "nowhere"),
            )
        self.ir.entities["m"] = Entity(id="m", kind=MODULE, name="m")
        self.ir.calls_resolved.add(("m::caller", "m::sure"))
        self.ir.calls_assumed.add(("m::caller", "m::maybe"))
        self.ir.calls_unresolved.add(("m::caller", "nowhere"))

    def test_each_stratum_maps_to_its_own_label(self):
        assert self.ir.call_confidence("m::caller", "m::sure") == RESOLVED
        assert self.ir.call_confidence("m::caller", "m::maybe") == ASSUMED
        assert self.ir.call_confidence("m::caller", "nowhere") == UNRESOLVED

    def test_non_edges_have_no_confidence(self):
        assert self.ir.call_confidence("m::sure", "m::maybe") is None

    def test_all_three_strata_appear_on_the_elements(self):
        _, edges = elements_for(self.ir, self.ir.entities["m::caller"])
        assert {pair[1]: data['confidence']
                for pair, data in edge_map(edges).items()} == {
            "m::sure": RESOLVED,
            "m::maybe": ASSUMED,
            "nowhere": UNRESOLVED,
        }

    def test_most_confident_stratum_wins_if_an_edge_is_in_two(self):
        self.ir.calls_assumed.add(("m::caller", "m::sure"))
        assert self.ir.call_confidence("m::caller", "m::sure") == RESOLVED


class TestMembershipIsNotACall:

    def test_membership_edges_carry_no_confidence(self):
        ir = extract("test_interface_basic_ptree")
        assert ir.interface_members
        for iface, member in ir.interface_members:
            assert ir.call_confidence(iface, member) is None


# =============================================================================
# Interface membership is structure, not a call
# =============================================================================

class TestInterfaceMembership:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.ir = extract("test_interface_basic_ptree")
        self.iface = entity(self.ir, "interface", "interface_basic_mod", "compute")
        self.nodes, self.edges = elements_for(self.ir, self.iface)
        self.edges_by_pair = edge_map(self.edges)

    def test_membership_edges_are_marked_and_carry_no_confidence(self):
        member_edges = [d for d in self.edges_by_pair.values()
                        if d['relation'] == INTERFACE_MEMBER]
        assert len(member_edges) == 3
        assert all('confidence' not in d for d in member_edges)

    def test_calls_into_the_generic_keep_their_confidence(self):
        caller = entity(self.ir, "subroutine", "caller_basic_mod", "test_calls")
        data = self.edges_by_pair[(caller.id, self.iface.id)]
        assert data['relation'] == CALL
        assert data['confidence'] == RESOLVED
        assert data['direction'] == 'incoming'


# =============================================================================
# The widget layer still consumes these elements (thin-layer smoke test)
# =============================================================================

class TestExplorerWidgetLayer:

    def test_explorer_renders_the_elements_without_merging(self):
        # Skip (not fail) where the ipycytoscape import chain is broken — e.g. a
        # user-site pandas without numpy shadowing the venv; see the module
        # docstring (PYTHONNOUSERSITE=1 runs this test for real). exc_type is
        # needed because the breakage is a transitive ImportError, not a missing
        # ipycytoscape.
        pytest.importorskip("ipycytoscape", exc_type=ImportError)
        from flinspect.explorer import Explorer  # imports ipycytoscape
        from flinspect.parse_forest import ParseForest

        ir = extract("test_name_collision_ptree")
        explorer = Explorer(ParseForest(ir=ir))
        explorer.category_picker.value = "Subroutine"
        assert sorted(explorer.name_selector.options) == [
            "collide_a_mod::apply_bc",
            "collide_b_mod::apply_bc",
            "collide_c_mod::apply_bc",
            "collide_caller_mod::drive",
        ]

        explorer.name_selector.value = "collide_caller_mod::drive"
        graph = explorer.graph_widget.graph
        assert {n.data['id'] for n in graph.nodes} >= {
            "collide_a_mod::apply_bc",
            "collide_b_mod::apply_bc",
            "collide_c_mod::apply_bc",
        }
        assert len(graph.edges) == 3
        assert all(e.data['confidence'] == RESOLVED for e in graph.edges)
        selected = [n for n in graph.nodes if n.classes == 'selected']
        assert [n.data['id'] for n in selected] == ["collide_caller_mod::drive"]
