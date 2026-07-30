"""Explorer — the Jupyter widget layer over the IR.

Kept deliberately thin (principle #10 — rendering is not the seam): every
decision about *what* is drawn lives in :mod:`flinspect.graph_view`, which is
pure and unit-tested; this module owns the stylesheet, the legend, and the event
wiring. The stylesheet is where the visual encoding is defined:

* node fill      = entity kind (subroutine / function / interface)
* node ghosting  = ``defined="false"`` — referenced but never parsed
* edge colour    = direction relative to the selected node (incoming/outgoing)
* edge line style = confidence stratum (D3): solid resolved, dashed assumed,
  dotted + muted unresolved
* purple diamond-headed edges = generic-interface membership (structure, not a
  call, hence no confidence)

The two edge encodings compose because they touch different properties (colour
vs. line style); ``LEGEND_HTML`` below spells the whole scheme out for the user.
"""

import re
from flinspect.ir import (
    SUBROUTINE, FUNCTION, INTERFACE, DERIVED_TYPE, CALLABLE_KINDS,
)
from flinspect.graph_view import (
    gen_subgraph, subgraph_elements, INTERFACE_MEMBER,
)
from ipywidgets import VBox, HBox, Dropdown, Text, Select, Output, HTML, IntSlider, Label, Button
import ipycytoscape


out = Output()

# Map the UI category labels to IR entity kinds.
_CATEGORY_KIND = {
    "Subroutine": SUBROUTINE,
    "Function": FUNCTION,
    "Interface": INTERFACE,
    "Derived Type": DERIVED_TYPE,
}

# Colours shared by the stylesheet and the legend.
_INCOMING_COLOR = '#3498db'
_OUTGOING_COLOR = '#e74c3c'
_MEMBER_COLOR = '#8e44ad'
_EDGE_COLOR = '#95a5a6'


def _line_swatch(style, color=_EDGE_COLOR):
    return (f"<span style='display:inline-block;width:34px;border-top:3px {style} "
            f"{color};vertical-align:middle;margin:0 4px 4px 0;'></span>")


def _node_swatch(color, extra=''):
    return (f"<span style='display:inline-block;width:14px;height:14px;border-radius:50%;"
            f"background:{color};vertical-align:middle;margin:0 4px -2px 0;{extra}'></span>")


#: Makes the visual encoding discoverable — call confidence (D3) is the point of
#: the graph, so it must not be a thing you have to read the source to decode.
LEGEND_HTML = f"""
<div style='font-size:11px;line-height:1.7;color:#333;border:1px solid #ddd;
            border-radius:4px;padding:6px 10px;margin:4px 0;max-width:780px;'>
  <b>Call confidence</b> (line style):
    {_line_swatch('solid')}resolved
    {_line_swatch('dashed')}assumed
    <span style='opacity:0.55;'>{_line_swatch('dotted')}unresolved</span>
  &nbsp;|&nbsp; <b>Direction</b> (colour):
    {_line_swatch('solid', _INCOMING_COLOR)}calls in
    {_line_swatch('solid', _OUTGOING_COLOR)}calls out
  &nbsp;|&nbsp; {_line_swatch('solid', _MEMBER_COLOR)}interface membership
  <br>
  <b>Nodes:</b>
    {_node_swatch('#ECCBCA')}subroutine
    {_node_swatch('#c7b7a2')}function
    {_node_swatch('#b2c0ca')}interface
    {_node_swatch('#ffffff', 'border:2px dashed #999;opacity:0.6;')}undefined
      (referenced, never parsed)
</div>
"""


