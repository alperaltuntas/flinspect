import re
from pathlib import Path
from flinspect.utils import level, is_fortran_intrinsic
from flinspect.parse_state import ParseState
from flinspect.variable_info import VariableInfo
from flinspect.parse_node import Interface
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
        self.unfound_subroutine_calls = []
        self.unfound_function_calls = []

        # Variable type tracking: maps (scope_key, var_name) -> VariableInfo
        # Persists across parsing passes (structure, interfaces, calls)
        self.variables = {}

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
        """Resets the internal state for re-parsing the file."""
        self._lines_generator = None
        self.line = None
        self.next_line = None
        self.line_number = 0
        self.curr = ParseState()
        self.unfound_subroutine_calls = []
        self.unfound_function_calls = []

    # -------------------------------------------------------------------------
    # Variable tracking methods
    # -------------------------------------------------------------------------

    def add_variable(self, name: str, var_info):
        """Register a variable in the current scope."""
        scope_key = self.curr.get_scope_key()
        if scope_key not in self.variables:
            self.variables[scope_key] = {}
        self.variables[scope_key][name.lower()] = var_info

    def get_variable(self, name: str):
        """Look up a variable, checking current scope then enclosing scopes."""
        name_lower = name.lower()
        
        # Check current routine scope
        if self.curr.routine:
            scope_key = self.curr.get_scope_key()
            if scope_key in self.variables and name_lower in self.variables[scope_key]:
                return self.variables[scope_key][name_lower]
            
            # Check parent routine scope (for nested routines)
            if self.curr.parent_routine:
                parent_scope = f"{self.curr.program_unit.name}::{self.curr.parent_routine.name}"
                if parent_scope in self.variables and name_lower in self.variables[parent_scope]:
                    return self.variables[parent_scope][name_lower]
        
        # Check module/program scope
        if self.curr.program_unit:
            module_scope = self.curr.program_unit.name
            if module_scope in self.variables and name_lower in self.variables[module_scope]:
                return self.variables[module_scope][name_lower]
        
        return None

    # -------------------------------------------------------------------------
    # Helper methods for parsing array specs, kinds, and type compatibility
    # -------------------------------------------------------------------------

    def _parse_array_spec(self, line):
        """Parse array specification from a line and return rank (int or None)."""

        if "DeferredShapeSpecList -> int = " in line:
            m = re.search(r"DeferredShapeSpecList -> int = '(\d+)'", line)
            return int(m.group(1)) if m else 1
        if "AssumedShapeSpec -> int = " in line:
            m = re.search(r"AssumedShapeSpec -> int = '(\d+)'", line)
            return int(m.group(1)) if m else 1
        if "AssumedShapeSpec" in line:
            return 1  # At least 1 assumed-shape dimension (e.g., array(lo:))
        if "AssumedRankSpec" in line:
            return -1  # Assumed rank (..) - could be any rank
        if "ImpliedShapeSpec" in line:
            return 1  # Implied shape (*) means assumed-size array
        if "ExplicitShapeSpec" in line:
            return 1  # At least 1 dimension, caller may need to count more
        return None

    def _extract_kind_from_line(self, line):
        """Extract kind specifier from a line containing KindSelector.
        Returns the kind specifier (e.g., 'r8_kind', 'i4_kind') or None if not found."""

        if "KindSelector" in line:
            m = re.search(r"Name = '(\w+)'", line)
            return m.group(1) if m else None
        return None

    def _extract_structure_component_name(self, designator_level):
        """Extract the method name and object name from a ProcComponentRef -> StructureComponent.

        After encountering a line ending with:
            ProcedureDesignator -> ProcComponentRef -> Scalar -> StructureComponent
        this method reads the nested lines to find the component (method) name
        and the object name.

        The parse tree structure is:
            ProcedureDesignator -> ProcComponentRef -> Scalar -> StructureComponent
              DataRef -> ...          (the object, possibly nested like obj%field%...)
                Name = 'obj_name'   (or more DataRef nesting)
              Name = 'method_name'  (the last Name at StructureComponent level)

        Returns
        -------
        tuple of (str or None, str or None)
            (method_name, object_name) where method_name is the component being
            called and object_name is the first Name found inside the DataRef
            (the root object). Either may be None if not found.
        """
        callee_name = None
        object_name = None
        found_dataref = False

        while self.peek_next_line():
            next_line = self.peek_next_line()
            next_lvl = level(next_line)

            if next_lvl <= designator_level:
                break

            if next_lvl == designator_level + 1:
                m = re.search(r"Name = '(\w+)'", next_line)
                if m:
                    if 'DataRef' in next_line and object_name is None:
                        # DataRef -> Name = 'obj_name' (simple case)
                        object_name = m.group(1)
                    callee_name = m.group(1)
                elif 'DataRef' in next_line:
                    found_dataref = True
            elif next_lvl == designator_level + 2 and found_dataref and object_name is None:
                # Nested DataRef: the first Name child is the root object
                m = re.search(r"Name = '(\w+)'", next_line)
                if m:
                    object_name = m.group(1)

            self.read_next_line()

        return callee_name, object_name

    def _resolve_binding_name(self, binding_name, type_name):
        """Resolve a type-bound procedure binding name to its implementation name.

        When a derived type has:
            procedure :: reset => reset_bounds
        a call like 'obj%reset()' should resolve to 'reset_bounds'.

        Only the bindings of the derived type identified by *type_name* are
        searched, so there is no ambiguity when multiple types share the same
        binding name.

        Parameters
        ----------
        binding_name : str
            The binding name used in the call (e.g., 'reset').
        type_name : str
            The declared derived-type name of the calling object (e.g.,
            'fmsdiagibounds_type').

        Returns
        -------
        tuple of (str, Scope or None)
            A tuple (impl_name, defining_scope) where impl_name is the
            implementation name (e.g., 'reset_bounds') and defining_scope is
            the scope that defines the derived type. If no matching binding
            is found, returns (binding_name, None).
        """
        binding_lower = binding_name.lower()
        type_name_lower = type_name.lower()

        for dt in self.nr.derived_types:
            if dt.name.lower() == type_name_lower:
                for bname, iname in dt.bindings.items():
                    if bname.lower() == binding_lower:
                        return iname, dt.scope

        return binding_name, None

    def _record_call_dependencies(self, callee_name, call_arg_types, call_arg_ranks, call_arg_kinds, call_arg_names=None, is_function=False, defining_scope=None):
        """Record a call relationship between the current scope and the callee."""
        caller = self.curr.scope
        callee = self.find_named_entity(caller, callee_name)

        # If not found through normal USE chains, try the defining scope directly
        # (for type-bound procedure calls where the routine is not explicitly USE'd)
        if callee is None and defining_scope is not None:
            callee = self.find_named_entity(defining_scope, callee_name)

        if callee is None:
            if is_function:
                self.unfound_function_calls.append((caller.name, callee_name))
            elif not callee_name.lower().startswith("mpi_"):
                self.unfound_subroutine_calls.append((caller.name, callee_name))
        elif isinstance(callee, Interface):
            matching_procs = self.resolve_interface_procedures(callee, call_arg_types, call_arg_ranks, call_arg_kinds, call_arg_names)
            for proc in matching_procs:
                caller.callees.add(proc)
                proc.callers.add(caller)
            caller.callees.add(callee)
            callee.callers.add(caller)
        else:
            caller.callees.add(callee)
            callee.callers.add(caller)

    def _types_compatible(self, call_type, proc_type):
        """Check if a call argument type (str) is compatible with a procedure parameter type (str)."""

        # Unknown types are always considered compatible (conservative)
        if call_type == "unknown" or proc_type == "unknown":
            return True
        
        # Exact match
        if call_type == proc_type:
            return True
        
        # Numeric is compatible with integer or real
        if call_type == "numeric" and proc_type in ("integer", "real"):
            return True
        if proc_type == "numeric" and call_type in ("integer", "real"):
            return True
        
        # Incompatible type pairs
        incompatible_pairs = [
            (("integer", "real", "numeric"), ("character", "logical")),
            (("character",), ("integer", "real", "logical", "numeric")),
            (("logical",), ("integer", "real", "character", "numeric")),
        ]
        for group1, group2 in incompatible_pairs:
            if call_type in group1 and proc_type in group2:
                return False
            if proc_type in group1 and call_type in group2:
                return False
        
        # For derived types, they must match exactly (if both are known)
        if call_type.startswith("derived:") and proc_type.startswith("derived:"):
            return call_type == proc_type
        
        # Default: assume compatible (conservative)
        return True

    def _ranks_compatible(self, call_rank, proc_rank):
        """Check if call argument rank (int) is compatible with procedure parameter rank."""
        # -1 means unknown, treat as compatible
        if call_rank == -1 or proc_rank == -1:
            return True
        return call_rank == proc_rank

    def _kinds_compatible(self, call_kind, proc_kind):
        """Check if call argument kind (str) is compatible with procedure parameter kind (str)."""

        # None means unknown, treat as compatible
        if call_kind is None or proc_kind is None:
            return True
        return call_kind == proc_kind

    def _procedure_matches(self, proc, call_arg_types, call_arg_ranks=None, call_arg_kinds=None, call_arg_names=None):
        """Check if a procedure matches the call signature.
        
        Parameters
        ----------
        proc : Callable
            The procedure to check.
        call_arg_types : list
            Inferred types of actual arguments.
        call_arg_ranks : list, optional
            Inferred ranks of actual arguments.
        call_arg_kinds : list, optional
            Inferred kinds of actual arguments.
        call_arg_names : list, optional
            Keyword names used in the call (None for positional args).
            
        Returns
        -------
        bool
            True if the procedure could match the call, False otherwise.
        """
        if proc.num_args is None:
            return True  # No signature info, assume match
        
        # Check argument count
        num_call_args = len(call_arg_types)
        min_args = proc.num_required_args if proc.num_required_args is not None else proc.num_args
        max_args = proc.num_args
        if not (min_args <= num_call_args <= max_args):
            return False
        
        # Build a mapping from call argument index to the corresponding
        # procedure parameter index.  Positional arguments map 1-to-1;
        # keyword arguments must be resolved by name.
        proc_arg_names_lower = (
            [n.lower() for n in proc.arg_names] if proc.arg_names else None
        )

        call_to_proc_idx = []
        for i in range(len(call_arg_types)):
            kw_name = call_arg_names[i] if call_arg_names else None
            if kw_name is not None and proc_arg_names_lower is not None:
                kw_lower = kw_name.lower()
                if kw_lower in proc_arg_names_lower:
                    call_to_proc_idx.append(proc_arg_names_lower.index(kw_lower))
                else:
                    return False  # keyword not in procedure → no match
            else:
                call_to_proc_idx.append(i)  # positional

        # Check types
        if call_arg_types and proc.arg_types:
            for i, call_type in enumerate(call_arg_types):
                pi = call_to_proc_idx[i]
                if pi < len(proc.arg_types):
                    if not self._types_compatible(call_type, proc.arg_types[pi]):
                        return False
        
        # Check ranks
        if call_arg_ranks and proc.arg_ranks:
            for i, call_rank in enumerate(call_arg_ranks):
                pi = call_to_proc_idx[i]
                if pi < len(proc.arg_ranks):
                    if not self._ranks_compatible(call_rank, proc.arg_ranks[pi]):
                        return False
        
        # Check kinds
        if call_arg_kinds and proc.arg_kinds:
            for i, call_kind in enumerate(call_arg_kinds):
                pi = call_to_proc_idx[i]
                if pi < len(proc.arg_kinds):
                    if not self._kinds_compatible(call_kind, proc.arg_kinds[pi]):
                        return False
        
        return True

    # -------------------------------------------------------------------------
    # Expression and variable type inference
    # -------------------------------------------------------------------------

    # Lookup tables for expression type inference
    _LITERAL_TYPES = {
        "IntLiteralConstant": ("integer", 0, None),
        "RealLiteralConstant": ("real", 0, None),
        "CharLiteralConstant": ("character", 0, None),
        "LogicalLiteralConstant": ("logical", 0, None),
        "BOZLiteralConstant": ("logical", 0, None),
        "ComplexLiteralConstant": ("complex", 0, None),
    }
    _ARITHMETIC_OPS = {"-> Add", "-> Subtract", "-> Multiply", "-> Divide", "-> Negate"}
    _LOGICAL_OPS = {"-> NOT", "-> AND", "-> OR"}
    _COMPARISON_OPS = {"-> LT", "-> LE", "-> GT", "-> GE", "-> EQ", "-> NE"}

    def _infer_expr_type(self, expr_line):
        """Infer the type of an expression from its parse tree representation.
        
        Parameters
        ----------
        expr_line : str
            A line containing an expression (ActualArg -> Expr -> ...)
            
        Returns
        -------
        tuple (str, int, str or None)
            The inferred type ('integer', 'real', 'character', 'logical', 'unknown'),
            rank (0 for scalar, 1+ for arrays, -1 for unknown),
            and kind specifier (e.g., 'r8_kind', 'i4_kind') or None if unknown
        """
        # Check for literal constants (always scalars with default kind)
        for literal, type_info in self._LITERAL_TYPES.items():
            if literal in expr_line:
                return type_info
        
        # Arithmetic operations return numeric type with unknown rank
        if any(op in expr_line for op in self._ARITHMETIC_OPS):
            return "numeric", -1, None
        
        # Logical operations
        if any(op in expr_line for op in self._LOGICAL_OPS):
            return "logical", -1, None
        
        # Comparison operations return logical scalars
        if any(op in expr_line for op in self._COMPARISON_OPS):
            return "logical", 0, None
        
        # String concatenation
        if "-> Concat" in expr_line:
            return "character", -1, None
        
        # Array constructor returns array rank 1
        if "-> ArrayConstructor" in expr_line:
            return "unknown", 1, None
        
        # If it's a simple designator/variable, we can't easily determine type without context
        return "unknown", -1, None

    def _infer_variable_type(self, lines, start_level):
        """Infer type, rank, and kind from a variable reference in expression lines.
        
        Parameters
        ----------
        lines : list of str
            Lines to parse looking for variable name and array subscripts
        start_level : int
            The indentation level of the start of this expression
            
        Returns
        -------
        tuple (str, int, str or None)
            Type, rank, and kind inferred from variable lookup and subscript analysis
        """
        var_name = None
        has_subscripts = False
        subscript_count = 0
        has_triplet = False

        # Detect StructureComponent access (e.g., CS%data_field).  We can only
        # resolve the parent object's type, not the component's, so we must
        # return unknown to avoid false type/rank mismatches.
        has_structure_component = any("StructureComponent" in l for l in lines)

        func_ref_name = None  # Name from ProcedureDesignator (array-as-FunctionReference)
        func_ref_level = None  # Level of the FunctionReference -> Call line

        for line in lines:
            lvl = level(line)
            if lvl <= start_level:
                break

            # flang parses array element access (e.g., fields(i)) as
            # FunctionReference -> Call with ProcedureDesignator -> Name.
            # Capture this name so we can look it up as a variable.
            if "ProcedureDesignator -> Name = '" in line and func_ref_name is None:
                m = re.search(r"Name = '(\w+)'", line)
                if m:
                    func_ref_name = m.group(1)
                    func_ref_level = lvl
                continue

            # If we are inside a FunctionReference's ActualArgSpec (subscript),
            # skip DataRef -> Name lines – they are subscript indices, not the
            # variable being referenced.
            if func_ref_level is not None and lvl > func_ref_level:
                continue

            # Look for variable name in DataRef -> Name pattern
            if "DataRef -> Name = '" in line:
                m = re.search(r"Name = '(\w+)'", line)
                if m:
                    var_name = m.group(1)
            # Check for array element access (reduces rank)
            elif "ArrayElement" in line:
                has_subscripts = True
            elif "SectionSubscript" in line:
                subscript_count += 1
            elif "SubscriptTriplet" in line:
                has_triplet = True  # Triplet means dimension is preserved

        # If no DataRef name was found but we have a FunctionReference name,
        # it may be an array element access.  Try looking it up as a variable.
        if var_name is None and func_ref_name is not None:
            var_info = self.get_variable(func_ref_name)
            if var_info is not None:
                var_name = func_ref_name
                # Array element access: rank is reduced by 1 (scalar subscript)
                has_subscripts = True
                subscript_count = max(subscript_count, 1)

        if var_name:
            # Look up the variable type
            var_info = self.get_variable(var_name)
            if var_info:
                # For StructureComponent access (e.g., CS%data_field) we resolved
                # the parent object (CS) but not the component (data_field).
                # Return unknown so that the wildcard doesn't falsely reject
                # matching procedures.
                if has_structure_component:
                    return "unknown", -1, None

                var_type = var_info.type
                var_rank = var_info.rank
                var_kind = var_info.kind

                # Adjust rank based on subscripts
                if has_subscripts and subscript_count > 0:
                    # If using subscript triplets (:), dimensions are preserved
                    # If using scalar subscripts, rank is reduced
                    # This is a simplification - we'd need more analysis for full accuracy
                    if has_triplet:
                        # At least some dimensions preserved
                        new_rank = max(0, var_rank - (subscript_count - 1)) if subscript_count > 0 else var_rank
                        return var_type, new_rank, var_kind
                    else:
                        # All subscripts are scalar, reduces to scalar or lower rank
                        new_rank = max(0, var_rank - subscript_count)
                        return var_type, new_rank, var_kind
                return var_type, var_rank, var_kind

        return "unknown", -1, None

    def _collect_arg_lines(self, arg_level):
        """Collect all lines belonging to a single argument expression.
        
        Returns
        -------
        list of str
            Lines within this argument block.
        """
        arg_lines = []
        while self.peek_next_line() and level(self.peek_next_line()) > arg_level:
            arg_lines.append(self.peek_next_line())
            self.read_next_line()
        return arg_lines

    def _infer_arg_type(self, arg_lines, arg_level):
        """Infer type, rank, and kind for a single argument from its expression lines.
        
        Returns
        -------
        tuple (str, int, str or None)
            Inferred (type, rank, kind).
        """
        arg_type, arg_rank, arg_kind = "unknown", -1, None
        
        # First pass: check for expression-level type inference
        for line in arg_lines:
            if "ActualArg -> Expr" in line:
                arg_type, arg_rank, arg_kind = self._infer_expr_type(line)
                if arg_type != "unknown" and arg_rank != -1:
                    return arg_type, arg_rank, arg_kind
                break
        
        # Second pass: try variable lookup for rank/kind info
        var_type, var_rank, var_kind = self._infer_variable_type(arg_lines, arg_level)
        if var_type != "unknown":
            # Keep "numeric" from arithmetic, but use variable's rank/kind
            if arg_type == "numeric":
                return arg_type, var_rank, var_kind
            return var_type, var_rank, var_kind
        
        return arg_type, arg_rank, arg_kind

    def parse_call_arguments(self, call_level):
        """Parse actual arguments in a call statement, extracting types, ranks, kinds, and keyword names.
        
        Returns
        -------
        tuple (list, list, list, list)
            (arg_types, arg_ranks, arg_kinds, arg_names)
            arg_names contains the keyword name if used (e.g., 'data' in data=x), or None for positional args
        """
        arg_types, arg_ranks, arg_kinds, arg_names = [], [], [], []
        arg_level = call_level + 1
        
        while self.peek_next_line():
            next_line = self.peek_next_line()
            next_lvl = level(next_line)
            
            if next_lvl <= call_level:
                break
            
            if next_lvl == arg_level and "ActualArgSpec" in next_line:
                self.read_next_line()
                arg_lines = self._collect_arg_lines(arg_level)
                
                # Check for keyword argument (Keyword -> Name = 'xxx')
                keyword_name = None
                for line in arg_lines:
                    if "Keyword -> Name = " in line:
                        m = re.search(r"Keyword -> Name = '(\w+)'", line)
                        if m:
                            keyword_name = m.group(1)
                        break
                
                arg_type, arg_rank, arg_kind = self._infer_arg_type(arg_lines, arg_level)
                arg_types.append(arg_type)
                arg_ranks.append(arg_rank)
                arg_kinds.append(arg_kind)
                arg_names.append(keyword_name)
            else:
                self.read_next_line()
        
        return arg_types, arg_ranks, arg_kinds, arg_names

    def resolve_interface_procedures(self, interface, call_arg_types, call_arg_ranks=None, call_arg_kinds=None, call_arg_names=None):
        """Resolves which interface procedures match a call based on argument types, ranks, kinds, and names.
        
        When a call is made to an interface (generic name), this method determines
        which specific module procedures within the interface could match based on
        the types, array ranks, kind specifiers, and keyword argument names provided in the call.
        
        Parameters
        ----------
        interface : Interface
            The interface block containing module procedures.
        call_arg_types : list
            The inferred types of actual arguments in order.
        call_arg_ranks : list, optional
            The inferred ranks of actual arguments in order (-1 for unknown).
        call_arg_kinds : list, optional
            The inferred kind specifiers of actual arguments in order (None if unknown).
        call_arg_names : list, optional
            The keyword names used in the call (None for positional arguments).
            
        Returns
        -------
        list
            List of matching procedures. If signature info is not available,
            returns all procedures (fallback to old behavior).
        """
        # Check if any procedure has signature info
        has_any_signature_info = any(p.num_args is not None for p in interface.procedures)
        
        # If no signature info at all, fall back to returning all procedures
        if not has_any_signature_info:
            return list(interface.procedures)
        
        # Filter procedures that match the call signature
        matching = [
            proc for proc in interface.procedures
            if self._procedure_matches(proc, call_arg_types, call_arg_ranks, call_arg_kinds, call_arg_names)
        ]

        # If no procedures matched, fall back to returning all procedures.
        # In Fortran, a call to a generic interface must resolve to at least one
        # module procedure at runtime, so an empty result means our type inference
        # was too imprecise — not that no procedure matches.
        if not matching:
            return list(interface.procedures)

        return matching

    def msg(self, prefix):
        """Helper method to format error/warning messages."""
        return \
            f"{prefix}\n"\
            f"  file: {self.parse_tree_path}:{self.line_number}\n"\
            f"  line: {self.line}"

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
        stmt_level = level(self.line)
        while re.search(r"\bPrefix", self.line) or level(self.line) > stmt_level:
            self.read_next_line()
        res = re.search(r"Name = '(\w+)'", self.line)
        if not res:
            raise ValueError(self.msg("FunctionStmt syntax not recognized"))
        name = res.group(1)

        # Collect dummy argument names following the routine name
        # For subroutines: DummyArg -> Name = 'xxx'
        # For functions: Name = 'xxx' at the same level as function name
        arg_names = []
        while self.peek_next_line() and level(self.peek_next_line()) == stmt_level:
            next_line = self.peek_next_line()
            if is_subroutine and "DummyArg -> Name = " in next_line:
                m = re.search(r"Name = '(\w+)'", next_line)
                if m:
                    arg_names.append(m.group(1))
                self.read_next_line()
            elif is_function and re.search(r"\| Name = '\w+'", next_line):
                m = re.search(r"Name = '(\w+)'", next_line)
                if m:
                    arg_names.append(m.group(1))
                self.read_next_line()
            else:
                break

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
        
        # Parse SpecificationPart to get optional arguments and types
        self._parse_routine_signature(routine, arg_names)
        
        return True

    def _extract_type_from_decl(self, decl_line):
        """Extract the type from a DeclarationTypeSpec line.
        
        Parameters
        ----------
        decl_line : str
            A line containing DeclarationTypeSpec
            
        Returns
        -------
        str
            The type name (e.g., 'integer', 'real', 'character', 'logical', 'derived:typename')
        """
        if "IntrinsicTypeSpec -> IntegerTypeSpec" in decl_line:
            return "integer"
        if "IntrinsicTypeSpec -> RealTypeSpec" in decl_line or "IntrinsicTypeSpec -> Real" in decl_line:
            return "real"
        if "IntrinsicTypeSpec -> DoublePrecision" in decl_line:
            return "real"
        if "IntrinsicTypeSpec -> Character" in decl_line:
            return "character"
        if "IntrinsicTypeSpec -> Logical" in decl_line:
            return "logical"
        if "IntrinsicTypeSpec -> Complex" in decl_line:
            return "complex"
        if "DeclarationTypeSpec -> Type" in decl_line or "DerivedTypeSpec" in decl_line:
            # Derived type - extract name if possible
            m = re.search(r"Name = '(\w+)'", decl_line)
            if m:
                return f"derived:{m.group(1)}"
            return "derived"
        if "DeclarationTypeSpec -> Class" in decl_line:
            return "class"
        return "unknown"

    def _count_explicit_dimensions(self, first_line):
        """Count additional dimension specifications after the first.

        Handles ExplicitShapeSpec, AssumedShapeSpec, and DeferredShapeSpecList
        continuation lines that follow the initial ArraySpec line.
        Skips child lines (e.g., SpecificationExpr) that are deeper than the
        array spec level.
        """
        count = 0
        if "ExplicitShapeSpec" in first_line or "AssumedShapeSpec" in first_line:
            spec_level = level(first_line)
            while self.peek_next_line():
                nxt = self.peek_next_line()
                nxt_level = level(nxt)
                if nxt_level > spec_level:
                    # Skip child lines (e.g., SpecificationExpr bounds)
                    self.read_next_line()
                    continue
                if nxt_level == spec_level and ("ExplicitShapeSpec" in nxt or "AssumedShapeSpec" in nxt):
                    count += 1
                    self.read_next_line()
                else:
                    break
        return count

    def _parse_entity_decl(self, base_rank):
        """Parse an EntityDecl block and return (name, rank) or (None, 0) if not found.
        
        Parameters
        ----------
        base_rank : int
            The default rank from the type declaration (used if no ArraySpec in entity).
        """
        entity_level = level(self.line)
        entity_name = None
        entity_rank = 0
        
        while self.peek_next_line() and level(self.peek_next_line()) > entity_level:
            entity_line = self.peek_next_line()
            
            if "Name = '" in entity_line:
                m = re.search(r"Name = '(\w+)'", entity_line)
                if m:
                    entity_name = m.group(1)
                self.read_next_line()
            elif "ArraySpec" in entity_line:
                rank = self._parse_array_spec(entity_line)
                if rank is not None:
                    entity_rank = rank
                self.read_next_line()
                entity_rank += self._count_explicit_dimensions(entity_line)
            else:
                self.read_next_line()
        
        # Use entity_rank if found, otherwise use type-level rank
        final_rank = entity_rank if entity_rank > 0 else base_rank
        return entity_name, final_rank

    def _parse_routine_signature(self, routine, arg_names):
        """Parse the SpecificationPart to determine argument types, ranks, and which are optional.
        
        Sets routine.num_required_args, routine.arg_types, routine.arg_ranks, and routine.arg_kinds.
        """
        if not arg_names:
            routine.num_required_args = 0
            routine.arg_names = []
            routine.arg_types = []
            routine.arg_ranks = []
            routine.arg_kinds = []
            return
            
        # Look for SpecificationPart
        if not self.peek_next_line() or "| SpecificationPart" not in self.peek_next_line():
            n = len(arg_names)
            routine.arg_names = list(arg_names)  # Store names even if types unknown
            routine.arg_types = ["unknown"] * n
            routine.arg_ranks = [0] * n
            routine.arg_kinds = [None] * n
            routine.num_required_args = n
            return
            
        self.read_next_line()  # consume SpecificationPart line
        spec_level = level(self.line)
        
        # Track argument info
        optional_args = set()
        arg_type_map = {}
        arg_rank_map = {}
        arg_kind_map = {}
        
        # Current declaration state
        decl_type = "unknown"
        decl_is_optional = False
        decl_rank = 0
        decl_kind = None
        
        while self.peek_next_line():
            next_line = self.peek_next_line()
            
            if level(next_line) <= spec_level:
                break
            
            # New TypeDeclarationStmt - reset state
            if "TypeDeclarationStmt" in next_line:
                decl_is_optional = False
                decl_type = "unknown"
                decl_rank = 0
                decl_kind = None
                self.read_next_line()
                continue
            
            # Extract type from DeclarationTypeSpec
            if "DeclarationTypeSpec" in next_line:
                decl_type = self._extract_type_from_decl(next_line)
                decl_kind = self._extract_kind_from_line(next_line) or decl_kind
                if decl_type == "derived":
                    self.read_next_line()
                    if self.peek_next_line() and "DerivedTypeSpec" in self.peek_next_line():
                        self.read_next_line()
                        if self.peek_next_line() and "Name = " in self.peek_next_line():
                            m = re.search(r"Name = '(\w+)'", self.read_next_line())
                            if m:
                                decl_type = f"derived:{m.group(1)}"
                    continue
                self.read_next_line()
                continue
            
            # Kind selector
            kind = self._extract_kind_from_line(next_line)
            if kind:
                decl_kind = kind
                self.read_next_line()
                continue
            
            # Optional attribute
            if "AttrSpec -> Optional" in next_line:
                decl_is_optional = True
                self.read_next_line()
                continue
            
            # Array specification (type-level rank)
            if "AttrSpec -> ArraySpec" in next_line:
                rank = self._parse_array_spec(next_line)
                if rank is not None:
                    decl_rank = rank
                self.read_next_line()
                decl_rank += self._count_explicit_dimensions(next_line)
                continue
                
            # EntityDecl - extract variable name and entity-level rank
            if "EntityDecl" in next_line:
                self.read_next_line()
                decl_name, entity_rank = self._parse_entity_decl(decl_rank)
                
                if decl_name:
                    self.add_variable(decl_name, VariableInfo(type=decl_type, rank=entity_rank, kind=decl_kind))
                    if decl_name in arg_names:
                        arg_type_map[decl_name] = decl_type
                        arg_rank_map[decl_name] = entity_rank
                        arg_kind_map[decl_name] = decl_kind
                        if decl_is_optional:
                            optional_args.add(decl_name)
                continue
            
            self.read_next_line()
        
        # Build ordered lists based on arg_names order
        routine.arg_names = list(arg_names)  # Store the argument names for keyword matching
        routine.arg_types = [arg_type_map.get(name, "unknown") for name in arg_names]
        routine.arg_ranks = [arg_rank_map.get(name, 0) for name in arg_names]
        routine.arg_kinds = [arg_kind_map.get(name, None) for name in arg_names]
        routine.num_required_args = routine.num_args - len(optional_args)

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
                assert end_name == self.curr.routine.name, self.msg(f"EndSubroutineStmt name {end_name} does not match Subroparse_subroutine_call_stmtutineStmt name {self.curr.routine.name}")
            self.curr.routine = self.curr.parent_routine
            self.curr.parent_routine = None
            return True
        return False

    def parse_only_clause(self):
        if "| Only" not in self.line:
            return False

        used_name = None
        used_name_alias = None # for rename clauses
        if (m := re.search(r"Only -> GenericSpec -> Name = '(\w+)'", self.line)):
            used_name = m.group(1)
        elif (m := re.search(r"Only -> GenericSpec -> DefinedOperator -> IntrinsicOperator = (\w+)", self.line)):
            used_name = m.group(1)
        elif re.search(r"Only -> GenericSpec -> Assignment", self.line):
            used_name = "assignment(=)"
        elif re.search(r"Only -> Rename -> Names", self.line):
            self.line = self.read_next_line()
            m = re.search(r"Name = '(\w+)'", self.line)
            assert m, self.msg("Only Rename syntax not recognized")
            used_name_alias = m.group(1)
            self.line = self.read_next_line()
            m = re.search(r"Name = '(\w+)'", self.line)
            assert m, self.msg("Only Rename syntax not recognized")
            used_name = m.group(1)
        else:
            raise ValueError(self.msg("Only syntax not recognized"))

        assert self.curr.used_module, self.msg("Only clause found without a preceding UseStmt")

        if used_name_alias:
            # It's a rename in an Only clause
            used_renames = self.curr.scope.used_renames_lists[self.curr.used_module]
            used_renames.append((used_name_alias, used_name))
        else:
            # Regular only clause
            used_names = self.curr.scope.used_names_lists[self.curr.used_module]
            if used_names and used_names[0] == '*':
                pass
            else:
                used_names.append(used_name)

        return True

    def parse_rename_clause(self):
        if "| Rename" not in self.line:
            return False
        
        assert self.line.endswith("Rename -> Names"), self.msg("Rename syntax not recognized")
        assert self.curr.used_module, self.msg("Rename clause found without a preceding UseStmt")

        self.line = self.read_next_line()
        m = re.search(r"Name = '(\w+)'", self.line)
        assert m, self.msg("Rename syntax not recognized")
        used_name_alias = m.group(1)
        self.line = self.read_next_line()
        m = re.search(r"Name = '(\w+)'", self.line)
        assert m, self.msg("Rename syntax not recognized")
        used_name = m.group(1)

        used_renames = self.curr.scope.used_renames_lists[self.curr.used_module]
        used_renames.append((used_name_alias, used_name))

        if "| Rename" not in self.peek_next_line():
            self.curr.used_module = None

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
        assert next_line is not None, self.msg("Unexpected end of file after UseStmt")
        if "| Only" in next_line:
            if self.curr.used_module not in self.curr.scope.used_names_lists:
                self.curr.scope.used_names_lists[self.curr.used_module] = []
            if self.curr.used_module not in self.curr.scope.used_renames_lists:
                self.curr.scope.used_renames_lists[self.curr.used_module] = []
        elif "| Rename" in next_line:
            if self.curr.used_module not in self.curr.scope.used_names_lists:
                self.curr.scope.used_names_lists[self.curr.used_module] = ['*']
            if self.curr.used_module not in self.curr.scope.used_renames_lists:
                self.curr.scope.used_renames_lists[self.curr.used_module] = []
        else:
            self.curr.scope.used_names_lists[self.curr.used_module] = ['*']
            self.curr.scope.used_renames_lists[self.curr.used_module] = []
            self.curr.used_module = None

        return True

    def parse_derived_type_stmt(self):

        if "DerivedTypeDef" not in self.line:
            return False

        assert not self.curr.in_derived_type, self.msg("Nested DerivedTypeDef not supported")
        assert self.line.endswith("DeclarationConstruct -> SpecificationConstruct -> DerivedTypeDef")
        self.read_next_line()
        assert self.line.endswith("| DerivedTypeStmt"), self.msg("DerivedTypeStmt syntax not recognized")
        self.read_next_line()

        # Check for EXTENDS and other TypeAttrSpec
        parent_type_name = None
        while "| TypeAttrSpec" in self.line:
            m = re.search(r"TypeAttrSpec -> Extends -> Name = '(\w+)'", self.line)
            if m:
                parent_type_name = m.group(1)
            self.read_next_line()

        m = re.search(r"Name = '(\w+)'", self.line)
        assert m, self.msg("DerivedTypeStmt Name syntax not recognized")
        derived_type_name = m.group(1)
        self.curr.derived_type = self.nr.DerivedType(derived_type_name, self.curr.scope)
        if parent_type_name:
            self.curr.derived_type.parent_type_name = parent_type_name
        return True
    
    def parse_end_derived_type_stmt(self):
        if "| EndTypeStmt" not in self.line:
            return False
        assert self.curr.in_derived_type, self.msg("EndTypeStmt found without a preceding DerivedTypeStmt")
        m = re.search(r"EndTypeStmt -> Name = '(\w+)'", self.line)
        if m:
            end_type_name = m.group(1)
            assert end_type_name == self.curr.derived_type.name, self.msg(f"EndTypeStmt name {end_type_name} does not match DerivedTypeStmt name {self.curr.derived_type.name}")
        self.curr.derived_type = None
        return True


    def parse_type_bound_proc_binding(self):
        """Parse TypeBoundProcBinding to record binding_name -> impl_name mappings.

        In Fortran, derived types can have type-bound procedures:
            procedure :: reset => reset_bounds   ! binding_name=reset, impl_name=reset_bounds
            procedure :: get_imin                 ! binding_name=impl_name=get_imin

        In the parse tree these appear as:
            TypeBoundProcBinding -> TypeBoundProcedureStmt -> WithoutInterface
              TypeBoundProcDecl
                Name = 'binding_name'
                Name = 'impl_name'       (only present when => is used)
        """
        if "TypeBoundProcBinding" not in self.line:
            return False

        if not self.curr.in_derived_type:
            return False

        binding_level = level(self.line)
        binding_name = None
        impl_name = None

        # Read through nested lines to find the name(s)
        while self.peek_next_line():
            next_line = self.peek_next_line()
            next_lvl = level(next_line)

            if next_lvl <= binding_level:
                break

            m = re.search(r"Name = '(\w+)'", next_line)
            if m:
                if binding_name is None:
                    binding_name = m.group(1)
                else:
                    impl_name = m.group(1)

            self.read_next_line()

        # If no impl_name, the binding name IS the impl name
        if binding_name and not impl_name:
            impl_name = binding_name

        if binding_name and impl_name:
            self.curr.derived_type.bindings[binding_name] = impl_name

        return True

    def parse_variable_declaration(self):
        """Parse TypeDeclarationStmt to track variable types, ranks, and kinds."""
        if "TypeDeclarationStmt" not in self.line:
            return False
        
        # Skip if inside a derived type definition (component declarations)
        if self.curr.in_derived_type:
            return False
        
        stmt_level = level(self.line)
        var_type = "unknown"
        var_rank = 0
        var_kind = None
        
        while self.peek_next_line() and level(self.peek_next_line()) > stmt_level:
            next_line = self.peek_next_line()
            
            # Extract type from DeclarationTypeSpec
            if "DeclarationTypeSpec" in next_line:
                var_type = self._extract_type_from_decl(next_line)
                var_kind = self._extract_kind_from_line(next_line) or var_kind
                if "DoublePrecision" in next_line:
                    var_kind = "r8_kind"
                self.read_next_line()
            # Array rank in AttrSpec
            elif "AttrSpec -> ArraySpec" in next_line:
                rank = self._parse_array_spec(next_line)
                if rank is not None:
                    var_rank = rank
                self.read_next_line()
                var_rank += self._count_explicit_dimensions(next_line)
            # EntityDecl block
            elif "EntityDecl" in next_line and "Name = " not in next_line:
                self.read_next_line()
                entity_name, entity_rank = self._parse_entity_decl(var_rank)
                if entity_name:
                    self.add_variable(entity_name, VariableInfo(type=var_type, rank=entity_rank, kind=var_kind))
            # Direct name (inline EntityDecl)
            elif "Name = '" in next_line and "EntityDecl" not in self.line:
                m = re.search(r"Name = '(\w+)'", next_line)
                if m:
                    self.add_variable(m.group(1), VariableInfo(type=var_type, rank=var_rank, kind=var_kind))
                self.read_next_line()
            else:
                self.read_next_line()
        
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
                procedure = self.find_named_entity(self.curr.program_unit, procedure_name)
                assert procedure is not None, self.msg(f"Could not find module procedure '{procedure_name}' for interface '{interface_name}'")
                interface.procedures.add(procedure)
                continue
            assert False, self.msg("InterfaceSpecification syntax not recognized")
        
        return True

    def find_named_entity(self, origin, name):
        """Finds a named entity (subroutine, function, or interface) by name in the current parse tree.

        Parameters
        ----------
        origin : Routine or ProgramUnit
            The origin routine or program unit where the search starts.
        name : str
            The name of the entity to find.

        Returns
        -------
        Node or None
            The found entity, or None if not found.
        """

        origin_unit = origin.program_unit if hasattr(origin, 'program_unit') else origin

        if origin_unit is None:
            print(f"Warning: origin_unit is None when searching for {name} from {origin}")
            raise ValueError("origin_unit is None")

        visited = set() # to avoid repetition

        def dfs(current_unit, name):

            if (current_unit, name) in visited:
                return None
            visited.add((current_unit, name))

            # Check subroutines
            for subr in current_unit.subroutines:
                if subr.name == name:
                    return subr

            # Check functions
            for func in current_unit.functions:
                if func.name == name:
                    return func

            # Check interfaces
            for intf in current_unit.interfaces:
                if intf.name == name:
                    return intf

            # Recurse on used modules
            for used_mod in current_unit.used_names_lists.keys():
                if '*' in current_unit.used_names_lists[used_mod]:
                    result = dfs(used_mod, name)
                    if result is not None:
                        return result
                if name in current_unit.used_names_lists[used_mod]:
                    return self.find_named_entity(used_mod, name)
            
            # Recurse on used modules via renames
            found_alias = False
            for used_mod, renames in current_unit.used_renames_lists.items():
                for alias, original_name in renames:
                    if alias == name:
                        result = self.find_named_entity(used_mod, original_name)
                        if result is not None:
                            return result
                        found_alias = True
                        break
                if found_alias:
                    break

            return None

        return dfs(origin_unit, name)

    def parse_subroutine_call_stmt(self):

        if not "CallStmt" in self.line:
            return False

        assert self.line.endswith("ActionStmt -> CallStmt"), self.msg("CallStmt syntax not recognized")
        assert self.curr.program_unit is not None, self.msg("CallStmt found outside of a program unit")

        self.line = self.read_next_line()
        assert self.line.endswith("| Call"), self.msg("CallStmt syntax not recognized.")
        call_level = level(self.line)

        self.line = self.read_next_line()
        if self.line.endswith("ProcedureDesignator -> ProcComponentRef -> Scalar -> StructureComponent"):
            designator_level = level(self.line)
            binding_name, object_name = self._extract_structure_component_name(designator_level)
            if binding_name is None:
                return
            # Look up the object's declared type so we resolve the correct binding
            obj_type_name = None
            if object_name:
                var_info = self.get_variable(object_name)
                if var_info and var_info.type.startswith('derived:'):
                    obj_type_name = var_info.type[len('derived:'):]
            if obj_type_name is not None:
                callee_name, defining_scope = self._resolve_binding_name(binding_name, obj_type_name)
            else:
                callee_name, defining_scope = binding_name, None
            call_arg_types, call_arg_ranks, call_arg_kinds, call_arg_names = self.parse_call_arguments(call_level)
            self._record_call_dependencies(callee_name, call_arg_types, call_arg_ranks, call_arg_kinds, call_arg_names,
                                           defining_scope=defining_scope)
            return
        m = re.search(r"ProcedureDesignator -> Name = '(\w+)'", self.line)
        if not m:
            raise ValueError(self.msg("ProcedureDesignator syntax not recognized"))
        callee_name = m.group(1)

        call_arg_types, call_arg_ranks, call_arg_kinds, call_arg_names = self.parse_call_arguments(call_level)
        self._record_call_dependencies(callee_name, call_arg_types, call_arg_ranks, call_arg_kinds, call_arg_names)

    def parse_function_call_stmt(self):

        # todo: flang parse tree treats array accesses as function calls, need to filter those out

        if "FunctionReference -> Call" not in self.line:
            return False

        assert self.curr.program_unit is not None, self.msg("FunctionReference found outside of a program unit")
        call_level = level(self.line)

        self.line = self.read_next_line()
        assert "ProcedureDesignator" in self.line, self.msg("FunctionReference syntax not recognized")

        callee_name = None
        defining_scope = None
        m = re.search(r"ProcedureDesignator -> Name = '(\w+)'", self.line)
        if m:
            callee_name = m.group(1)
        elif "ProcComponentRef" in self.line:
            designator_level = level(self.line)
            binding_name, object_name = self._extract_structure_component_name(designator_level)
            if binding_name is None:
                return True
            # Look up the object's declared type so we resolve the correct binding
            obj_type_name = None
            if object_name:
                var_info = self.get_variable(object_name)
                if var_info and var_info.type.startswith('derived:'):
                    obj_type_name = var_info.type[len('derived:'):]
            if obj_type_name is not None:
                callee_name, defining_scope = self._resolve_binding_name(binding_name, obj_type_name)
            else:
                callee_name, defining_scope = binding_name, None
        else:
            l = level(self.line)
            while level(self.line) >= l:
                self.line = self.read_next_line()
                if level(self.line) == l+1 and '| Name = ' in self.line:
                    m = re.search(r"Name = '(\w+)'", self.line)
                    if m:
                        callee_name = m.group(1)
                    break
            assert callee_name is not None, self.msg("FunctionReference syntax not recognized")
        
        if is_fortran_intrinsic(callee_name):
            return True

        call_arg_types, call_arg_ranks, call_arg_kinds, call_arg_names = self.parse_call_arguments(call_level)
        self._record_call_dependencies(callee_name, call_arg_types, call_arg_ranks, call_arg_kinds, call_arg_names, is_function=True, defining_scope=defining_scope)

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
                if self.parse_rename_clause():
                    continue
                if self.parse_use_stmt():
                    continue
                if self.parse_derived_type_stmt():
                    continue
                if self.parse_type_bound_proc_binding():
                    continue
                if self.parse_end_derived_type_stmt():
                    continue
                if self.parse_variable_declaration():
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
                if self.parse_derived_type_stmt():
                    continue
                if self.parse_type_bound_proc_binding():
                    continue
                if self.parse_end_derived_type_stmt():
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
                if self.parse_derived_type_stmt():
                    continue
                if self.parse_end_derived_type_stmt():
                    continue
                if self.parse_module_stmt():
                    continue
                if self.parse_end_module_stmt():
                    continue
                if self.parse_program_unit():
                    continue
                if self.parse_subroutine_call_stmt():
                    continue
                if self.parse_function_call_stmt():
                    continue
            return self.unfound_subroutine_calls, self.unfound_function_calls
        finally:
            self.reset()


