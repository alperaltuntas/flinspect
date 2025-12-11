from dataclasses import dataclass
from os import name

from flinspect.parse_node import Module, Program, Subprogram, Subroutine, Function

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
