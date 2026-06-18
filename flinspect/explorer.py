import re
import networkx as nx
from collections import defaultdict
from flinspect.ir import (
    MODULE, SUBROUTINE, FUNCTION, INTERFACE, DERIVED_TYPE, CALLABLE_KINDS,
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
                    'line-color': '#95a5a6',
                    'target-arrow-color': '#95a5a6',
                    'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier'
                }
            },
            {
                'selector': 'edge[direction="incoming"]',
                'style': {
                    'line-color': '#3498db',
                    'target-arrow-color': '#3498db'
                }
            },
            {
                'selector': 'edge[direction="outgoing"]',
                'style': {
                    'line-color': '#e74c3c',
                    'target-arrow-color': '#e74c3c'
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

    def _enclosing_module_name(self, eid):
        seen = set()
        cur = self.ir.get(eid)
        while cur is not None and cur.id not in seen:
            if cur.kind == MODULE:
                return cur.name
            seen.add(cur.id)
            cur = self.ir.get(cur.scope) if cur.scope else None
        return 'Unknown Module'

    def gen_subgraph(self, entity):
        subgraph = nx.DiGraph()
        subgraph.add_node(entity)
        if entity.kind in (SUBROUTINE, FUNCTION):
            for caller in self.ir.callers(entity.id):
                subgraph.add_edge(caller, entity)
            for callee in self.ir.callees(entity.id):
                subgraph.add_edge(entity, callee)
        elif entity.kind == INTERFACE:
            for caller in self.ir.callers(entity.id):
                subgraph.add_edge(caller, entity)
            for procedure in self.ir.members(entity.id):
                subgraph.add_edge(entity, procedure)
        return subgraph

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

        # Extract subgraph
        subgraph = self.gen_subgraph(center_node)

        self.graph_widget.graph.clear()

        # Group nodes by program unit (enclosing module)
        program_units = defaultdict(list)
        for node in subgraph.nodes():
            program_units[self._enclosing_module_name(node.id)].append(node)

        # Add parent nodes for each program unit
        for program_unit_name, nodes in program_units.items():
            if len(nodes) > 1 or len(program_units) > 1:
                parent_data = {
                    'id': f'module_{program_unit_name}',
                    'label': program_unit_name,
                    'type': 'module'
                }
                parent_node = ipycytoscape.Node(data=parent_data)
                self.graph_widget.graph.add_node(parent_node)

        # Add child nodes
        for node in subgraph.nodes():
            program_unit_name = self._enclosing_module_name(node.id)

            node_data = {
                'id': node.id,
                'label': node.name,
                'type': node.kind if node.kind in ('subroutine', 'function', 'interface') else 'other'
            }

            # Set parent if there are multiple program units or multiple nodes per unit
            if len(program_units) > 1 or len(program_units.get(program_unit_name, [])) > 1:
                node_data['parent'] = f'module_{program_unit_name}'

            # Mark the selected node
            if node == center_node:
                node_data['classes'] = 'selected'

            cytoscape_node = ipycytoscape.Node(data=node_data)
            self.graph_widget.graph.add_node(cytoscape_node)

        # Add edges
        for source, target in subgraph.edges():
            edge_data = {
                'source': source.id,
                'target': target.id
            }

            if target == center_node:
                edge_data['direction'] = 'incoming'
            elif source == center_node:
                edge_data['direction'] = 'outgoing'
            else:
                edge_data['direction'] = 'other'

            cytoscape_edge = ipycytoscape.Edge(data=edge_data)
            self.graph_widget.graph.add_edge(cytoscape_edge)

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
