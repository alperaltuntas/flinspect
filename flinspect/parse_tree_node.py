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
        self.interfaces = set()
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


class Interface(Callable):
    """Class representing a Fortran interface block."""

    def _initialize(self, name, program_unit):
        super()._initialize(name, program_unit)
        self.procedures = [] # List of Callable instances declared in this interface
