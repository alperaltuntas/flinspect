import re
from pathlib import Path
from flinspect.utils import level
from abc import ABC, abstractmethod


class Node(ABC):
    """Base class for all nodes in the parse tree representation.
    The Node class implements a registry to return existing instances
    if they already exist. Otherwise, a new instance is created and stored
    in the registry, and returned.
    """

    def __new__(cls, *args, **kwargs):
        """Creates a new instance of the class or returns an existing one from the registry.
        Do not override in subclasses."""

        key = cls._make_key(*args, **kwargs)
        if key not in cls._registry:
            instance = super().__new__(cls)
            instance._initialize(*args, **kwargs)
            cls._registry[key] = instance
        return cls._registry[key]

    def __init_subclass__(cls, **kwargs):
        """Initializes the registry for each subclass. Do not override in subclasses."""

        super().__init_subclass__(**kwargs)
        cls._registry = {}

    def __str__(self):
        return self.name

    @classmethod
    @abstractmethod
    def _make_key(cls, *args, **kwargs):
        """Generates a unique key for the instance to be used in the registry.
        To be overriden in subclasses."""
        pass
    
    @abstractmethod
    def _initialize(self, *args, **kwargs):
        """Initializes the instance with the provided arguments. We use this method to set up
        the instance attributes as opposed to using __init__ directly because __init__ gets
        called every time the __new__ method is invoked, and we use the __new__ method to 
        return existing instances from the registry if they exist, so we need to ensure that
        the attributes are only set once (via this _initialize method and not __init_).
        To be overriden in subclasses."""
        pass

class ProgramUnit(Node):
    """Base class for program units: modules, programs, and subprograms.
    
    Attributes
    ----------
    name : str
        The name of the program unit.
    used_modules : dict
        A dictionary where keys are module objects and values are lists of names used from the module.
    subroutines : set
        A set of Subroutine instances defined in this program unit.
    functions : set
        A set of Function instances defined in this program unit.
    ptree_path : Path
        The path to the parse tree file from which this program unit was read.
    """

    def _initialize(self, name):
        self.name = name
        self.used_modules = {} # Keys are module objects and values are lists of names used from the module
        self.subroutines = set()
        self.functions = set()
        self.ptree_path = ''

    @classmethod
    def _make_key(cls, name):
        return name

class Module(ProgramUnit):
    """Class representing a Fortran module."""
    pass

class Program(ProgramUnit):
    """Class representing a Fortran program."""
    pass

class Subprogram(ProgramUnit):
    """Class representing a Fortran subprogram, i.e., a source file with no module or program statement."""
    pass

class Callable(Node):
    """Base class for subroutines and functions.
    
    Attributes
    ----------
    name : str
        The name of the subroutine or function.
    program_unit : ProgramUnit
        The program unit (module, program, or subprogram) that contains this callable.
    used_modules : dict
        A dictionary where keys are module objects and values are lists of names used from the module.
    parent : Callable or None
        The parent callable if this is a nested subroutine/function, otherwise None.
    callees : set
        A set of Callable instances that are called by this callable.
    callers : set
        A set of Callable instances that call this callable.
    """
    def _initialize(self, name, program_unit, parent=None):
        """Initializes a Callable instance.

        Parameters
        ----------
        name : str
            The name of the subroutine or function.
        program_unit : ProgramUnit
            The program unit (module, program, or subprogram) that contains this callable.
        parent : Callable, optional
            The parent callable if this is a nested subroutine/function, by default None.
        """

        self.name = name
        self.program_unit = program_unit
        self.used_modules = {} # Keys are module objects and values are lists of names used from the module
        self.parent = parent # Parent callable if nested, else None
        self.callees = set()
        self.callers = set()

    @classmethod
    def _make_key(cls, name, program_unit, parent=None):
        if parent is None:
            return f"{program_unit.name}::{name}"
        return f"{program_unit.name}::{parent.name}::{name}"

class Subroutine(Callable):
    """Class representing a Fortran subroutine."""
    pass

class Function(Callable):
    """Class representing a Fortran function."""
    pass


