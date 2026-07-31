"""Pure graph-view construction: an IR neighbourhood → renderable elements.

This is the testable half of the Explorer. It holds every decision about *what*
is drawn — which entities are in a neighbourhood, how they are grouped, and which
facts each element carries — while `explorer.py` keeps only the widget layer
(stylesheet, legend, event wiring). Nothing here imports ipywidgets or
ipycytoscape, so it is unit-testable without a browser or a kernel.

Above the seam, so nothing flang-specific appears (principles #4/#5): confidence
comes from the IR's stratified call relations alone (D3), by set membership.

Element shape mirrors cytoscape's JSON — ``{'data': {...}, 'classes': '...'}`` —
which maps one-to-one onto ``ipycytoscape.Node(data=..., classes=...)``. Facts
live in ``data`` (so a click handler can report them); ``classes`` carries only
transient UI state (the selected node). Styling therefore selects on data
attributes: ``node[defined="false"]``, ``edge[confidence="assumed"]``,
``edge[relation="interface_member"]``.
"""

from __future__ import annotations

from collections import defaultdict

import networkx as nx

from groundline.ir import (
    IR, Entity, MODULE, SUBROUTINE, FUNCTION, INTERFACE,
    RESOLVED, ASSUMED, UNRESOLVED,  # stratum labels (D3); re-exported for callers
)

# What an edge *means*: a call (confidence-bearing) vs. generic-interface
# membership, which is structure and carries no confidence.
CALL = "call"
INTERFACE_MEMBER = "interface_member"

#: Entity kinds that get their own node style; anything else renders as 'other'.
STYLED_KINDS = (SUBROUTINE, FUNCTION, INTERFACE)

UNKNOWN_MODULE = "Unknown Module"


def edge_relation(ir: IR, source_id: str, target_id: str) -> str:
    """``CALL`` for call edges, ``INTERFACE_MEMBER`` for generic membership."""
    if ir.call_confidence(source_id, target_id) is not None:
        return CALL
    if (source_id, target_id) in ir.interface_members:
        return INTERFACE_MEMBER
    return CALL


def enclosing_module_name(ir: IR, eid: str) -> str:
    """Name of the module enclosing ``eid``, for compound-node grouping.

    Falls back to the scope's own trailing segment for entities whose scope is
    named but not defined in the parsed set (e.g. an unresolved target pinned to
    an external module, ``netcdf::nf90_open``), and to ``UNKNOWN_MODULE`` for
    bare-name atoms with no scope at all.
    """
    seen = set()
    cur = ir.get(eid)
    while cur is not None and cur.id not in seen:
        if cur.kind == MODULE:
            return cur.name
        seen.add(cur.id)
        scope = cur.scope
        nxt = ir.get(scope) if scope else None
        if nxt is None:
            return scope.split("::")[-1] if scope else UNKNOWN_MODULE
        cur = nxt
    return UNKNOWN_MODULE


def gen_subgraph(ir: IR, entity: Entity) -> nx.DiGraph:
    """The one-hop neighbourhood of ``entity`` as a NetworkX graph of entities.

    Subroutines/functions get callers and callees (the *may* view, so
    ``assumed``/``unresolved`` neighbours are present and get annotated by
    :func:`subgraph_elements`); a generic interface gets its callers and its
    specific procedures.
    """
    subgraph = nx.DiGraph()
    subgraph.add_node(entity)
    if entity.kind in (SUBROUTINE, FUNCTION):
        for caller in ir.callers(entity.id):
            subgraph.add_edge(caller, entity)
        for callee in ir.callees(entity.id):
            subgraph.add_edge(entity, callee)
    elif entity.kind == INTERFACE:
        for caller in ir.callers(entity.id):
            subgraph.add_edge(caller, entity)
        for procedure in ir.members(entity.id):
            subgraph.add_edge(entity, procedure)
    return subgraph


def subgraph_elements(ir: IR, subgraph: nx.DiGraph, center: Entity):
    """Convert a neighbourhood into cytoscape-shaped node and edge elements.

    Returns ``(nodes, edges)``, each a list of ``{'data': ..., 'classes': ...}``
    dicts. Nodes are keyed by the scope-qualified ``Entity.id`` — never the bare
    name (W5, principle #7) — with the name used only as the display label, so
    two same-named routines in different modules stay two nodes.

    Node data: ``id``, ``label``, ``type`` (entity kind, or ``'other'``),
    ``defined`` (``'true'``/``'false'`` — ghosting hook for referenced-but-not-
    parsed targets), and ``parent`` when compound grouping applies. Module
    compound parents are synthesised with ``id = 'module_<name>'`` and
    ``type = 'module'``.

    Edge data: ``source``, ``target``, ``relation`` (call vs. interface
    membership), ``direction`` relative to the center (``incoming`` /
    ``outgoing`` / ``other``), and ``confidence`` for call edges (D3).
    """
    program_units = defaultdict(list)
    for node in subgraph.nodes():
        program_units[enclosing_module_name(ir, node.id)].append(node)

    nodes = []
    for unit_name, members in program_units.items():
        # A compound parent is only worth drawing when it groups something.
        if len(members) > 1 or len(program_units) > 1:
            nodes.append({
                'data': {
                    'id': f'module_{unit_name}',
                    'label': unit_name,
                    'type': 'module',
                },
                'classes': '',
            })

    for node in subgraph.nodes():
        unit_name = enclosing_module_name(ir, node.id)
        data = {
            'id': node.id,
            'label': node.name,
            'type': node.kind if node.kind in STYLED_KINDS else 'other',
            'defined': 'true' if node.defined else 'false',
        }
        if len(program_units) > 1 or len(program_units.get(unit_name, [])) > 1:
            data['parent'] = f'module_{unit_name}'
        nodes.append({
            'data': data,
            'classes': 'selected' if node == center else '',
        })

    edges = []
    for source, target in subgraph.edges():
        data = {
            'source': source.id,
            'target': target.id,
            'relation': edge_relation(ir, source.id, target.id),
        }
        if target == center:
            data['direction'] = 'incoming'
        elif source == center:
            data['direction'] = 'outgoing'
        else:
            data['direction'] = 'other'

        confidence = ir.call_confidence(source.id, target.id)
        if confidence is not None:
            data['confidence'] = confidence

        edges.append({'data': data, 'classes': ''})

    return nodes, edges
