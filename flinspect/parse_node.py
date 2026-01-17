from abc import ABC, abstractmethod

class Node(ABC):
    """Base class for all nodes in the parse tree representation."""

    def __init__(self, name):
        self.name = name
    
    def __str__(self):
        return self.name
    
    def __repr__(self):
        return f"{self.__class__.__name__}('{self.name}')"
    
    @classmethod
    @abstractmethod
    def key(cls, *args, **kwargs):
        pass

class Scope(Node):
    """Base class for scopes: modules, programs, subprograms, subroutines, and functions.

    Attributes
    ----------
    name : str
        The name of the scope.
    used_names_lists : dict
        A dictionary where keys are module objects and values are lists of names used from the module.
    used_renames_lists : dict
        A dictionary where keys are module objects and values are lists of (alias, name) tuples
    """
    def __init__(self, name):
        super().__init__(name)
        self.used_names_lists = {} # Keys are module objects and values are lists of names used from the module
        self.used_renames_lists = {} # Keys are module objects and values are lists of (alias, name) tuples

    @property
    def used_module_names(self):
        """Returns a list of module names used by this scope."""
        if len(self.used_renames_lists) == 0:
            return list(self.used_names_lists.keys())
        # If there are used renames, include them
        union = set(self.used_names_lists.keys()).union(set(self.used_renames_lists.keys()))
        return list(union)


class ProgramUnit(Scope):
    """Base class for program units: modules, programs, and subprograms.
    
    Attributes
    ----------
    name : str
        The name of the program unit.
    subroutines : set
        A set of Subroutine instances defined in this program unit.
    functions : set
        A set of Function instances defined in this program unit.
    parse_tree_path : Path
        The path to the parse tree file from which this program unit was read.
    """

    def __init__(self, name):
        super().__init__(name)
        self.subroutines = set()
        self.functions = set()
        self.interfaces = set()
        self.derived_types = set()
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

class Callable(Scope):
    """Base class for subroutines and functions.
    
    Attributes
    ----------
    name : str
        The name of the subroutine or function.
    program_unit : ProgramUnit
        The program unit (module, program, or subprogram) that contains this callable.
    parent : Callable or None
        The parent callable if this is a nested subroutine/function, otherwise None.
    callees : set
        A set of Callable instances that are called by this callable.
    callers : set
        A set of Callable instances that call this callable.
    num_args : int or None
        The total number of arguments in the callable's signature (derived from arg_types).
        None if arg_types not yet parsed.
    num_required_args : int or None
        The number of required (non-optional) arguments. None if not yet parsed.
    arg_types : list or None
        List of argument types in order (e.g., ['integer', 'character', 'logical']).
        None if not yet parsed.
    arg_ranks : list or None
        List of argument ranks in order (0 for scalar, 1+ for arrays).
        None if not yet parsed.
    arg_kinds : list or None
        List of argument kind specifiers in order (e.g., ['r8_kind', 'i4_kind', None]).
        None for the whole list if not yet parsed, or None for individual entries if unknown.
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
        self.parent = parent # Parent callable if nested, else None
        self.callees = set()
        self.callers = set()
        self.derived_types = set()
        self.num_required_args = None  # Number of required (non-optional) arguments
        self.arg_types = None  # List of argument types in order
        self.arg_ranks = None  # List of argument ranks in order (0=scalar, 1+=array)
        self.arg_kinds = None  # List of argument kind specifiers (e.g., 'r8_kind', 'i4_kind')

    @property
    def num_args(self):
        """Total number of arguments, derived from arg_types length."""
        return len(self.arg_types) if self.arg_types is not None else None

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

class DerivedType(Node):
    """Class representing a Fortran derived type."""
    def __init__(self, name, scope):
        super().__init__(name)
        assert hasattr(scope, 'derived_types'), self.msg("Current scope cannot hold derived types")
        self.scope = scope
        self.scope.derived_types.add(self)
        self.callees = set()

    @classmethod
    def key(cls, name, scope):
        return f"{scope.name}::{name}"
