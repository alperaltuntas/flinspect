from dataclasses import dataclass
from flinspect.parse_node import Module, Program, Subprogram, Subroutine, Function

@dataclass
class ParseState:
    """Class to hold the current (changing) state while parsing a parse tree file."""
    program = None
    subprogram: Subprogram | None = None
    module: Module | None = None
    used_module: Module | None = None
    routine: Subroutine | None = None
    parent_routine: Subroutine | None = None

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