import re
from collections import defaultdict
from pathlib import Path


class Node:
    def __init__(self):
        # Prevent instantiation of Node directly, so as to make sure only 
        # one instance of an object with same name is created.
        raise RuntimeError("Call .instance() to create or get an instance of this class.")

class Module(Node):
    _instances = {}

    @classmethod
    def instance(cls, name):
        if name not in cls._instances:
            instance = object.__new__(cls)
            instance.name = name
            instance.file_name = ""
            instance.used_modules = set()
            cls._instances[name] = instance
        return cls._instances[name]
    

def read_ptree_file(file_path):
    """Reads a flang parse tree file and extracts module dependencies.
    
    Parameters:
    -----------
    file_path : str or Path
        The path to the parse tree file.

    Returns:
    --------
    list
        A list of Module instances representing the modules found in the file.
    """

    assert isinstance(file_path, (str, Path)), f"Expected a string or Path object, got {type(file_path)}"
    file_path = Path(file_path)

    assert file_path.is_file(), f"Expected a file, got {file_path}"

    modules = []
    module = None

    with open(file_path, 'r') as f:
        for line in f:
            if re.search(r"\bModuleStmt", line):
                m = re.search(r"ModuleStmt -> Name = '(\w+)'", line)
                assert m, f"ModuleStmt syntax not recognized in {file_path}"
                module_name = m.group(1)
                module = Module.instance(module_name)
                module.file_name = file_path.stem
                modules.append(module)

            elif re.search(r"\bUseStmt", line):
                m = re.search(r"UseStmt *$", line)
                assert m, f"UseStmt syntax not recognized in {file_path}"
                line = f.readline()
                if re.search(r"\bModuleNature", line):
                    line = f.readline()
                m = re.search(r"Name = '(\w+)'", line)
                assert m, f"UseStmt Name syntax not recognized in {file_path}, line: {line.strip()}"
                used_module_name = m.group(1)
                used_module = Module.instance(used_module_name)
                if module:
                    module.used_modules.add(used_module)
                else:
                    pass # todo: handle this case

            elif re.search(r"\bEndModuleStmt", line):
                assert module, f"EndModuleStmt found without a preceding ModuleStmt in {file_path}"
                m = re.search(r"EndModuleStmt -> Name = '(\w+)'", line)
                if m:
                    end_module_name = m.group(1)
                    assert end_module_name == module.name, f"EndModuleStmt name {end_module_name} does not match ModuleStmt name {module.name} in {file_path}"
                module = None

    return modules


def extract_all_modules(dir):
    """
    Extracts all modules from Fortran parse tree files in a given build directory.
    The function searches for files with the suffix '_ptree' in the specified directory,
    reads each file, and extracts module dependencies using the `read_ptree_file` function.

    Parameters:
    -----------
    dir : str or Path
        The directory containing the Fortran parse tree files or a single file with '_ptree'
        suffix.

    Returns:
    --------
    list
        A list of Module instances representing the modules found in the files.
    """

    assert isinstance(dir, (str, Path)), f"Expected a string or Path object, got {type(dir)}"
    dir = Path(dir)
    assert dir.is_dir(), f"Expected a directory, got {dir}"

    parse_tree_files = list(dir.glob("*_ptree"))
    if not parse_tree_files:
        raise ValueError(f"No parse tree files found in {dir}. Expected files with '_ptree' suffix.")

    modules = []
    for file in parse_tree_files:
        #print(f"Processing {file}...")
        modules.extend(read_ptree_file(file))

    return modules
    


