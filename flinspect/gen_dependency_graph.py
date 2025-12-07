import networkx as nx
from pathlib import Path

from flinspect.parse_tree_parser import ParseTreeParser

def gen_call_graph(paths):
    """Generates a directed graph of subroutine/function call dependencies.

    Parameters
    ----------
    paths : list of str or Path
        List of paths to Python files or directories containing parse tree files.

    Returns
    -------
    networkx.DiGraph
        A directed graph where nodes are subroutine/function names and edges represent call dependencies.
    """

    if isinstance(paths, (str, Path)):
        paths = [paths]
    elif isinstance(paths, list):
        assert all(isinstance(p, (str, Path)) for p in paths), \
            f"Expected a list of str or Path objects, got {type(paths)}"
    else:
        raise TypeError(f"Expected a list of paths, str, or Path object, got {type(paths)}")

    # Sweep 0: extract module dependencies and subroutine ownership

    modules = []
    for path in paths:
        with ParseTreeParser(path) as ptp:
            ptp.parse()
            modules.extend(ptp.modules)

    g_modules = nx.DiGraph()
    for module in modules:
        g_modules.add_node(module, source_name=module.ptree_path.stem)
        # Add edges for for used modules at the module level
        for used_module in module.used_modules:
            g_modules.add_edge(module, used_module)
        # Add edges for used modules in subroutines and functions
        for subroutine in module.subroutines:
            for used_module in subroutine.used_modules:
                g_modules.add_edge(module, used_module)
        for function in module.functions:
            for used_module in function.used_modules:
                g_modules.add_edge(module, used_module)

    # topologically sort the modules
    sorted_modules = list(nx.topological_sort(g_modules))

    # Sweep 1: read subroutine/function call relationships in a topological order of modules
    skipped_modules  = []
    for module in sorted_modules:
        ptree_path = module.ptree_path
        if ptree_path:
            with ParseTreeParser(ptree_path) as ptp:
                ptp.parse(sweep=1)
        else:
            skipped_modules.append(module)

    if skipped_modules:
        print(f"Warning: The following modules were skipped due to missing parse tree paths:\n\t{', '.join(m.name for m in skipped_modules)}")
    

def gen_data_structure_hierarchy(paths):
    """Generate a hierarchy of data structures from the parse tree files.
    The resulting graph captures the relationships between data structures
    as well as between their owners (modules, programs, subroutines etc.) and 
    clients (subroutines, functions, etc.). """
    pass # Placeholder for future implementation

def gen_module_dependency_graph(paths):
    """Generates a directed graph of module dependencies.

    Parameters
    ----------
    paths : list of str or Path
        List of paths to Python files or directories containing parse tree files.

    Returns
    -------
    networkx.DiGraph
        A directed graph where nodes are module names and edges represent dependencies.
        Each node has an attribute 'source_name' indicating the original file name of the module.
    """

    if isinstance(paths, (str, Path)):
        paths = [paths]
    elif isinstance(paths, list):
        assert all(isinstance(p, (str, Path)) for p in paths), \
            f"Expected a list of str or Path objects, got {type(paths)}"
    else:
        raise TypeError(f"Expected a list of paths, str, or Path object, got {type(paths)}")

    modules = []
    for path in paths:
        with ParseTreeParser(path) as ptp:
            ptp.parse()
            modules.extend(ptp.modules)

    g_modules = nx.DiGraph()
    for module in modules:
        g_modules.add_node(module, source_name=module.ptree_path.stem)
        # Add edges for for used modules at the module level
        for used_module in module.used_modules:
            g_modules.add_edge(module, used_module)
        # Add edges for used modules in subroutines and functions
        for subroutine in module.subroutines:
            for used_module in subroutine.used_modules:
                g_modules.add_edge(module, used_module)
        for function in module.functions:
            for used_module in function.used_modules:
                g_modules.add_edge(module, used_module)
    
    return g_modules
