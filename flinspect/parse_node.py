from abc import ABC, abstractmethod

class Node(ABC):
    """Base class for all nodes in the parse tree representation."""

    def __init__(self, name, container=None):
        self.name = name
        self.container = container
    
    def __str__(self):
        return self.name
    
    def __repr__(self):
        return f"{self.__class__.__name__}('{self.name}')"
    
    @classmethod
    @abstractmethod
    def key(cls, *args, **kwargs):
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
    parse_tree_path : Path
        The path to the parse tree file from which this program unit was read.
    """

    def __init__(self, name):
        super().__init__(name)
        self.used_modules = {} # Keys are module objects and values are lists of names used from the module
        self.subroutines = set()
        self.functions = set()
        self.interfaces = set()
        self.parse_tree_path = None # To be set when the parse tree is read

    @classmethod
    def key(cls, name):
        return name

class Module(ProgramUnit):
    """Class representing a Fortran module."""
    pass

class Program(ProgramUnit):
    """Class representing a Fortran program."""
    def __init__(self, name):
        super().__init__(name)
        self.callees = set()
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
    def __init__(self, name, program_unit, parent=None):
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

        assert '::' not in name, "Callable name should not contain '::'"
        super().__init__(name)
        self.program_unit = program_unit
        self.used_modules = {} # Keys are module objects and values are lists of names used from the module
        self.parent = parent # Parent callable if nested, else None
        self.callees = set()
        self.callers = set()

    @classmethod
    def key(cls, name, program_unit, parent=None):
        if parent is None:
            return f"{program_unit.name}::{name}"
        return f"{program_unit.name}::{parent.name}::{name}"

class Subroutine(Callable):
    """Class representing a Fortran subroutine."""
    pass

class Function(Callable):
    """Class representing a Fortran function."""
    pass

class Interface(Node):
    """Class representing a Fortran interface block."""
    def __init__(self, name, program_unit):
        super().__init__(name)
        self.program_unit = program_unit
        self.program_unit.interfaces.add(self)
        self.procedures = set()
        self.callers = set()

    @classmethod
    def key(cls, name, program_unit):
        return f"{program_unit.name}::{name}"