class Explorer(VBox):
    def __init__(self, forest, **kwargs):

        super().__init__(**kwargs)
        out.clear_output()

        # Consume the IR only (no flang/registry internals).
        self.ir = forest.ir

        # Initialize Widgets
        self.category_picker = Dropdown(
            description='Category:',
            value=None,
            options=[
                "All",
                "Subroutine",
                "Function",
                "Interface",
                "Derived Type",
            ],
            layout={'width': '400px'},
            style={"description_width": "100px"}
        )

        self.search_box = Text(
            placeholder="Type name",
            description="Search:",
            continuous_update=False,
            layout={'width': '500px'},
            style={"description_width": "100px"}
        )

        self.name_selector = Select(
            options=[],
            layout={'width': '500px'},
            rows=10,
        )
        self.name_selector.unfiltered_options = []

        self.graph_widget =self.create_graph_widget()

        # Button section for graph controls
        self.graph_top_bar = HBox([
            Label("Dependency Graph:", layout={'width': '100px'}),
            HTML("<span style='margin-left: 5px;'></span>")
        ])

        # Layout all widgets
        self.children = [
            self.category_picker,
            self.search_box,
            self.name_selector,
            HTML("<hr>"),
            self.graph_top_bar,
            HTML(LEGEND_HTML),
            self.graph_widget,
            out
        ]

        # observe widget changes
        self.category_picker.observe(self.update_category, names='value', type='change')
        self.search_box.observe(self.on_search_box_change, names='value', type='change')
        self.name_selector.observe(self.on_name_selection_change, names='value', type='change')


    def create_graph_widget(self):
        """Create and configure the graph widget."""
        graph_widget = ipycytoscape.CytoscapeWidget()
        graph_widget.layout = {'width': '800px', 'height': '600px'}
        graph_widget.on('node', 'click', self.on_node_click)

        # Configure graph appearance
        graph_widget.set_style([
            {
                'selector': 'node',
                'style': {
                    'label': 'data(label)',
                    'width': '60px',
                    'height': '60px',
                    'background-color': "#346edb",
                    'text-valign': 'center',
                    'text-halign': 'center',
                    'color': "#000000",
                    'font-size': '12px',
                    'text-wrap': 'wrap',
                    'text-max-width': '80px'
                }
            },
            {
                'selector': 'node[type="module"]',
                'style': {
                    'label': 'data(label)',
                    'width': '200px',
                    'height': '150px',
                    'background-color': "#e8e8e8",
                    'background-opacity': 0.7,
                    'border-width': '2px',
                    'border-color': '#666666',
                    'border-style': 'dashed',
                    'text-valign': 'top',
                    'text-halign': 'center',
                    'color': "#333333",
                    'font-size': '14px',
                    'font-weight': 'bold',
                    'text-margin-y': '14px',
                    'shape': 'rectangle'
                }
            },
            {
                'selector': 'node[type="subroutine"]',
                'style': {
                    'background-color': "#ECCBCA"
                }
            },
            {
                'selector': 'node[type="function"]',
                'style': {
                    'background-color': "#c7b7a2"
                }
            },
            {
                'selector': 'node[type="interface"]',
                'style': {
                    'background-color': "#b2c0ca"
                }
            },
            {
                # Referenced but never parsed (defined=False): ghosted outline, so
                # "we don't have this code" reads at a glance (D3, principle #6).
                'selector': 'node[defined="false"]',
                'style': {
                    'background-opacity': 0.15,
                    'border-width': '2px',
                    'border-color': '#999999',
                    'border-style': 'dashed',
                    'color': '#777777',
                    'font-style': 'italic'
                }
            },
            {
                'selector': 'node.selected',
                'style': {
                    'border-width': '4px',
                    'border-color': '#9b59b6'
                }
            },
            {
                'selector': 'edge',
                'style': {
                    'width': 2,
                    'line-color': _EDGE_COLOR,
                    'target-arrow-color': _EDGE_COLOR,
                    'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier'
                }
            },
            # Direction sets colour; confidence (below) sets line style — the two
            # encodings touch disjoint properties, so they compose.
            {
                'selector': 'edge[direction="incoming"]',
                'style': {
                    'line-color': _INCOMING_COLOR,
                    'target-arrow-color': _INCOMING_COLOR
                }
            },
            {
                'selector': 'edge[direction="outgoing"]',
                'style': {
                    'line-color': _OUTGOING_COLOR,
                    'target-arrow-color': _OUTGOING_COLOR
                }
            },
            {
                'selector': 'edge[confidence="resolved"]',
                'style': {
                    'line-style': 'solid'
                }
            },
            {
                'selector': 'edge[confidence="assumed"]',
                'style': {
                    'line-style': 'dashed'
                }
            },
            {
                'selector': 'edge[confidence="unresolved"]',
                'style': {
                    'line-style': 'dotted',
                    'opacity': 0.55,
                    'width': 1
                }
            },
            {
                # Interface membership is structure, not a call: no confidence, and
                # visually distinct from every call edge. Listed after the direction
                # rules so its colour wins.
                'selector': f'edge[relation="{INTERFACE_MEMBER}"]',
                'style': {
                    'line-color': _MEMBER_COLOR,
                    'target-arrow-color': _MEMBER_COLOR,
                    'target-arrow-shape': 'diamond',
                    'line-style': 'solid',
                    'width': 2
                }
            },
            {
                'selector': ':parent',
                'style': {
                    'text-valign': 'top',
                    'text-halign': 'center',
                    'background-color': '#f0f0f0',
                    'background-opacity': 0.2,
                    'border-width': '2px',
                    'border-color': '#888888',
                    'border-style': 'solid'
                }
            }
        ])

        return graph_widget

    # ------------------------------------------------------------------ #
    # IR queries
    # ------------------------------------------------------------------ #
    def _ids_of_kind(self, kind):
        return [e.id for e in self.ir.of_kind(kind)]

    def get_options_for_all_categories(self):
        """All selectable entity ids across the browsable categories."""
        options = set()
        for kind in (SUBROUTINE, FUNCTION, INTERFACE, DERIVED_TYPE):
            options.update(self._ids_of_kind(kind))
        return options

    def find_entity_by_id(self, eid):
        """Find a browsable entity (subroutine/function/interface) by id."""
        entity = self.ir.get(eid)
        if entity is not None and entity.kind in CALLABLE_KINDS:
            return entity
        return None

    def gen_subgraph(self, entity):
        """The one-hop neighbourhood of ``entity`` (see :mod:`flinspect.graph_view`)."""
        return gen_subgraph(self.ir, entity)

    def update_graph_display(self):
        """Update the dependency graph display based on current selection."""

        selected_id = self.name_selector.value
        if not selected_id:
            self.graph_widget.graph.clear()
            return

        center_node = self.find_entity_by_id(selected_id)
        if not center_node:
            self.graph_widget.graph.clear()
            return

        # All content decisions (grouping, confidence, ghosting) happen in the pure
        # builder; here we only hand the elements to the widget.
        nodes, edges = subgraph_elements(
            self.ir, self.gen_subgraph(center_node), center_node)

        self.graph_widget.graph.clear()

        # `classes` is a top-level cytoscape element attribute, not a data key —
        # passing it inside `data` silently disables the `.selected` style.
        for node in nodes:
            self.graph_widget.graph.add_node(
                ipycytoscape.Node(data=node['data'], classes=node['classes']))
        for edge in edges:
            self.graph_widget.graph.add_edge(
                ipycytoscape.Edge(data=edge['data'], classes=edge['classes']))

        # Apply layout - use a layout that works well with compound nodes
        self.graph_widget.set_layout(name='cose', animate=False,
                                   nodeRepulsion=4000,
                                   idealEdgeLength=100,
                                   edgeElasticity=100,
                                   nestingFactor=1.2)

    @out.capture()
    def update_category(self, change):
        """Update available options when category changes."""
        self.search_box.value = ""
        self.name_selector.value = None

        new_category = change['new']
        if new_category == "All":
            options = self.get_options_for_all_categories()
        elif new_category in _CATEGORY_KIND:
            options = set(self._ids_of_kind(_CATEGORY_KIND[new_category]))
        elif new_category is None:
            options = set()
        else:
            raise ValueError(f"Unknown category: {new_category}")

        self.name_selector.unfiltered_options = list(options)
        self.name_selector.options = list(options)

        # Clear graph when category changes
        self.graph_widget.graph.clear()

    @out.capture()
    def on_search_box_change(self, change):
        """Filter options based on search term."""
        search_term = change['new']
        search_term = rf'{search_term}'
        try:
            filtered_options = [name for name in self.name_selector.unfiltered_options
                              if re.search(search_term, name, re.IGNORECASE)]
            self.name_selector.options = filtered_options
        except Exception as e:
            print(f"Error occurred while searching: {e}")

    @out.capture()
    def on_name_selection_change(self, change):
        """Handle name selection changes."""
        self.update_graph_display()


    @out.capture()
    def on_node_click(self, event):
        """Handle node clicks in the graph."""
        print("Clicked node:", event['data'])
        if 'data' in event and 'id' in event['data']:
            clicked_id = event['data']['id']

            if clicked_id in self.name_selector.options:
                self.name_selector.value = clicked_id
            else:
                clicked_node = self.find_entity_by_id(clicked_id)
                if clicked_node:
                    if clicked_node.kind == SUBROUTINE:
                        self.category_picker.value = "Subroutine"
                    elif clicked_node.kind == FUNCTION:
                        self.category_picker.value = "Function"
                    elif clicked_node.kind == INTERFACE:
                        self.category_picker.value = "Interface"

                    self.name_selector.value = clicked_id
