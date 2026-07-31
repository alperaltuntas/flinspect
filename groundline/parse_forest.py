"""ParseForest — a flang-agnostic consumer that builds graphs from the IR.

ParseForest no longer parses anything itself: it asks a frontend for an
:class:`~groundline.ir.IR` and builds NetworkX graphs purely from the IR's
relations. Nothing here imports flang-specific machinery (principle #4 — graph
vocabulary lives above the seam).
"""

import networkx as nx
from pathlib import Path

from groundline.ir import IR, MODULE
from groundline.frontend import FlangDumpFrontend


class ParseForest:
    """A collection of parsed program units, as a queryable :class:`IR` + graphs."""

    def __init__(self, parse_tree_paths=None, *, ir=None, frontend=None):
        """Build a forest from parse-tree paths (default flang frontend) or an IR.

        Parameters
        ----------
        parse_tree_paths : str | Path | list, optional
            Paths to parse-tree dump files (or directories of them).
        ir : IR, optional
            A pre-built IR to consume directly (skips extraction).
        frontend : Frontend, optional
            Frontend to extract with; defaults to :class:`FlangDumpFrontend`.
        """
        if ir is not None:
            self.ir = ir
        else:
            if parse_tree_paths is None:
                raise ValueError("Provide either parse_tree_paths or ir.")
            frontend = frontend or FlangDumpFrontend()
            self.ir = frontend.extract(parse_tree_paths)

        if self.ir.file_errors:
            print(f"Skipped {len(self.ir.file_errors)} unparseable file(s): "
                  f"{[fe.path.name for fe in self.ir.file_errors]}")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _enclosing(self, eid, kind):
        """Walk up the scope chain to the enclosing entity of the given kind."""
        seen = set()
        cur = self.ir.get(eid)
        while cur is not None and cur.id not in seen:
            if cur.kind == kind:
                return cur
            seen.add(cur.id)
            cur = self.ir.get(cur.scope) if cur.scope else None
        return None

    # ------------------------------------------------------------------ #
    # Graphs
    # ------------------------------------------------------------------ #
    def get_module_dependency_graph(self):
        """Directed graph of module dependencies (USE + type-extension edges).

        Nodes are module-name strings. Edges represent ``uses`` relationships
        (lifted from any contained scope to the enclosing module) and derived-type
        inheritance (``EXTENDS`` implies a dependency on the defining module).
        """
        g = nx.DiGraph()
        defined_modules = [m for m in self.ir.modules if m.defined]
        for m in defined_modules:
            g.add_node(m.name, source_name=m.name)

        # USE edges, lifted to the enclosing module.
        for use in self.ir.uses:
            mod = self._enclosing(use.scope, MODULE)
            if mod is None:
                continue
            g.add_edge(mod.name, use.module)

        # Type-extension (EXTENDS) edges: a child type depends on the module that
        # defines its parent type.
        type_module = {}  # type name (lower) -> set of defining module names
        for dt in self.ir.derived_types:
            mod = self._enclosing(dt.id, MODULE)
            if mod is not None:
                type_module.setdefault(dt.name.lower(), set()).add(mod.name)
        for dt in self.ir.derived_types:
            if not dt.parent_type:
                continue
            child_mod = self._enclosing(dt.id, MODULE)
            if child_mod is None:
                continue
            for parent_mod in type_module.get(dt.parent_type.lower(), ()):
                # A type extending a type of its own module is not an
                # inter-module dependency; the self-loop it would draw makes the
                # graph trivially cyclic (e.g. MOM_io_file's MOM_infra_file
                # extends MOM_file in the same module).
                if parent_mod == child_mod.name:
                    continue
                g.add_edge(child_mod.name, parent_mod)

        return g

    def get_call_graph(self, *, must_only=False):
        """Directed call graph over subroutines and functions.

        Nodes are IR :class:`~groundline.ir.Entity` objects; edges are the ``calls``
        relation (a caller may also point at a generic interface, which is added as
        a node via the edge, matching the legacy behaviour).

        Every edge carries its confidence stratum as a ``confidence`` attribute
        (``'resolved'`` / ``'assumed'`` / ``'unresolved'``; D3), so a NetworkX
        consumer can filter — e.g. ``[e for e in g.edges(data=True)
        if e[2]['confidence'] != 'resolved']`` — without re-deriving set membership.

        Parameters
        ----------
        must_only : bool, default False
            Build from the *must* view (``calls_must`` = resolved only, the
            under-approximation) instead of the *may* view (all three strata).
            Every edge is then ``confidence='resolved'``. This filters *edges*
            only — the node set is still every subroutine/function in the IR, so
            ``defined=False`` targets remain as isolated nodes.
        """
        n_unresolved = len(self.ir.calls_unresolved)
        print(f"Total unresolved call edges across all parse trees: {n_unresolved}")

        g = nx.DiGraph()
        callers = {}
        for s in self.ir.subroutines:
            pu = self._enclosing(s.id, MODULE)
            g.add_node(s, type='subroutine', program_unit=pu.name if pu else None)
            callers[s.id] = s
        for f in self.ir.functions:
            pu = self._enclosing(f.id, MODULE)
            g.add_node(f, type='function', program_unit=pu.name if pu else None)
            callers[f.id] = f

        relation = self.ir.calls_must if must_only else self.ir.calls
        for caller_id, callee_id in relation:
            caller = callers.get(caller_id)
            callee = self.ir.get(callee_id)
            if caller is None or callee is None:
                continue
            g.add_edge(caller, callee,
                       confidence=self.ir.call_confidence(caller_id, callee_id))

        return g
