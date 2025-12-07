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
        self.f = None # file handle
        self.module = None
        self.modules = []
        self.program = None
        self.used_module = None
        self.routine = None
        self.outer_routine = None

    def __enter__(self):
        self.f = open(self.file_path, 'r')
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        if self.f:
            self.f.close()
        return False  # Do not suppress exceptions

    @property
    def current_program_unit(self):
        return self.module or self.program
    
    @property
    def current_scope(self):
        return self.routine or self.current_program_unit

    def parse_header(self):
        first = self.f.readline().strip()
        if not first.startswith("======"):
            print(f"Warning: Skipping {self.file_path.name} as it does not start with proper header.")
            return False
        return True

    def parse_call_stmt(self, line):

        file_path = self.file_path

        # sweep 1 only
        assert line.endswith("ActionStmt -> CallStmt"), f"CallStmt syntax not recognized in {file_path}, line: {line}"
        assert self.current_program_unit is not None, f"CallStmt found outside of a program unit in {file_path}, line: {line}"

        line = self.f.readline().strip()
        assert line.endswith("| Call"), f"CallStmt syntax not recognized in {file_path}, line: {line}"

        line = self.f.readline().strip()
        if line.endswith("ProcedureDesignator -> ProcComponentRef -> Scalar -> StructureComponent"):
            return  # structure component call (obj%method), not handled
        m = re.search(r"ProcedureDesignator -> Name = '(\w+)'", line)
        if not m:
            raise ValueError(f"ProcedureDesignator syntax not recognized in {file_path}, line: {line}")
        callee = m.group(1)

        caller = self.routine
        assert caller, f"CallStmt found without a preceding SubroutineStmt in {file_path} at line: {line}"
        assert callee, f"CallStmt found without a subroutine name in {file_path} at line: {line}"

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
            print(f"Warning: Could not find callee {callee} in any used module of {self.current_program_unit.name} for call in {caller.name} at line: {line}")

    def parse_routine_begin(self, line):
        file_path = self.file_path
        is_function = line.endswith("| FunctionStmt") or False
        is_subroutine = line.endswith("| SubroutineStmt")
        if not (is_function or is_subroutine):
            return False

        # advance to Name line, skipping Prefix blocks
        line = self.f.readline().strip()
        l = level(line)
        while re.search(r"\bPrefix", line) or level(line) > l:
            line = self.f.readline().strip()
        res = re.search(r"Name = '(\w+)'", line)
        if not res:
            raise ValueError(f"FunctionStmt syntax not recognized in {file_path}, line: {line}")
        name = res.group(1)

        if self.routine is not None:
            assert self.outer_routine is None, f"More than one level of routine nesting found in {file_path}"
        self.outer_routine = self.routine

        assert self.current_program_unit is not None, f"Function/Subroutine found without a preceding ModuleStmt or ProgramStmt in {file_path}"

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

    def parse_routine_end(self, line):
        if "| EndFunctionStmt" in line:
            assert type(self.routine) is Function, f"EndFunctionStmt found without a preceding FunctionStmt in {self.file_path}"
            m = re.search(r"EndFunctionStmt -> Name = '(\w+)'", line)
            if m:
                end_name = m.group(1)
                assert end_name == self.routine.name, f"EndFunctionStmt name {end_name} does not match FunctionStmt name {self.routine.name} in {self.file_path}"
            self.routine = self.outer_routine
            self.outer_routine = None
            return True

        if "| EndSubroutineStmt" in line:
            assert type(self.routine) is Subroutine, f"EndSubroutineStmt found without a preceding SubroutineStmt in {self.file_path}"
            m = re.search(r"EndSubroutineStmt -> Name = '(\w+)'", line)
            if m:
                end_name = m.group(1)
                assert end_name == self.routine.name, f"EndSubroutineStmt name {end_name} does not match SubroutineStmt name {self.routine.name} in {self.file_path}"
            self.routine = self.outer_routine
            self.outer_routine = None
            return True
        return False

    def parse_only_clause(self, line):
        if "| Only" not in line:
            return False

        only_name = None
        if (m := re.search(r"Only -> GenericSpec -> Name = '(\w+)'", line)):
            only_name = m.group(1)
        elif (m := re.search(r"Only -> GenericSpec -> DefinedOperator -> IntrinsicOperator = (\w+)", line)):
            only_name = m.group(1)
        elif re.search(r"Only -> GenericSpec -> Assignment", line):
            only_name = "assignment(=)"
        elif re.search(r"Only -> Rename -> Names", line):
            line = self.f.readline().strip()
            m = re.search(r"Name = '(\w+)'", line)
            assert m, f"Only Rename syntax not recognized in {self.file_path}, line: {line}"
            line = self.f.readline().strip()
            m = re.search(r"Name = '(\w+)'", line)
            assert m, f"Only Rename syntax not recognized in {self.file_path}, line: {line}"
            only_name = m.group(1)
        else:
            raise ValueError(f"Only syntax not recognized in {self.file_path}, line: {line}")

        assert self.used_module, f"Only clause found without a preceding UseStmt in {self.file_path} at line: {line}"
        used_module_only_list = self.current_scope.used_modules[self.used_module]
        if used_module_only_list and used_module_only_list[0] == '*':
            pass
        else:
            used_module_only_list.append(only_name)
        return True

    def parse_use_stmt(self, line):
        if "| UseStmt" not in line:
            return False
        m = re.search(r"UseStmt *$", line)
        assert m, f"UseStmt syntax not recognized in {self.file_path}"
        line = self.f.readline().strip()
        if re.search(r"\bModuleNature", line):
            line = self.f.readline().strip()
        m = re.search(r"Name = '(\w+)'", line)
        assert m, f"UseStmt Name syntax not recognized in {self.file_path}, line: {line}"
        used_module_name = m.group(1)
        self.used_module = Module(used_module_name)
        self.current_scope.used_modules[self.used_module] = []
        return True

    def parse_module_stmt(self, line):
        if "| ModuleStmt" not in line:
            return False
        m = re.search(r"ModuleStmt -> Name = '(\w+)'", line)
        assert m, f"ModuleStmt syntax not recognized in {self.file_path}"
        assert self.module is None, f"ModuleStmt found without a preceding EndModuleStmt in {self.file_path}"
        module_name = m.group(1)
        self.module = Module(module_name)
        self.module.ptree_path = self.file_path
        self.modules.append(self.module)
        return True

    def parse_end_module_stmt(self, line):
        if "| EndModuleStmt" not in line:
            return False
        assert self.module, f"EndModuleStmt found without a preceding ModuleStmt in {self.file_path}"
        m = re.search(r"EndModuleStmt -> Name = '(\w+)'", line)
        if m:
            end_module_name = m.group(1)
            assert end_module_name == self.module.name, f"EndModuleStmt name {end_module_name} does not match ModuleStmt name {self.module.name} in {self.file_path}"
        self.module = None
        return True

    def parse_program_unit(self, line):
        if not line.startswith("Program -> ProgramUnit"):
            return False

        if line.startswith("Program -> ProgramUnit -> FunctionSubprogram") or \
           line.startswith("Program -> ProgramUnit -> SubroutineSubprogram"):
            self.module = Subprogram(self.file_path.stem)
            return True

        if line.startswith("Program -> ProgramUnit -> Module"):
            return True  # handled by ModuleStmt/EndModuleStmt

        if line.startswith("Program -> ProgramUnit -> MainProgram"):
            line = self.f.readline().strip()
            m = re.search(r"ProgramStmt -> Name = '(\w+)'", line)
            if not m:
                raise ValueError(f"ProgramStmt syntax not recognized in {self.file_path}, line: {line}")
            program_name = m.group(1)
            self.program = Program(program_name)
            self.program.ptree_path = self.file_path
            return True

        raise ValueError(f"ProgramUnit syntax not recognized in {self.file_path}, line: {line}")

    def finalize_used_module_on_other_lines(self):
        # If we previously saw a UseStmt and didn't see an Only clause yet, and the current line isn't
        # one of the known handlers, assume whole-module use.
        if self.used_module:
            self.current_scope.used_modules[self.used_module] = ['*']
            self.used_module = None

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

        for raw in self.f:
            line = raw.strip()

            if sweep == 1 and "CallStmt" in line:
                self.parse_call_stmt(line)
                continue

            if self.parse_routine_begin(line):
                continue
            if self.parse_routine_end(line):
                continue
            if self.parse_only_clause(line):
                continue
            if self.parse_use_stmt(line):
                continue
            if self.parse_module_stmt(line):
                continue
            if self.parse_end_module_stmt(line):
                continue
            if self.parse_program_unit(line):
                continue

            # Fallback: if a UseStmt was seen and no Only followed, mark entire module used.
            self.finalize_used_module_on_other_lines()
        
        return self.modules

