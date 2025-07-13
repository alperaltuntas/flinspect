import re
from pathlib import Path
from flinspect.utils import level


class Node:
    """Base class for nodes in the parse tree."""

    def __new__(cls, *args, **kwargs):
        key = cls._make_key(*args, **kwargs)
        if key not in cls._registry:
            instance = super().__new__(cls)
            instance._initialize(*args, **kwargs)
            cls._registry[key] = instance
        return cls._registry[key]

    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._registry = {}

    def __str__(self):
        return self.name

    @classmethod
    def _make_key(cls, *args, **kwargs):
        """Generates a unique key for the instance to be used in the registry."""
        raise NotImplementedError("Subclasses must implement _make_key")
    
    def _initialize(self, *args, **kwargs):
        """Initializes the instance with the provided arguments. We use this method to set up
        the instance attributes as opposed to using __init__ directly because __init__ gets
        called every time the __new__ method is invoked, and we use the __new__ method to 
        return existing instances from the registry if they exist, so we need to ensure that
        the attributes are only set once (via this _initialize method and not __init_)."""
        raise NotImplementedError("Subclasses must implement _initialize")

class ProgramUnit(Node):
    def _initialize(self, name):
        self.name = name
        self.used_modules = set()
        self.subroutines = set()
        self.functions = set()
        self.ptree_path = ''

    @classmethod
    def _make_key(cls, name):
        return name

class Module(ProgramUnit): pass
class Program(ProgramUnit): pass
class Subprogram(ProgramUnit): pass

class Callable(Node):
    def _initialize(self, name, program_unit, parent=None):
        self.name = name
        self.program_unit = program_unit
        self.used_modules = set()
        self.parent = parent

    @classmethod
    def _make_key(cls, name, program_unit, parent=None):
        return f"{program_unit.name}::{name}"

class Subroutine(Callable): pass
class Function(Callable): pass


def read_ptree_file(file_path, sweep=0):
    """Reads a flang parse tree file and extracts module dependencies.
    
    Parameters:
    -----------
    file_path : str or Path
        The path to the parse tree file.
    sweep : int, optional
        The sweep number to determine the type of information to extract.

    Returns:
    --------
    list
        A list of Module instances representing the modules found in the file.
    """

    assert isinstance(file_path, (str, Path)), f"Expected a string or Path object, got {type(file_path)}"
    file_path = Path(file_path)

    assert file_path.is_file(), f"Expected a file, got {file_path}"

    modules = []
    program = None # this is set only when the file corresponds to a main program
    module = None
    routine = None # soubroutine or function
    outer_routine = None # outer routine is the one that contains the current subroutine/function

    with open(file_path, 'r') as f:

        line = f.readline().strip()
        if not line.startswith("======"):
            print(f"Warning: Skipping {file_path.name} as it does not start with proper header.")
            return []

        for line in f:
            line = line.strip()

            if (is_function := line.endswith("| FunctionStmt")) or \
                 (line.endswith("| SubroutineStmt")):

                line = f.readline().strip()
                l = level(line)
                while re.search(r"\bPrefix", line) or level(line) > l:
                    line = f.readline().strip()
                res = re.search(r"Name = '(\w+)'", line)
                if not res:
                    raise ValueError(f"FunctionStmt syntax not recognized in {file_path}, line: {line}")
                name = res.group(1)

                if routine is not None:
                    assert outer_routine is None, f"More than one level of routine nesting found in {file_path}"
                outer_routine = routine

                program_unit = module or program
                assert program_unit is not None, f"FunctionStmt found without a preceding ModuleStmt or ProgramStmt in {file_path}"

                if is_function:
                    routine = Function(name, program_unit, outer_routine)
                    program_unit.functions.add(routine)
                else:
                    routine = Subroutine(name, program_unit, outer_routine)
                    program_unit.subroutines.add(routine)

            elif "| EndFunctionStmt" in line:
                assert type(routine) is Function, f"EndFunctionStmt found without a preceding FunctionStmt in {file_path}"
                m = re.search(r"EndFunctionStmt -> Name = '(\w+)'", line)
                if m:
                    end_function_name = m.group(1)
                    assert end_function_name == routine.name, f"EndFunctionStmt name {end_function_name} does not match FunctionStmt name {routine.name} in {file_path}"
                routine = outer_routine
                outer_routine = None

            elif "| EndSubroutineStmt" in line:
                assert type(routine) is Subroutine, f"EndSubroutineStmt found without a preceding SubroutineStmt in {file_path}"
                m = re.search(r"EndSubroutineStmt -> Name = '(\w+)'", line)
                if m:
                    end_subroutine_name = m.group(1)
                    assert end_subroutine_name == routine.name, f"EndSubroutineStmt name {end_subroutine_name} does not match SubroutineStmt name {routine.name} in {file_path}"
                routine = outer_routine
                outer_routine = None                

            elif " UseStmt" in line:
                m = re.search(r"UseStmt *$", line)
                assert m, f"UseStmt syntax not recognized in {file_path}"
                line = f.readline().strip()
                if re.search(r"\bModuleNature", line):
                    line = f.readline().strip()
                m = re.search(r"Name = '(\w+)'", line)
                assert m, f"UseStmt Name syntax not recognized in {file_path}, line: {line}"
                used_module_name = m.group(1)
                used_module = Module(used_module_name)
                if module:
                    module.used_modules.add(used_module)
                elif program:
                    program.used_modules.add(used_module)

            elif " ModuleStmt" in line:
                m = re.search(r"ModuleStmt -> Name = '(\w+)'", line)
                assert m, f"ModuleStmt syntax not recognized in {file_path}"
                assert not module, f"ModuleStmt found without a preceding EndModuleStmt in {file_path}"
                module_name = m.group(1)
                module = Module(module_name)
                module.ptree_path = file_path
                modules.append(module)

            elif " EndModuleStmt" in line:
                assert module, f"EndModuleStmt found without a preceding ModuleStmt in {file_path}"
                m = re.search(r"EndModuleStmt -> Name = '(\w+)'", line)
                if m:
                    end_module_name = m.group(1)
                    assert end_module_name == module.name, f"EndModuleStmt name {end_module_name} does not match ModuleStmt name {module.name} in {file_path}"
                module = None
            
            elif line.startswith("Program -> ProgramUnit"):

                if line.startswith("Program -> ProgramUnit -> FunctionSubprogram") or \
                    line.startswith("Program -> ProgramUnit -> SubroutineSubprogram"): 
                    # A source file with no module or program statement
                    module = Subprogram(file_path.stem)

                elif line.startswith("Program -> ProgramUnit -> Module"):
                    # A module file. May contain multiple modules.
                    # Modules are handled in the "ModuleStmt" and "EndModuleStmt" cases above.
                    # So we just skip this line.
                    pass

                elif line.startswith("Program -> ProgramUnit -> MainProgram"):
                    line = f.readline().strip()
                    m = re.search(r"ProgramStmt -> Name = '(\w+)'", line)
                    if not m:
                        raise ValueError(f"ProgramStmt syntax not recognized in {file_path}, line: {line}")
                    program_name = m.group(1)
                    program = Program(program_name)
                    program.ptree_path = file_path
                
                else:
                    raise ValueError(f"ProgramUnit syntax not recognized in {file_path}, line: {line}")

    return modules
