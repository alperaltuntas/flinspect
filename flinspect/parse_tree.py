import re
from pathlib import Path
from flinspect.utils import level
from flinspect.parse_state import ParseState
from flinspect.node_registry import NodeRegistry


class ParseTree:
    """A class to read and parse a flang parse tree file."""

    def __init__(self, parse_tree_path, node_registry=None):

        assert isinstance(parse_tree_path, (str, Path)), f"Expected a string or Path object, got {type(parse_tree_path)}"
        parse_tree_path = Path(parse_tree_path)
        assert parse_tree_path.is_file(), f"Expected a file, got {parse_tree_path}"

        self.parse_tree_path = parse_tree_path

        # A registry to intern node objects
        self.nr = node_registry or NodeRegistry()

        # Internal iterator over lines in the parse tree file
        self._lines_generator = None 

        # Current line being parsed
        self.line = None
        self.next_line = None
        self.line_number = 0

        # Set of unfound calls during call resolution
        self.unfound_calls = []

        # Current state variables during parsing that get updated as we read lines
        self.curr = ParseState()

    def lines(self):
        """Iterator over lines in the parse tree file."""
        if self._lines_generator is None:
            def _iter_lines():
                with self.parse_tree_path.open('r') as f:
                    self.next_line = f.readline().strip()
                    for line in f:
                        self.line = self.next_line
                        self.next_line = line.strip()
                        self.line_number += 1
                        yield self.line
                    self.line = self.next_line
                    self.next_line = None
                    yield self.line
            self._lines_generator = _iter_lines()
        return self._lines_generator

    def read_next_line(self):
        """Reads the next line from the parse tree file and updates self.line."""
        next(self.lines())
        return self.line
    
    def peek_next_line(self):
        """Peeks at the next line without advancing the iterator."""
        return self.next_line
    
    def reset(self):
        """Resets the internal state for re-parsing."""
        self._lines_generator = None
        self.line = None
        self.next_line = None
        self.line_number = 0
        self.curr = ParseState()
        self.unfound_calls = []

    def msg(self, prefix):
        """Helper method to format error/warning messages."""
        return \
            f"{prefix}\n"\
            f"  file:{self.parse_tree_path}\n"\
            f"  line {self.line_number}: {self.line}"

    def parse_header(self):
        """Parses the header of the parse tree file to ensure it is valid."""
        assert self.line is None, self.msg("parse_header should be called at the beginning before reading any lines.")
        first = next(self.lines())
        if not first.startswith("======"):
            print(f"Warning: Skipping {self.parse_tree_path.name} as it does not start with proper header.")
            return False
        return True

    def parse_routine_begin(self):
        is_function = self.line.endswith("| FunctionStmt")
        is_subroutine = self.line.endswith("| SubroutineStmt")
        if not (is_function or is_subroutine):
            return False

        # advance to Name line, skipping Prefix blocks
        self.read_next_line()
        l = level(self.line)
        while re.search(r"\bPrefix", self.line) or level(self.line) > l:
            self.read_next_line()
        res = re.search(r"Name = '(\w+)'", self.line)
        if not res:
            raise ValueError(self.msg("FunctionStmt syntax not recognized"))
        name = res.group(1)

        if self.curr.routine is not None:
            assert self.curr.parent_routine is None, self.msg("More than one level of routine nesting found")
        self.curr.parent_routine = self.curr.routine

        assert self.curr.program_unit is not None, self.msg("Function/Subroutine found without a preceding ModuleStmt or ProgramStmt")

        if is_function:
            routine = self.nr.Function(name, self.curr.program_unit, self.curr.parent_routine)
            self.curr.routine = routine
            if self.curr.parent_routine is None:
                self.curr.program_unit.functions.add(routine)
        else:
            routine = self.nr.Subroutine(name, self.curr.program_unit, self.curr.parent_routine)
            self.curr.routine = routine
            if self.curr.parent_routine is None:
                self.curr.program_unit.subroutines.add(routine)
        return True

    def parse_routine_end(self):
        if "| EndFunctionStmt" in self.line:
            assert self.curr.in_function, self.msg("EndFunctionStmt found without a preceding FunctionStmt")
            m = re.search(r"EndFunctionStmt -> Name = '(\w+)'", self.line)
            if m:
                end_name = m.group(1)
                assert end_name == self.curr.routine.name, self.msg(f"EndFunctionStmt name {end_name} does not match FunctionStmt name {self.curr.routine.name}")
            self.curr.routine = self.curr.parent_routine
            self.curr.parent_routine = None
            return True

        if "| EndSubroutineStmt" in self.line:
            assert self.curr.in_subroutine, self.msg("EndSubroutineStmt found without a preceding SubroutineStmt")
            m = re.search(r"EndSubroutineStmt -> Name = '(\w+)'", self.line)
            if m:
                end_name = m.group(1)
                assert end_name == self.curr.routine.name, self.msg(f"EndSubroutineStmt name {end_name} does not match SubroutineStmt name {self.curr.routine.name}")
            self.curr.routine = self.curr.parent_routine
            self.curr.parent_routine = None
            return True
        return False

    def parse_only_clause(self):
        if "| Only" not in self.line:
            return False

        only_name = None
        if (m := re.search(r"Only -> GenericSpec -> Name = '(\w+)'", self.line)):
            only_name = m.group(1)
        elif (m := re.search(r"Only -> GenericSpec -> DefinedOperator -> IntrinsicOperator = (\w+)", self.line)):
            only_name = m.group(1)
        elif re.search(r"Only -> GenericSpec -> Assignment", self.line):
            only_name = "assignment(=)"
        elif re.search(r"Only -> Rename -> Names", self.line):
            self.line = self.read_next_line()
            m = re.search(r"Name = '(\w+)'", self.line)
            assert m, self.msg("Only Rename syntax not recognized")
            self.line = self.read_next_line()
            m = re.search(r"Name = '(\w+)'", self.line)
            assert m, self.msg("Only Rename syntax not recognized")
            only_name = m.group(1)
        else:
            raise ValueError(self.msg("Only syntax not recognized"))

        assert self.curr.used_module, self.msg("Only clause found without a preceding UseStmt")
        used_module_only_list = self.curr.scope.used_modules[self.curr.used_module]
        if used_module_only_list and used_module_only_list[0] == '*':
            pass
        else:
            used_module_only_list.append(only_name)
        return True

    def parse_use_stmt(self):
        if "| UseStmt" not in self.line:
            return False
        m = re.search(r"UseStmt *$", self.line)
        assert m, self.msg("UseStmt syntax not recognized")
        self.line = self.read_next_line()
        if re.search(r"\bModuleNature", self.line):
            self.line = self.read_next_line()
        m = re.search(r"Name = '(\w+)'", self.line)
        assert m, self.msg("UseStmt Name syntax not recognized")
        used_module_name = m.group(1)
        self.curr.used_module = self.nr.Module(used_module_name)
        next_line = self.peek_next_line()
        if next_line and "| Only" in next_line:
            if self.curr.used_module not in self.curr.scope.used_modules:
                self.curr.scope.used_modules[self.curr.used_module] = []
        else:
            self.curr.scope.used_modules[self.curr.used_module] = ['*']
            self.curr.used_module = None

        return True

    def parse_module_stmt(self):
        if "| ModuleStmt" not in self.line:
            return False
        m = re.search(r"ModuleStmt -> Name = '(\w+)'", self.line)
        assert m, self.msg("ModuleStmt syntax not recognized")
        assert self.curr.module is None, self.msg("ModuleStmt found without a preceding EndModuleStmt")
        module_name = m.group(1)
        self.curr.module = self.nr.Module(module_name)
        self.curr.module.parse_tree_path = self.parse_tree_path
        return True

    def parse_end_module_stmt(self):
        if "| EndModuleStmt" not in self.line:
            return False
        assert self.curr.module, self.msg("EndModuleStmt found without a preceding ModuleStmt")
        m = re.search(r"EndModuleStmt -> Name = '(\w+)'", self.line)
        if m:
            end_module_name = m.group(1)
            assert end_module_name == self.curr.module.name, self.msg(f"EndModuleStmt name {end_module_name} does not match ModuleStmt name {self.curr.module.name}")
        self.curr.module = None
        return True

    def parse_program_unit(self):
        if not self.line.startswith("Program -> ProgramUnit"):
            return False

        if self.line.startswith("Program -> ProgramUnit -> FunctionSubprogram") or \
           self.line.startswith("Program -> ProgramUnit -> SubroutineSubprogram"):
            self.curr.subprogram = self.nr.Subprogram(self.parse_tree_path.stem)
            return True

        if self.line.startswith("Program -> ProgramUnit -> Module"):
            return True  # handled by ModuleStmt/EndModuleStmt

        if self.line.startswith("Program -> ProgramUnit -> MainProgram"):
            self.line = self.read_next_line()
            m = re.search(r"ProgramStmt -> Name = '(\w+)'", self.line)
            if not m:
                raise ValueError(self.msg("ProgramStmt syntax not recognized"))
            program_name = m.group(1)
            self.curr.program = self.nr.Program(program_name)
            self.curr.program.parse_tree_path = self.parse_tree_path
            return True

        raise ValueError(self.msg("ProgramUnit syntax not recognized"))

    def parse_interface_stmt(self):

        if "| InterfaceStmt" not in self.line:
            return False
        
        if self.line.endswith("InterfaceStmt ->"):
            return False # todo: handle this case
        if "InterfaceStmt -> Abstract" in self.line:
            return False # todo: abstract interface
        if "DefinedOperator" in self.line:
            return False # todo: operator interface
        if "Assignment" in self.line:
            return False # todo: assignment interface        

        m = re.search(r"InterfaceStmt -> GenericSpec -> Name = '(\w+)'", self.line)
        assert m, self.msg("InterfaceStmt syntax not recognized")
        assert self.curr.program_unit is not None, self.msg("InterfaceStmt found outside of a program unit")
        assert self.curr.routine is None, self.msg("InterfaceStmt found within a routine, nested interfaces are not supported")

        interface_name = m.group(1)
        interface = self.nr.Interface(interface_name, self.curr.program_unit)

        def find_module_procedure(procedure_name):

            for subr in self.curr.program_unit.subroutines:
                if subr.name == procedure_name:
                    return subr
            for function in self.curr.program_unit.functions:
                if function.name == procedure_name:
                    return function
            for used_mod, used_names in self.curr.program_unit.used_modules.items():
                if used_names and '*' in used_names:
                    for subr in used_mod.subroutines:
                        if subr.name == procedure_name:
                            return subr
                    for function in used_mod.functions:
                        if function.name == procedure_name:
                            return function
                else:
                    if procedure_name in used_names:
                        for subr in used_mod.subroutines:
                            if subr.name == procedure_name:
                                return subr
                        for function in used_mod.functions:
                            if function.name == procedure_name:
                                return function
            return None

        # Read until EndInterfaceStmt
        while self.line:
            self.read_next_line()
            if "EndInterfaceStmt ->" in self.line:
                break
            if self.line.endswith("InterfaceSpecification -> ProcedureStmt"):
                continue
            if m := re.search(r"Kind = (\w+)", self.line):
                kind = m.group(1)
                if kind == "Procedure":
                    return False # todo: handle these cases
                assert kind == "ModuleProcedure", self.msg("Only ModuleProcedure kinds are supported in interface blocks")
                continue
            if m := re.search(r"Name = '(\w+)'", self.line):
                procedure_name = m.group(1)
                procedure = find_module_procedure(procedure_name)
                assert procedure is not None, self.msg(f"Could not find module procedure '{procedure_name}' for interface '{interface_name}'")
                continue
            assert False, self.msg("InterfaceSpecification syntax not recognized")
        
        return True


    def find_subroutine_callee(self, caller_program_unit, callee_name):
        """Finds the callee subroutine by name for the given caller subroutine.

        Parameters
        ----------
        caller_program_unit : Module, Program, or Subprogram
            The caller program unit.
        callee_name : str
            The name of the callee subroutine.

        Returns
        -------
        Subroutine or None
            The callee subroutine if found, otherwise None.
        """

        # todo: if a certain module is used by a subroutine in the same program unit,
        # but not used by the subroutine making the call, we should not find the callee in that module.

        # Check subroutines in the same program unit
        for subr in caller_program_unit.subroutines:
            if subr.name == callee_name:
                return subr

        # Check interfaces in the same program unit
        for intf in caller_program_unit.interfaces:
            if intf.name == callee_name:
                return intf
        
        # todo: check that callee is public if found in a used module

        # Check subroutines and interfaces from used modules
        def check_used_module(used_mod, used_names):
            if used_names and '*' in used_names:
                for subr in used_mod.subroutines:
                    if subr.name == callee_name:
                        return subr
                for intf in used_mod.interfaces:
                    if intf.name == callee_name:
                        return intf
            else: # only specific names used
                if callee_name in used_names:
                    for subr in used_mod.subroutines:
                        if subr.name == callee_name:
                            return subr
                    for intf in used_mod.interfaces:
                        if intf.name == callee_name:
                            return intf
            return None

        for used_mod, used_names in caller_program_unit.used_modules.items():
            callee = check_used_module(used_mod, used_names)
            if callee is not None:
                return callee
        
        # Look at used modules of used modules:
        for used_mod, used_names in caller_program_unit.used_modules.items():
            for sub_used_mod, sub_used_names in used_mod.used_modules.items():
                callee = check_used_module(sub_used_mod, sub_used_names)
                if callee is not None:
                    return callee
        
        return None

    def parse_call_stmt(self):

        if not "CallStmt" in self.line:
            return False

        assert self.line.endswith("ActionStmt -> CallStmt"), self.msg("CallStmt syntax not recognized")
        assert self.curr.program_unit is not None, self.msg("CallStmt found outside of a program unit")

        self.line = self.read_next_line()
        assert self.line.endswith("| Call"), self.msg("CallStmt syntax not recognized.")

        self.line = self.read_next_line()
        if self.line.endswith("ProcedureDesignator -> ProcComponentRef -> Scalar -> StructureComponent"):
            return  # todo: structure component call (obj%method), not handled
        m = re.search(r"ProcedureDesignator -> Name = '(\w+)'", self.line)
        if not m:
            raise ValueError(self.msg("ProcedureDesignator syntax not recognized"))
        callee_name = m.group(1)
        assert callee_name, self.msg("CallStmt found without a subroutine name")

        caller = self.curr.routine
        if caller: # call from within a subroutine/function
            callee = self.find_subroutine_callee(caller.program_unit, callee_name)
        else: # call from within a program
            caller = self.curr.program_unit
            assert caller == self.curr.program, self.msg("CallStmt found outside of a routine or program")
            callee = self.find_subroutine_callee(caller, callee_name)

        if callee is None:
            #print(self.msg(f"Could not find callee {callee_name} in any used module of {self.curr.program_unit.name} for call in {caller.name}"))
            if callee_name.lower().startswith("mpi_"):
                return  # skip MPI calls
            self.unfound_calls.append((caller.name, callee_name))
        else:
            caller.callees.add(callee)
            callee.callers.add(caller)


    def parse_structure(self):
        """Reads a flang parse tree file and extracts structural information."""

        try:
            self.parse_header()

            for self.line in self.lines():
                if self.parse_routine_begin():
                    continue
                if self.parse_routine_end():
                    continue
                if self.parse_only_clause():
                    continue
                if self.parse_use_stmt():
                    continue
                if self.parse_module_stmt():
                    continue
                if self.parse_end_module_stmt():
                    continue
                if self.parse_program_unit():
                    continue

        finally:
            self.reset()

    def parse_interfaces(self):
        """Reads a flang parse tree file and extracts interface blocks."""

        try:
            self.parse_header()

            for self.line in self.lines():
                if self.parse_routine_begin():
                    continue
                if self.parse_routine_end():
                    continue
                if self.parse_module_stmt():
                    continue
                if self.parse_end_module_stmt():
                    continue
                if self.parse_program_unit():
                    continue
                if self.parse_interface_stmt():
                    continue
        finally:
            self.reset()

    def parse_calls(self):
        """Reads a flang parse tree file and extracts subroutine/function call relationships."""

        try:
            self.parse_header()

            for self.line in self.lines():
                if self.parse_routine_begin():
                    continue
                if self.parse_routine_end():
                    continue
                if self.parse_module_stmt():
                    continue
                if self.parse_end_module_stmt():
                    continue
                if self.parse_program_unit():
                    continue
                if self.parse_call_stmt():
                    continue
            return self.unfound_calls
        finally:
            self.reset()


