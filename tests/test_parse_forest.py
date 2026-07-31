"""Tests for the ParseForest consumer (graphs built from the IR).

Above the seam: these assert on NetworkX graph shape only — never on flang
strings or frontend internals (principle #5).
"""

import pytest
from pathlib import Path

from groundline.frontend import FlangDumpFrontend
from groundline.ir import RESOLVED, UNRESOLVED
from groundline.parse_forest import ParseForest


F90_DIR = Path(__file__).parent / "f90"


def forest(*fixtures):
    paths = [F90_DIR / f for f in fixtures]
    for p in paths:
        assert p.exists(), f"Parse tree not found: {p}"
    return ParseForest(ir=FlangDumpFrontend().extract(paths))


# =============================================================================
# Scope-qualified node identity in the call graph (W5, principle #7)
# =============================================================================

class TestCallGraphNodeIdentity:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.forest = forest("test_name_collision_ptree")
        self.g = self.forest.get_call_graph()

    def test_same_named_routines_are_distinct_nodes(self):
        same_named = [n for n in self.g.nodes() if n.name == "apply_bc"]
        assert len(same_named) == 3
        assert len({n.id for n in same_named}) == 3

    def test_no_edge_merging(self):
        drive = next(n for n in self.g.nodes() if n.name == "drive")
        # Three calls to three same-named targets: three surviving out-edges.
        assert self.g.out_degree(drive) == 3
        assert {t.id for t in self.g.successors(drive)} == {
            "collide_a_mod::apply_bc",
            "collide_b_mod::apply_bc",
            "collide_c_mod::apply_bc",
        }

    def test_each_target_keeps_its_own_program_unit(self):
        units = {n.id: self.g.nodes[n]["program_unit"]
                 for n in self.g.nodes() if n.name == "apply_bc"}
        assert units == {
            "collide_a_mod::apply_bc": "collide_a_mod",
            "collide_b_mod::apply_bc": "collide_b_mod",
            "collide_c_mod::apply_bc": "collide_c_mod",
        }


# =============================================================================
# Confidence as an edge attribute, filterable by any NetworkX consumer (D3)
# =============================================================================

class TestCallGraphConfidence:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.forest = forest("test_external_calls_ptree")
        self.g = self.forest.get_call_graph()
        self.caller = next(n for n in self.g.nodes()
                           if n.name == "test_external_calls")

    def test_every_edge_carries_a_stratum(self):
        strata = {d["confidence"] for _, _, d in self.g.edges(data=True)}
        assert strata <= {RESOLVED, "assumed", UNRESOLVED}
        assert None not in strata

    def test_strata_match_the_ir_relations(self):
        labelled = {(u.id, v.id): d["confidence"]
                    for u, v, d in self.g.edges(data=True)}
        assert labelled[(self.caller.id, "ext_provider_mod::helper_sub")] == RESOLVED
        assert labelled[(self.caller.id, "ext_sub")] == UNRESOLVED
        assert labelled[(self.caller.id, "ext_fun")] == UNRESOLVED

    def test_consumers_can_filter_without_touching_the_ir(self):
        # The whole point: no re-deriving set membership downstream.
        uncertain = [(u.id, v.id) for u, v, d in self.g.edges(data=True)
                     if d["confidence"] != RESOLVED]
        assert sorted(uncertain) == [
            (self.caller.id, "ext_fun"),
            (self.caller.id, "ext_sub"),
        ]

    def test_must_only_keeps_only_resolved_edges(self):
        g = self.forest.get_call_graph(must_only=True)
        assert {d["confidence"] for _, _, d in g.edges(data=True)} == {RESOLVED}
        # Every surviving edge is a must-edge. (Not an equality: the graph only
        # keeps edges whose caller is a subroutine/function node, so a must-edge
        # from another kind of scope has no graph edge to be.)
        assert {(u.id, v.id) for u, v in g.edges()} <= self.forest.ir.calls_must
        assert self.g.number_of_edges() > g.number_of_edges()

    def test_must_only_leaves_undefined_targets_isolated(self):
        # Node set is unchanged (every subroutine/function in the IR); it is the
        # *edges* that the must view withholds.
        g = self.forest.get_call_graph(must_only=True)
        undefined = [n for n in g.nodes() if not n.defined]
        assert {n.id for n in undefined} == {"ext_sub", "ext_fun"}
        assert all(g.degree(n) == 0 for n in undefined)
        # ... whereas the may view connects them
        assert all(self.g.degree(n) == 1 for n in undefined)
