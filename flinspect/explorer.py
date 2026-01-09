import re
import networkx as nx
from collections import defaultdict
from flinspect.parse_node import Module, Program, Subprogram, Callable, Subroutine, Function, Interface, DerivedType
from ipywidgets import VBox, HBox, Dropdown, Text, Select, Output, HTML, IntSlider, Label, Button
import ipycytoscape


out = Output()

class Explorer(VBox):
    def __init__(self, forest, **kwargs):

        super().__init__(**kwargs)
        out.clear_output()

        # Initialize state
        self.store = forest.registry._store

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

    def get_options_for_all_categories(self):
        """Get all callable options across all categories."""
        options = set()
        for cls in [Subroutine, Function, Interface, DerivedType]:
            options.update(self.store[cls].keys())
        return options

    def find_callable_by_name(self, name):
        """Find a callable object by name across all categories."""
        for cls in [Subroutine, Function, Interface]:
            if name in self.store[cls]:
                return self.store[cls][name]
        return None

    def gen_subgraph(self, routine):
        subgraph = nx.DiGraph()
        subgraph.add_node(routine)
        if isinstance(routine, (Subroutine, Function)):
            for caller in routine.callers:
                subgraph.add_edge(caller, routine)
            for callee in routine.callees:
                subgraph.add_edge(routine, callee)
        elif isinstance(routine, Interface):
            for caller in routine.callers:
                subgraph.add_edge(caller, routine)
            for procedure in routine.procedures:
                subgraph.add_edge(routine, procedure)
        return subgraph

    def update_graph_display(self):
        """Update the dependency graph display based on current selection."""
            
        selected_name = self.name_selector.value
        if not selected_name:
            self.graph_widget.graph.clear()
            return
            
        # Find the selected callable
        center_node = self.find_callable_by_name(selected_name)
        if not center_node:
            self.graph_widget.graph.clear()
            return
        
        # Extract subgraph
        subgraph = self.gen_subgraph(center_node)

        self.graph_widget.graph.clear()
        
        # Group nodes by program unit
        program_units = defaultdict(list)
        for node in subgraph.nodes():
            # Get the program unit name
            program_unit_name = 'Unknown Module'
            
            if hasattr(node, 'program_unit') and node.program_unit:
                program_unit_name = node.program_unit.name
            
            program_units[program_unit_name].append(node)
        
        # Add parent nodes for each program unit
        for program_unit_name, nodes in program_units.items():
            # Only create parent node if there are multiple nodes or if we want to show modules explicitly
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
            # Get the program unit name 
            program_unit_name = 'Unknown Module'  # Default fallback
            
            if hasattr(node, 'program_unit') and node.program_unit:
                program_unit_name = node.program_unit.name
                
            node_data = {
                'id': node.name,
                'label': node.name,
                'type': 'subroutine' if isinstance(node, Subroutine) else 
                        'function' if isinstance(node, Function) else 
                        'interface' if isinstance(node, Interface) else 'other'
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
                'source': source.name,
                'target': target.name
            }
            
            # Determine edge direction relative to center node
            if target == center_node:
                # Edge pointing to center node (incoming)
                edge_data['direction'] = 'incoming'
            elif source == center_node:
                # Edge from center node (outgoing)
                edge_data['direction'] = 'outgoing'
            else:
                # Edge between other nodes
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

        options = set()

        new_category = change['new']
        if new_category == "All":
            options = self.get_options_for_all_categories()
        elif new_category == "Subroutine":
            options = set(self.store[Subroutine].keys())
        elif new_category == "Function":
            options = set(self.store[Function].keys())
        elif new_category == "Interface":
            options = set(self.store[Interface].keys())
        elif new_category == "Derived Type":
            options = set(self.store[DerivedType].keys())
        else:
            if new_category is not None:
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
        # In ipycytoscape, the event structure is: {'data': {...}}
        # where data contains the node information
        print("Clicked node:", event['data'])
        if 'data' in event and 'id' in event['data']:
            clicked_node_name = event['data']['id']
            
            # Update the name selector to the clicked node
            if clicked_node_name in self.name_selector.options:
                self.name_selector.value = clicked_node_name
            else:
                # If the clicked node is not in current options, we need to update the category
                # Find which category this node belongs to
                clicked_node = self.find_callable_by_name(clicked_node_name)
                if clicked_node:
                    if isinstance(clicked_node, Subroutine):
                        self.category_picker.value = "Subroutine"
                    elif isinstance(clicked_node, Function):
                        self.category_picker.value = "Function"
                    elif isinstance(clicked_node, Interface):
                        self.category_picker.value = "Interface"
                    
                    # Wait for category update then set the name
                    self.name_selector.value = clicked_node_name
