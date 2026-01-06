import re
import networkx as nx
from flinspect.parse_node import Module, Program, Subprogram, Callable, Subroutine, Function, Interface, DerivedType
from ipywidgets import VBox, HBox, Combobox, Dropdown, Text, Select, Output, HTML, IntSlider, Label, Button
import ipycytoscape


out = Output()

class Explorer(VBox):
    def __init__(self, forest, **kwargs):

        super().__init__(**kwargs)

        out.clear_output()

        self.forest = forest
        self.store = forest.registry._store

        # Search and category selection widgets
        self.search_box = Text(
            placeholder="Type name",
            description="Search:",
            layout={'width': '400px'},
            style={"description_width": "100px"}
        )
        self.search_box.observe(self.on_search_box_change, names='value', type='change')

        self.name_selector = Select(
            options=[],
            layout={'width': '400px'},
            rows=10,
        )
        self.name_selector.unfiltered_options = []
        self.name_selector.observe(self.on_name_selection_change, names='value', type='change')

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
        self.category_picker.observe(self.update_category, names='value', type='change')

        # Dependency graph configuration widgets
        self.depth_slider = IntSlider(
            value=1,
            min=1,
            max=5,
            step=1,
            description='Graph Depth:',
            layout={'width': '400px'},
            style={"description_width": "100px"}
        )
        self.depth_slider.observe(self.on_depth_change, names='value', type='change')

        # Graph widget (will be created when requested)
        self.create_graph_widget()
        self.graph_visible = True

        # Initial layout without graph
        self.graph_section = VBox([
            self.graph_widget
        ])

        # Button section for graph controls
        self.graph_controls = HBox([
            HTML("<span style='margin-left: 10px; margin-right: 10px;'>|</span>"),
            Label("Graph Controls:", layout={'width': '100px'}),
            HTML("<span style='margin-left: 5px;'></span>")
        ])

        # Layout all widgets
        self.children = [
            self.category_picker,
            self.search_box,
            self.name_selector,
            HTML("<hr>"),
            self.graph_controls,
            self.graph_section,
            out
        ]

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

    def gen_subgraph(self, routine, depth=1):
        subgraph = nx.DiGraph()
        subgraph.add_node(routine)
        for caller in routine.callers:
            subgraph.add_edge(caller, routine)
        for callee in routine.callees:
            subgraph.add_edge(routine, callee)
        return subgraph

    def update_graph_display(self):
        """Update the dependency graph display based on current selection."""
        if not self.graph_widget or not self.graph_visible:
            return
            
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
        depth = self.depth_slider.value
        subgraph = self.gen_subgraph(center_node, depth)

        self.graph_widget.graph.clear()
        
        # Add nodes
        for node in subgraph.nodes():
            node_data = {
                'id': node.name,
                'label': node.name,
                'type': 'subroutine' if isinstance(node, Subroutine) else 
                        'function' if isinstance(node, Function) else 
                        'interface' if isinstance(node, Interface) else 'other'
            }
            
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
            cytoscape_edge = ipycytoscape.Edge(data=edge_data)
            self.graph_widget.graph.add_edge(cytoscape_edge)
        
        # Apply layout
        self.graph_widget.set_layout(name='cose', animate=True)

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
        
        # Clear graph when category changes (only if visible)
        if self.graph_visible and self.graph_widget:
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
        if self.graph_visible:
            self.update_graph_display()

    @out.capture() 
    def on_depth_change(self, change):
        """Handle depth slider changes."""
        if self.graph_visible:
            self.update_graph_display()

    def create_graph_widget(self):
        """Create and configure the graph widget."""
        self.graph_widget = ipycytoscape.CytoscapeWidget()
        self.graph_widget.layout = {'width': '800px', 'height': '600px'}
        self.graph_widget.on('node', 'click', self.on_node_click)
        
        # Configure graph appearance
        self.graph_widget.set_style([
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
                'selector': 'node[type="subroutine"]',
                'style': {
                    'background-color': "#ff8f83"
                }
            },
            {
                'selector': 'node[type="function"]',
                'style': {
                    'background-color': "#ffb758"
                }
            },
            {
                'selector': 'node[type="interface"]',
                'style': {
                    'background-color': "#fff756"
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
            }
        ])

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
