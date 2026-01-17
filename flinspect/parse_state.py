from dataclasses import dataclass
from flinspect.parse_node import Module, Subprogram, Subroutine, Function, DerivedType


@dataclass
class ParseState:
    """Class to hold the current (changing) state while parsing a parse tree file."""
    program = None
    subprogram: Subprogram | None = None
    module: Module | None = None
    used_module: Module | None = None
    routine: Subroutine | None = None
    parent_routine: Subroutine | None = None
    derived_type: DerivedType | None = None

    @property
    def program_unit(self):
        return self.module or self.subprogram or self.program

    @property
    def scope(self):
        return self.routine or self.program_unit

    @property
    def in_function(self):
        return isinstance(self.routine, Function)

    @property
    def in_subroutine(self):
        return isinstance(self.routine, Subroutine)

    @property
    def in_derived_type(self):
        return self.derived_type is not None

    def get_scope_key(self) -> str:
        """Get a unique key for the current scope."""
        if self.routine:
            if self.parent_routine:
                return f"{self.program_unit.name}::{self.parent_routine.name}::{self.routine.name}"
            return f"{self.program_unit.name}::{self.routine.name}"
        if self.program_unit:
            return self.program_unit.name
        return "__global__"