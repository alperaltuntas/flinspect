import networkx as nx
from pathlib import Path

from flinspect.ingest_parse_tree import extract_all_modules
from flinspect.utils import get_module_paths



def gen_dependency_graph(dirs):


    # dirs must be str, Path, or list of str/Path
    if isinstance(dirs, (str, Path)):
        dirs = [dirs]
    elif isinstance(dirs, list):
        assert all(isinstance(p, (str, Path)) for p in dirs), \
            f"Expected a list of str or Path objects, got {type(dirs)}"
    else:
        raise TypeError(f"Expected a list of paths, str, or Path object, got {type(dirs)}")

    dirs = [Path(p) for p in dirs]

    modules = []
    for dir in dirs:
        modules.extend(extract_all_modules(dir))

    path_names= {}
    for dir in dirs:
        path_names_file = dir / "path_names"
        with open(path_names_file) as f:
            for line in f:
                src_file_path = Path(line.strip())
                path_names[src_file_path.stem.lower()] = src_file_path.as_posix()

    # Now generate a NetworkX directed graph from the dependencies
    G = nx.DiGraph()
    for module in modules:

        # Set the node attributes
        node_color, edge_color = "lightseagreen", "turquoise" # for core MOM6
        if "/MARBL/" in path_names[module.file_name.lower()]:
            node_color, edge_color = "purple", "orchid"
        elif "/CVMix-src/" in path_names[module.file_name.lower()]:
            node_color, edge_color = "orangered", "coral"
        elif "/GSW-Fortran/" in path_names[module.file_name.lower()]:
            node_color, edge_color = "darkgrey", "grey"
        elif "/FMS/" in path_names[module.file_name.lower()]:
            node_color, edge_color = "orange", "gold"
        elif "/config_src/infra" in path_names[module.file_name.lower()]:
            node_color, edge_color = "blue", "lightblue"
        
        G.add_node(module.name, color=node_color)
        for used_module in module.used_modules:
            G.add_edge(module.name, used_module.name, color=edge_color)

    return G

def main():
    path = Path("/glade/work/altuntas/turbo-stack/bin/flangparse/FMS/")
    dependencies = gen_dependency_graph_dict(path)

    # Create a directed graph from the dependencies
    G = nx.DiGraph()
    for module, used_modules in dependencies.items():
        for used_module in used_modules:
            G.add_edge(module, used_module) 
    
    # Draw the graph
    import matplotlib.pyplot as plt
    plt.figure(figsize=(12, 8))
    pos = nx.spring_layout(G, seed=42)  # positions for all nodes
    nx.draw(G, pos, with_labels=True, node_size=2000, node_color='lightblue', font_size=10, font_color='black', font_weight='bold', arrows=True, arrowsize=20)
    plt.title("Dependency Graph of Fortran Modules")
    plt.show()


if __name__ == "__main__":
    main()