from dataclasses import dataclass
from os import name

from flinspect.parse_node import Module, Program, Subprogram, Subroutine, Function, Interface, DerivedType

@dataclass
class NodeRegistry:
    """A registry that interns node objects (Module, Program, Subroutine, etc.)
    so that each named node is created at most once per registry instance.

    A single NodeRegistry may be shared across multiple parse trees (a forest)
    to ensure consistent, unique node objects for the entire parsed collection.

    This also enables a functional-style workflow: the same node object is returned
    each time it is requested, even if the node has not yet been fully defined.
    """

    def __init__(self):
        self._store = {}

    def _get_or_create(self, cls, *args, **kwargs):
        key = cls.key(*args, **kwargs)
        if cls not in self._store:
            self._store[cls] = {}
        if key not in self._store[cls]:
            assert isinstance(key, str), f"Expected key to be str, got {type(key)}"
            self._store[cls][key] = cls(*args, **kwargs)
        return self._store[cls][key]

    def Module(self, *args, **kwargs) -> Module:
        return self._get_or_create(Module, *args, **kwargs)

    def Program(self, *args, **kwargs) -> Program:
        return self._get_or_create(Program, *args, **kwargs)

    def Subprogram(self, *args, **kwargs) -> Subprogram:
        return self._get_or_create(Subprogram, *args, **kwargs)

    def Subroutine(self, *args, **kwargs) -> Subroutine:
        return self._get_or_create(Subroutine, *args, **kwargs)

    def Function(self, *args, **kwargs) -> Function:
        return self._get_or_create(Function, *args, **kwargs)

    def Interface(self, *args, **kwargs) -> Interface:
        return self._get_or_create(Interface, *args, **kwargs)

    def DerivedType(self, *args, **kwargs) -> DerivedType:
        return self._get_or_create(DerivedType, *args, **kwargs)

    @property
    def modules(self):
        return self._store.get(Module, {}).values()

    @property
    def programs(self):
        return self._store.get(Program, {}).values()

    @property
    def subprograms(self):
        return self._store.get(Subprogram, {}).values()

    @property
    def subroutines(self):
        return self._store.get(Subroutine, {}).values()

    @property
    def functions(self):
        return self._store.get(Function, {}).values()

    @property
    def interfaces(self):
        return self._store.get(Interface, {}).values()
    
    @property
    def derived_types(self):
        return self._store.get(DerivedType, {}).values()

    def get_subroutine_by_name(self, name):
        # look for keys ending with the given name
        subroutines = []
        for key, subroutine in self._store[Subroutine].items():
             if key.endswith(name):
                subroutines.append((name, subroutine))
        if len(subroutines) == 1:
            return subroutines[0][1]
        elif len(subroutines) > 1:
            raise ValueError(f"Multiple subroutines found with name ending '{name}': {[s[0] for s in subroutines]}")
        else:
            return None
