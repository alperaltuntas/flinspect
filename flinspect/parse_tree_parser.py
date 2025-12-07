import re
from pathlib import Path
from flinspect.utils import level
from flinspect.parse_tree_node import Module, Program, Subprogram, Subroutine, Function

class ParseTreeParser:

    def __init__(self, file_path):

        assert isinstance(file_path, (str, Path)), f"Expected a string or Path object, got {type(file_path)}"
        file_path = Path(file_path)
        assert file_path.is_file(), f"Expected a file, got {file_path}"

        self.file_path = file_path
        self.module = None
        self.modules = []
        self.program = None
        self.used_module = None
        self.routine = None
        self.outer_routine = None
        self._lines = None # iterator over lines
        self.line = None

    def lines(self):
        """Iterator over lines in the parse tree file."""
        if self._lines is None:
            def _iter_lines():
                with self.file_path.open('r') as f:
                    for line in f:
                        yield line.strip()
            self._lines = _iter_lines()
        return self._lines

    def read_next_line(self):
        """Reads the next line from the parse tree file and updates self.line."""
        self.line = next(self.lines())
        return self.line

    @property
    def current_program_unit(self):
        return self.module or self.program

    @property
    def current_scope(self):
        return self.routine or self.current_program_unit

    def msg(self, prefix):
        """Helper method to format error/warning messages."""
        return f"{prefix} in {self.file_path}, line: {self.line}"

    def parse_header(self):
        assert self.line is None, self.msg("parse_header should be called at the beginning before reading any lines.")
        first = next(self.lines())
        if not first.startswith("======"):
            print(f"Warning: Skipping {self.file_path.name} as it does not start with proper header.")
            return False
        return True

    def parse_routine_begin(self):
        is_function = self.line.endswith("| FunctionStmt") or False
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

        if self.routine is not None:
            assert self.outer_routine is None, self.msg("More than one level of routine nesting found")
        self.outer_routine = self.routine

        assert self.current_program_unit is not None, self.msg("Function/Subroutine found without a preceding ModuleStmt or ProgramStmt")

        if is_function:
            routine = Function(name, self.current_program_unit, self.outer_routine)
            self.routine = routine
            if self.outer_routine is None:
                self.current_program_unit.functions.add(routine)
        else:
            routine = Subroutine(name, self.current_program_unit, self.outer_routine)
            self.routine = routine
            if self.outer_routine is None:
                self.current_program_unit.subroutines.add(routine)
        return True

    def parse_routine_end(self):
        if "| EndFunctionStmt" in self.line:
            assert type(self.routine) is Function, self.msg("EndFunctionStmt found without a preceding FunctionStmt")
            m = re.search(r"EndFunctionStmt -> Name = '(\w+)'", self.line)
            if m:
                end_name = m.group(1)
                assert end_name == self.routine.name, self.msg(f"EndFunctionStmt name {end_name} does not match FunctionStmt name {self.routine.name}")
            self.routine = self.outer_routine
            self.outer_routine = None
            return True

        if "| EndSubroutineStmt" in self.line:
            assert type(self.routine) is Subroutine, self.msg("EndSubroutineStmt found without a preceding SubroutineStmt")
            m = re.search(r"EndSubroutineStmt -> Name = '(\w+)'", self.line)
            if m:
                end_name = m.group(1)
                assert end_name == self.routine.name, self.msg(f"EndSubroutineStmt name {end_name} does not match SubroutineStmt name {self.routine.name}")
            self.routine = self.outer_routine
            self.outer_routine = None
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

        assert self.used_module, self.msg("Only clause found without a preceding UseStmt")
        used_module_only_list = self.current_scope.used_modules[self.used_module]
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
        self.used_module = Module(used_module_name)
        self.current_scope.used_modules[self.used_module] = []
        return True

    def parse_module_stmt(self):
        if "| ModuleStmt" not in self.line:
            return False
        m = re.search(r"ModuleStmt -> Name = '(\w+)'", self.line)
        assert m, self.msg("ModuleStmt syntax not recognized")
        assert self.module is None, self.msg("ModuleStmt found without a preceding EndModuleStmt")
        module_name = m.group(1)
        self.module = Module(module_name)
        self.module.ptree_path = self.file_path
        self.modules.append(self.module)
        return True

    def parse_end_module_stmt(self):
        if "| EndModuleStmt" not in self.line:
            return False
        assert self.module, self.msg("EndModuleStmt found without a preceding ModuleStmt")
        m = re.search(r"EndModuleStmt -> Name = '(\w+)'", self.line)
        if m:
            end_module_name = m.group(1)
            assert end_module_name == self.module.name, self.msg(f"EndModuleStmt name {end_module_name} does not match ModuleStmt name {self.module.name}")
        self.module = None
        return True

    def parse_program_unit(self):
        if not self.line.startswith("Program -> ProgramUnit"):
            return False

        if self.line.startswith("Program -> ProgramUnit -> FunctionSubprogram") or \
           self.line.startswith("Program -> ProgramUnit -> SubroutineSubprogram"):
            self.module = Subprogram(self.file_path.stem)
            return True

        if self.line.startswith("Program -> ProgramUnit -> Module"):
            return True  # handled by ModuleStmt/EndModuleStmt

        if self.line.startswith("Program -> ProgramUnit -> MainProgram"):
            self.line = self.read_next_line()
            m = re.search(r"ProgramStmt -> Name = '(\w+)'", self.line)
            if not m:
                raise ValueError(self.msg("ProgramStmt syntax not recognized"))
            program_name = m.group(1)
            self.program = Program(program_name)
            self.program.ptree_path = self.file_path
            return True

        raise ValueError(self.msg("ProgramUnit syntax not recognized"))

    def finalize_used_module_on_other_lines(self):
        # If we previously saw a UseStmt and didn't see an Only clause yet, and the current line isn't
        # one of the known handlers, assume whole-module use.
        if self.used_module:
            self.current_scope.used_modules[self.used_module] = ['*']
            self.used_module = None


    def parse_call_stmt(self):

        if not "CallStmt" in self.line:
            return False

        # sweep 1 only
        assert self.line.endswith("ActionStmt -> CallStmt"), self.msg("CallStmt syntax not recognized")
        assert self.current_program_unit is not None, self.msg("CallStmt found outside of a program unit")

        self.line = self.read_next_line()
        assert self.line.endswith("| Call"), self.msg("CallStmt syntax not recognized.")

        self.line = self.read_next_line()
        if self.line.endswith("ProcedureDesignator -> ProcComponentRef -> Scalar -> StructureComponent"):
            return  # structure component call (obj%method), not handled
        m = re.search(r"ProcedureDesignator -> Name = '(\w+)'", self.line)
        if not m:
            raise ValueError(self.msg("ProcedureDesignator syntax not recognized"))
        callee = m.group(1)

        caller = self.routine
        assert caller, self.msg("CallStmt found without a preceding SubroutineStmt")
        assert callee, self.msg("CallStmt found without a subroutine name")

        # resolve callee
        found_callee = False

        # in same program unit
        for subr in self.current_program_unit.subroutines:
            if callee == subr.name:
                caller.callees.add(subr)
                subr.callers.add(caller)
                found_callee = True
                break

        # in used modules
        if not found_callee:
            for used_mod, used_names in self.current_program_unit.used_modules.items():
                if used_names and '*' in used_names:
                    for subr in used_mod.subroutines:
                        if callee == subr.name:
                            caller.callees.add(subr)
                            subr.callers.add(caller)
                            found_callee = True
                            break
                else:
                    if callee in used_names:
                        for subr in used_mod.subroutines:
                            if callee == subr.name:
                                caller.callees.add(subr)
                                subr.callers.add(caller)
                                found_callee = True
                                break
                if found_callee:
                    break

        if not found_callee:
            print(self.msg(f"Could not find callee {callee} in any used module of {self.current_program_unit.name} for call in {caller.name}"))

    def parse(self, sweep=0):
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

        if not self.parse_header():
            return []

        for self.line in self.lines():

            # Sweep 0 - Structure parsing
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

            # Sweep 1 - Call relationship parsing
            if sweep == 1:
                if self.parse_call_stmt():
                    continue

            # Fallback: if a UseStmt was seen and no Only followed, mark entire module used.
            self.finalize_used_module_on_other_lines()

        return self.modules

