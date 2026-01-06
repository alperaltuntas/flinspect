import networkx as nx
from pathlib import Path

from flinspect.parse_tree import ParseTree
from flinspect.node_registry import NodeRegistry

class ParseForest:
    """A class representing a collection of parse trees for program units (source files).
    """

    def __init__(self, parse_tree_paths):
        """Initializes the ParseForest by parsing the given parse tree files.
        
        Parameters
        ----------
        parse_tree_paths : list of str or Path
            List of paths to parse tree files or directories containing parse tree files.
        """

        if isinstance(parse_tree_paths, (str, Path)):
            parse_tree_paths = [parse_tree_paths]
        elif isinstance(parse_tree_paths, list):
            assert all(isinstance(p, (str, Path)) for p in parse_tree_paths), \
                f"Expected a list of str or Path objects, got {type(parse_tree_paths)}"
        else:
            raise TypeError(f"Expected a list of paths, str, or Path object, got {type(parse_tree_paths)}")
       
        self.registry = NodeRegistry()
        self.trees = []

        # Parse structure:
        for path in parse_tree_paths:
            tree = ParseTree(path, self.registry)
            tree.parse_structure()
            self.trees.append(tree)

    def get_module_dependency_graph(self):
        """Generates a directed graph of module dependencies.

        Returns
        -------
        networkx.DiGraph
            A directed graph where nodes are module names and edges represent 'uses' relationships.
        """


        skipped_modules  = []

        g = nx.DiGraph()
        for module in self.registry.modules:
            if module.parse_tree_path is None:
                skipped_modules.append(module)
                continue # external module, e.g., netcdf, mpi, etc. so skip
            g.add_node(module, source_name=module.parse_tree_path.stem)
            # Add edges for used modules at the module level
            for used_module in module.used_module_names:
                g.add_edge(module, used_module)
            # Add edges for used modules in subroutines and functions
            for subroutine in module.subroutines:
                for used_module in subroutine.used_module_names:
                    g.add_edge(module, used_module)
            for function in module.functions:
                for used_module in function.used_module_names:
                    g.add_edge(module, used_module)

        print (f"Skipped {len(skipped_modules)} modules with unknown parse tree paths: {[m.name for m in skipped_modules]}")
    
        return g


    def get_call_graph(self):

        for tree in self.trees:
            tree.parse_interfaces()

        # Parse call relationships:
        self.unfound_subroutine_calls = []
        self.unfound_function_calls = []
        for tree in self.trees:
            uc, uf = tree.parse_calls()
            self.unfound_subroutine_calls.extend(uc)
            self.unfound_function_calls.extend(uf)

        print(f"Total unfound calls across all parse trees: {len(self.unfound_subroutine_calls)}")
        print(f"Total unfound function calls across all parse trees: {len(self.unfound_function_calls)}")

        g = nx.DiGraph()
        for subroutine in self.registry.subroutines:
            g.add_node(subroutine, type='subroutine', program_unit=subroutine.program_unit.name)
        for function in self.registry.functions:
            g.add_node(function, type='function', program_unit=function.program_unit.name)
        for subroutine in self.registry.subroutines:
            for callee in subroutine.callees:
                g.add_edge(subroutine, callee)
        for function in self.registry.functions:
            for callee in function.callees:
                g.add_edge(function, callee)
        
        # also connect subroutines/functions to (all) subroutines/functions in interfaces that they call:
        for interface in self.registry.interfaces:
            for caller in interface.callers:
                for callee in interface.procedures:
                    #print(f"Adding edge from {caller.name} to interface procedure {callee.name}")
                    g.add_edge(caller, callee)

        return g