def read_ptree_file(file_path, sweep=0):
    """Reads a flang parse tree file and extracts module dependencies.
    
    Parameters:
    -----------
    file_path : str or Path
        The path to the parse tree file.
    sweep : int, optional
        The sweep number to determine the type of information to extract.
        Sweep 0 extracts module dependencies and subroutine ownership.
        Sweep 1 extracts subroutine/function call relationships.

    Returns:
    --------
    list
        A list of Module instances representing the modules found in the file.
    """

    assert isinstance(file_path, (str, Path)), f"Expected a string or Path object, got {type(file_path)}"
    file_path = Path(file_path)

    assert file_path.is_file(), f"Expected a file, got {file_path}"

    modules = []
    program = None  # Current program. Is None if we are not in a program unit.
    module = None   # Current module or subprogram (subprogram: a source file with no module|program statement).
    routine = None  # Current subroutine or function.
    outer_routine = None  # Outer routine is the one that contains the current subroutine/function.
    used_module = None  # Name of the last used module.

    # Define lambdas for convenience
    program_unit = lambda: module or program    # Returns the current program unit (program, module, or subprogram)
    scope = lambda: routine or program_unit()   # Returns the current lower scope (routine or program unit)

    with open(file_path, 'r') as f:

        line = f.readline().strip()
        if not line.startswith("======"):
            print(f"Warning: Skipping {file_path.name} as it does not start with proper header.")
            return []

        for line in f:
            line = line.strip()

            if sweep == 1:
                if "CallStmt" in line:
                    assert line.endswith("ActionStmt -> CallStmt"), f"CallStmt syntax not recognized in {file_path}, line: {line}"
                    assert program_unit() is not None, f"CallStmt found outside of a program unit in {file_path}, line: {line}"

                    line = f.readline().strip()
                    assert line.endswith("| Call"), f"CallStmt syntax not recognized in {file_path}, line: {line}"
                    
                    line = f.readline().strip()
                    if line.endswith("ProcedureDesignator -> ProcComponentRef -> Scalar -> StructureComponent"):
                        continue # todo: handle this case: structure component call, e.g., obj%method()
                    else:
                        m = re.search(r"ProcedureDesignator -> Name = '(\w+)'", line)
                        if not m:
                            raise ValueError(f"ProcedureDesignator syntax not recognized in {file_path}, line: {line}")
                        callee = m.group(1)

                    caller = routine
                    assert caller, f"CallStmt found without a preceding SubroutineStmt in {file_path} at line: {line}"
                    assert callee, f"CallStmt found without a subroutine name in {file_path} at line: {line}"

                    found_callee = False

                    # first, check if the callee is in the same program unit
                    for subr in program_unit().subroutines:
                        if callee == subr.name:
                            #print(f"Found callee {callee} in program unit {program_unit().name}")
                            caller.callees.add(subr)
                            subr.callers.add(caller)
                            found_callee = True
                            break

                    for used_module, used_callables in program_unit().used_modules.items():
                        if found_callee:
                            break
                        if used_callables and '*' in used_callables: # entire module is used
                            for subr in used_module.subroutines:
                                if callee == subr.name:
                                    #print(f"Found callee {callee} in module {used_module.name}")
                                    caller.callees.add(subr)
                                    subr.callers.add(caller)
                                    found_callee = True
                                break
                        else:
                            for name in used_callables:
                                if callee == name:
                                    for subr in used_module.subroutines:
                                        if callee == subr.name:
                                            #print(f"Found callee {callee} in module {used_module.name} via Only clause")
                                            caller.callees.add(subr)
                                            subr.callers.add(caller)
                                            found_callee = True
                                        break
                                    break

                    if not found_callee:
                        print(f"Warning: Could not find callee {callee} in any used module of {program_unit().name} for call in {caller.name} at line: {line}")

                    # Find the subroutine
                    #print(module.name)
                    #module = routine.program_unit
                    #print(module.name)

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

                assert program_unit() is not None, f"FunctionStmt found without a preceding ModuleStmt or ProgramStmt in {file_path}"

                if is_function:
                    routine = Function(name, program_unit(), outer_routine)
                    if outer_routine is None:
                        program_unit().functions.add(routine)
                else:
                    routine = Subroutine(name, program_unit(), outer_routine)
                    if outer_routine is None:
                        program_unit().subroutines.add(routine)

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
            
            elif "| Only" in line:

                only_name = None
                if (m := re.search(r"Only -> GenericSpec -> Name = '(\w+)'", line)):
                    only_name = m.group(1)
                elif  (m := re.search(r"Only -> GenericSpec -> DefinedOperator -> IntrinsicOperator = (\w+)", line)):
                    only_name = m.group(1)
                elif (m := re.search(r"Only -> GenericSpec -> Assignment", line)):
                    only_name = "assignment(=)"
                elif (m := re.search(r"Only -> Rename -> Names", line)):
                    line = f.readline().strip()
                    m = re.search(r"Name = '(\w+)'", line)
                    assert m, f"Only Rename syntax not recognized in {file_path}, line: {line}"
                    line = f.readline().strip()
                    m = re.search(r"Name = '(\w+)'", line)
                    assert m, f"Only Rename syntax not recognized in {file_path}, line: {line}"
                    only_name = m.group(1)
                else:
                    raise ValueError(f"Only syntax not recognized in {file_path}, line: {line}")

                assert used_module, f"Only clause found without a preceding UseStmt in {file_path} at line: {line}"
                used_module_only_list = scope().used_modules[used_module]
                if used_module_only_list and used_module_only_list[0] == '*':
                    pass
                else:
                    used_module_only_list.append(only_name)

            elif "| UseStmt" in line:
                m = re.search(r"UseStmt *$", line)
                assert m, f"UseStmt syntax not recognized in {file_path}"
                line = f.readline().strip()
                if re.search(r"\bModuleNature", line):
                    line = f.readline().strip()
                m = re.search(r"Name = '(\w+)'", line)
                assert m, f"UseStmt Name syntax not recognized in {file_path}, line: {line}"
                used_module_name = m.group(1)
                used_module = Module(used_module_name)
                scope().used_modules[used_module] = []

            elif "| ModuleStmt" in line:
                m = re.search(r"ModuleStmt -> Name = '(\w+)'", line)
                assert m, f"ModuleStmt syntax not recognized in {file_path}"
                assert not module, f"ModuleStmt found without a preceding EndModuleStmt in {file_path}"
                module_name = m.group(1)
                module = Module(module_name)
                module.ptree_path = file_path
                modules.append(module)

            elif "| EndModuleStmt" in line:
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
            
            # end of checking content of this line. Apply cleanups if necessary
            # ======================================================================================

            elif used_module:
                # This is the case where we had a "UseStmt" in the previous line, which apparently
                # is not followed by an "Only" clause, so we just add the entire module.
                scope().used_modules[used_module] = ['*']
                used_module = None


    return modules
