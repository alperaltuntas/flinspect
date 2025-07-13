import networkx as nx
from pathlib import Path

from flinspect.ingest_parse_tree import read_ptree_file


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
        modules.extend(read_ptree_file(path))

    g_modules = nx.DiGraph()
    for module in modules:
        g_modules.add_node(module, source_name=module.ptree_path.stem)
        for used_module in module.used_modules:
            g_modules.add_edge(module, used_module)
    
    return g_modules
