import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from groundline.frontend._flang_text import (
    level, is_fortran_intrinsic, node_path, unparse_text, call_candidates, demangle,
)
from groundline.frontend._state import ParseState
from groundline.frontend._variable_info import VariableInfo
from groundline.frontend._nodes import Interface, Callable, DerivedType
from groundline.frontend._registry import NodeRegistry
from groundline.ir import (
    IR, Entity, Signature, Use, FileError,
    MODULE, PROGRAM, SUBPROGRAM, SUBROUTINE, FUNCTION, INTERFACE, DERIVED_TYPE,
    CALLABLE_KINDS,
)


# Confidence strata (D3). Frontend-internal tokens; the IR expresses them as the
# calls_resolved / calls_assumed / calls_unresolved relations.
RESOLVED = "resolved"
ASSUMED = "assumed"
UNRESOLVED = "unresolved"


@dataclass
class CallEvent:
    """One call site, as recorded during the call pass (resolution happens later).

    ``call_text`` is sema's unparse of *this* call: the ``CallStmt`` annotation
    for subroutine calls, the enclosing annotated ``Expr`` for function
    references. Sema resolves generic and type-bound names in that text, so it —
    not the structured tree, which still shows the name as written — carries the
    compiler's answer (DESIGN Q2).
    """

    caller: object                     # Scope node the call was made from
    written_name: str                  # callee as written (generic/binding name)
    call_text: Optional[str]           # sema unparse of this call (None if absent)
    is_function: bool = False
    is_type_bound: bool = False        # a `obj%binding(...)` call
    bound_type_name: Optional[str] = None  # declared derived type of `obj`, if known


@dataclass(frozen=True)
class UnknownTarget:
    """A call target that exists (it is called) but was found nowhere (D3).

    Projected onto the IR as a first-class entity with ``defined=False`` —
    scope-qualified when ``module`` pins the defining module, a bare name atom
    otherwise.
    """

    name: str
    module: Optional[str] = None
    is_function: bool = False


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

        # Call sites recorded by the call pass, resolved later (classify_calls).
        self.call_events = []

        # Stack of enclosing annotated Expr nodes, as (level, unparse_text) —
        # maintained by parse_calls so a FunctionReference can read the exact
        # resolved text of its own call from its parent Expr.
        self._expr_stack = []

        # Variable type tracking: maps (scope_key, var_name) -> VariableInfo.
        # Persists across parsing passes; survives Phase 2 to give `obj%binding()`
        # calls the declared derived type of `obj`.
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
        self._expr_stack = []

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

    def _kind_selector_name(self, line):
        """Extract the kind name from a KindSelector line (e.g. 'r8_kind'), or None.

        The annotated ``Expr`` node ends the KindSelector line
        (``KindSelector -> ... -> Expr = '8_4'``, holding sema's *folded* kind
        value) and the designator sits on the child line, so read the name from
        there.  The kind *name* is deliberately the token kept: kinds are entity
        signature facts, no longer inputs to call resolution (Phase 2 retired
        that engine), and the name is the more readable fact.

        Must be called with *line* already consumed: it may read the child line.
        """
        if "KindSelector" not in line:
            return None
        m = re.search(r"Name = '(\w+)'", line)
        if m:
            return m.group(1)
        if not node_path(line).endswith("Expr"):
            return None
        child = self.peek_next_line()
        if child is None or level(child) <= level(line):
            return None
        self.read_next_line()
        m = re.search(r"Name = '(\w+)'", child)
        return m.group(1) if m else None

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

    def _record_call(self, written_name, call_text, is_function=False,
                     is_type_bound=False, object_name=None):
        """Record a call site as a :class:`CallEvent` (resolution happens later)."""
        bound_type_name = None
        if is_type_bound and object_name:
            var_info = self.get_variable(object_name)
            if var_info and var_info.type.startswith("derived:"):
                bound_type_name = var_info.type[len("derived:"):]
        self.call_events.append(CallEvent(
            caller=self.curr.scope,
            written_name=written_name,
            call_text=call_text,
            is_function=is_function,
            is_type_bound=is_type_bound,
            bound_type_name=bound_type_name,
        ))

    def _skip_call_block(self, call_level):
        """Consume the remainder of a Call node (its argument subtree).

        Note this intentionally preserves the long-standing behaviour that a
        function reference nested in another call's argument list is not recorded
        as a call site of its own (an under-approximation; see DESIGN W2).
        """
        while self.peek_next_line() and level(self.peek_next_line()) > call_level:
            self.read_next_line()

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
                if decl_type in ("derived", "class"):
                    self.read_next_line()
                    if self.peek_next_line() and "DerivedTypeSpec" in self.peek_next_line():
                        self.read_next_line()
                        if self.peek_next_line() and "Name = " in self.peek_next_line():
                            m = re.search(r"Name = '(\w+)'", self.read_next_line())
                            if m:
                                decl_type = f"derived:{m.group(1)}"
                    continue
                self.read_next_line()
                decl_kind = self._kind_selector_name(next_line) or decl_kind
                continue

            # Kind selector on its own line (e.g. `real(kind=r8_kind)`, where the
            # KindSelector is a child of the type spec rather than part of it)
            if "KindSelector" in next_line:
                self.read_next_line()
                decl_kind = self._kind_selector_name(next_line) or decl_kind
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

    def parse_access_stmt(self):
        """Parse an AccessStmt to record module-level public/private accessibility (W4).

        Shapes (with or without names)::

            OtherSpecificationStmt -> AccessStmt
              AccessSpec -> Kind = Private            ! default accessibility
            OtherSpecificationStmt -> AccessStmt
              AccessSpec -> Kind = Public
              AccessId -> GenericSpec -> Name = 'compute'   ! per-name override

        Non-name AccessIds (operators, assignment) are ignored — the call
        resolver only looks up names.
        """
        if not node_path(self.line).endswith("AccessStmt"):
            return False

        stmt_level = level(self.line)
        kind = None
        names = []
        while self.peek_next_line() and level(self.peek_next_line()) > stmt_level:
            child = self.read_next_line()
            if (m := re.search(r"AccessSpec -> Kind = (\w+)", child)):
                kind = m.group(1).lower()
            elif (m := re.search(r"AccessId -> GenericSpec -> Name = '(\w+)'", child)):
                names.append(m.group(1))

        unit = self.curr.program_unit
        if unit is None or self.curr.routine is not None or self.curr.in_derived_type or kind is None:
            return True
        if names:
            for n in names:
                unit.access_overrides[n.lower()] = kind
        else:
            unit.default_access = kind
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
        """Parse a TypeBoundProcBinding into the derived type's binding tables.

        Specific bindings — one TypeBoundProcDecl per bound name, several per
        statement (`procedure :: a, b` or `procedure :: reset => reset_bounds`)::

            TypeBoundProcBinding -> TypeBoundProcedureStmt -> WithoutInterface
              TypeBoundProcDecl
                Name = 'binding_name'
                Name = 'impl_name'       (only present when => is used)
              TypeBoundProcDecl          (next name of the same statement)
                ...

        land in ``bindings`` as binding_name -> impl_name. Generic bindings
        (`generic :: go => go_r, go_i`)::

            TypeBoundProcBinding -> TypeBoundGenericStmt
              GenericSpec -> Name = 'go'
              Name = 'go_r'
              Name = 'go_i'

        land in ``generic_bindings`` as generic name -> [specific binding names].
        """
        if "TypeBoundProcBinding" not in self.line:
            return False

        if not self.curr.in_derived_type:
            return False

        binding_level = level(self.line)
        is_generic = "TypeBoundGenericStmt" in self.line
        dt = self.curr.derived_type

        generic_name = None
        specifics = []          # generic stmt: the specific binding names
        decl_names = []         # current TypeBoundProcDecl's names
        in_decl = False

        def flush_decl():
            if decl_names:
                # first name is the binding; the second (from `=>`) its impl
                dt.bindings[decl_names[0]] = decl_names[1] if len(decl_names) > 1 else decl_names[0]

        while self.peek_next_line():
            next_line = self.peek_next_line()
            if level(next_line) <= binding_level:
                break
            self.read_next_line()

            if "TypeBoundProcDecl" in next_line:
                flush_decl()
                decl_names = []
                in_decl = True
                continue
            m = re.search(r"Name = '(\w+)'", next_line)
            if not m:
                continue
            if is_generic:
                if "GenericSpec" in next_line:
                    generic_name = m.group(1)
                else:
                    specifics.append(m.group(1))
            elif in_decl:
                decl_names.append(m.group(1))
            # names outside any decl (e.g. WithInterface's interface name) are
            # not bindings — ignore them

        flush_decl()
        if is_generic and generic_name and specifics:
            dt.generic_bindings[generic_name] = specifics

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
                self.read_next_line()
                if var_type in ("derived", "class"):
                    # `type(t) :: x` / `class(t) :: x` split over child lines:
                    # DerivedTypeSpec, then Name — read them so the declared type
                    # is usable for resolving `x%binding()` calls.
                    if self.peek_next_line() and "DerivedTypeSpec" in self.peek_next_line():
                        self.read_next_line()
                        if self.peek_next_line() and "Name = " in self.peek_next_line():
                            m = re.search(r"Name = '(\w+)'", self.read_next_line())
                            if m:
                                var_type = f"derived:{m.group(1)}"
                    continue
                var_kind = self._kind_selector_name(next_line) or var_kind
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

    @staticmethod
    def _exports(unit, name):
        """Whether *unit* makes *name* accessible to code that USEs it (W4).

        Decided from the module's parsed AccessStmts: an explicit ``public`` /
        ``private`` naming wins; otherwise the module's default accessibility
        applies. Modules never parsed (external) default to public — their
        contents are unknown anyway.
        """
        overrides = getattr(unit, "access_overrides", {})
        default = getattr(unit, "default_access", "public")
        return overrides.get(name.lower(), default) == "public"

    def find_named_entity(self, origin, name):
        """Finds a callable (subroutine, function, or interface) visible as *name*.

        The search follows the use-chain exactly (principle #7, W4): the origin
        scope's own subprograms and interfaces first (private ones included —
        they are local), then USE'd modules through explicit only-lists and
        renames, then wildcard USEs — crossing into a used module only for names
        that module makes public.

        Parameters
        ----------
        origin : Routine or ProgramUnit
            The scope the name is referenced from.
        name : str
            The name of the entity to find, as visible in *origin*.

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

        def dfs(scope, name):

            if (scope, name) in visited:
                return None
            visited.add((scope, name))

            # Check the scope's own subprograms and interfaces. (A Callable scope
            # has none of these; its own USE statements below still apply.)
            for subr in getattr(scope, "subroutines", ()):
                if subr.name == name:
                    return subr
            for func in getattr(scope, "functions", ()):
                if func.name == name:
                    return func
            for intf in getattr(scope, "interfaces", ()):
                if intf.name == name:
                    return intf

            # Explicit only-list imports: flang already validated the import, so
            # the name's accessibility in used_mod is settled; search used_mod as
            # a fresh origin (its own privates are candidates there).
            for used_mod, names in scope.used_names_lists.items():
                if name in names:
                    result = dfs(used_mod, name)
                    if result is not None:
                        return result

            # Renamed imports: the alias is local; the original name is looked
            # up in the exporting module.
            for used_mod, renames in scope.used_renames_lists.items():
                for alias, original_name in renames:
                    if alias == name:
                        result = dfs(used_mod, original_name)
                        if result is not None:
                            return result

            # Wildcard imports: only names the used module exports are visible.
            for used_mod, names in scope.used_names_lists.items():
                if '*' in names and self._exports(used_mod, name):
                    result = dfs(used_mod, name)
                    if result is not None:
                        return result

            return None

        # A routine scope's own USE statements are searched first, then the
        # enclosing program unit's.
        if origin is not origin_unit:
            result = dfs(origin, name)
            if result is not None:
                return result
        return dfs(origin_unit, name)

    def parse_subroutine_call_stmt(self):

        if not "CallStmt" in self.line:
            return False

        # With sema the statement carries an unparse annotation
        # (`ActionStmt -> CallStmt = 'CALL compute_real(r,1_4)'`) in which generic
        # and type-bound names are already *resolved* — that text is the call's
        # sema answer (DESIGN Q2).
        assert node_path(self.line).endswith("ActionStmt -> CallStmt"), self.msg("CallStmt syntax not recognized")
        assert self.curr.program_unit is not None, self.msg("CallStmt found outside of a program unit")
        call_text = unparse_text(self.line)

        self.line = self.read_next_line()
        assert self.line.endswith("| Call"), self.msg("CallStmt syntax not recognized.")
        call_level = level(self.line)

        self.line = self.read_next_line()
        if self.line.endswith("ProcedureDesignator -> ProcComponentRef -> Scalar -> StructureComponent"):
            designator_level = level(self.line)
            binding_name, object_name = self._extract_structure_component_name(designator_level)
            if binding_name is not None:
                self._record_call(binding_name, call_text,
                                  is_type_bound=True, object_name=object_name)
            self._skip_call_block(call_level)
            return True
        m = re.search(r"ProcedureDesignator -> Name = '(\w+)'", self.line)
        if not m:
            raise ValueError(self.msg("ProcedureDesignator syntax not recognized"))
        self._record_call(m.group(1), call_text)
        self._skip_call_block(call_level)
        return True

    def parse_function_call_stmt(self):

        # todo: flang parse tree treats array accesses as function calls, need to filter those out

        if "FunctionReference -> Call" not in self.line:
            return False

        assert self.curr.program_unit is not None, self.msg("FunctionReference found outside of a program unit")
        call_level = level(self.line)

        # The exact resolved text of *this* call is the annotation on the
        # enclosing Expr node (the FunctionReference's parent line), which
        # parse_calls tracks on a stack.
        call_text = self._expr_stack[-1][1] if self._expr_stack else None

        self.line = self.read_next_line()
        assert "ProcedureDesignator" in self.line, self.msg("FunctionReference syntax not recognized")

        callee_name = None
        is_type_bound = False
        object_name = None
        m = re.search(r"ProcedureDesignator -> Name = '(\w+)'", self.line)
        if m:
            callee_name = m.group(1)
        elif "ProcComponentRef" in self.line:
            designator_level = level(self.line)
            callee_name, object_name = self._extract_structure_component_name(designator_level)
            if callee_name is None:
                return True
            is_type_bound = True
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

        self._record_call(callee_name, call_text, is_function=True,
                          is_type_bound=is_type_bound, object_name=object_name)
        self._skip_call_block(call_level)
        return True

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
                if self.parse_access_stmt():
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
        """Reads a flang parse tree file and records subroutine/function call sites.

        Call sites land in ``self.call_events``; resolving them into stratified
        edges is :meth:`classify_calls`' job (it needs the whole forest parsed
        first).
        """

        self.call_events = []

        try:
            self.parse_header()

            for self.line in self.lines():
                # Maintain the stack of enclosing annotated Expr nodes: each Expr
                # unparse is the exact resolved text of the (sub)expression it
                # heads, which is how a FunctionReference reads its own call text.
                lvl = level(self.line)
                while self._expr_stack and self._expr_stack[-1][0] >= lvl:
                    self._expr_stack.pop()
                if node_path(self.line).endswith("Expr"):
                    text = unparse_text(self.line)
                    if text is not None:
                        self._expr_stack.append((lvl, text))

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
            return self.call_events
        finally:
            self.reset()

    # -------------------------------------------------------------------------
    # Call classification: sema's answer -> stratified edges (D3)
    # -------------------------------------------------------------------------

    def _sema_answer(self, event):
        """Sema's resolved callee for *event*, read from its unparse text.

        Returns ``("static", name)`` when sema printed the call with a resolved
        procedure name (possibly mangled — see :func:`demangle`), ``("dynamic",
        binding_name)`` when a type-bound call survives as ``obj%binding(...)``
        (dynamic dispatch: sema could not resolve it statically), or ``None``
        when there is no usable answer.
        """
        text = event.call_text
        if not text:
            return None
        body = text[5:] if text.startswith("CALL ") else text
        cands = call_candidates(body)
        if not cands:
            return None
        if event.is_type_bound:
            # Dynamic dispatch keeps the `%binding(` in the text; check it first
            # so an array-element object (`x(i)%go(...)`) can't masquerade as a
            # resolved call to `x`.
            for _, is_bound, name in cands:
                if is_bound and name.lower() == event.written_name.lower():
                    return ("dynamic", event.written_name)
            # Static dispatch: sema hoists the object into the argument list and
            # prints the specific up front: `CALL go_r(obj,1._4)`.
            offset, is_bound, name = cands[0]
            if offset == 0 and not is_bound:
                return ("static", name)
            return None
        # A plain call's own text always starts with its (resolved) callee; a
        # nonzero offset means the text belongs to an enclosing construct and
        # cannot be attributed to this call with certainty.
        offset, is_bound, name = cands[0]
        if offset == 0 and not is_bound:
            return ("static", name)
        return None

    def _procs_named(self, name, is_function):
        """All defined procedures of the right flavour with this name (any scope)."""
        pool = self.nr.functions if is_function else self.nr.subroutines
        return [p for p in pool if p.name.lower() == name.lower()]

    @staticmethod
    def _proc_in_scope(scope, name, is_function):
        """A procedure named *name* among *scope*'s own subprograms, or None."""
        pool = getattr(scope, "functions" if is_function else "subroutines", ())
        for p in pool:
            if p.name.lower() == name.lower():
                return p
        return None

    def _module_named(self, name):
        for mod in self.nr.modules:
            if mod.name.lower() == name.lower():
                return mod
        return None

    @staticmethod
    def _use_chain_module(scope, name):
        """The single module whose only-list/rename imports *name* into *scope*.

        Used to scope-qualify an unresolved target: if the caller (or its
        program unit) imports *name* from exactly one module via an explicit
        only-list or rename, that module is the target's defining scope. A
        wildcard USE pins nothing.
        """
        modules = set()
        scopes = [scope]
        program_unit = getattr(scope, "program_unit", None)
        if program_unit is not None:
            scopes.append(program_unit)
        for s in scopes:
            for used_mod, names in getattr(s, "used_names_lists", {}).items():
                if any(n != "*" and n.lower() == name.lower() for n in names):
                    modules.add(used_mod.name)
            for used_mod, renames in getattr(s, "used_renames_lists", {}).items():
                for alias, _ in renames:
                    if alias.lower() == name.lower():
                        modules.add(used_mod.name)
        return modules.pop() if len(modules) == 1 else None

    def _locate_resolved(self, event, name):
        """Find the procedure entity behind a sema-resolved plain *name*.

        Tried in decreasing order of scope-correctness; sema vouches for the
        name, so a whole-forest unique match is accepted as a last resort (the
        resolved specific need not be accessible by name in the calling scope —
        e.g. a private specific reached through a public generic is printed
        unmangled when the call and definition share a file).
        """
        found = self.find_named_entity(event.caller, name)
        if found is not None and not isinstance(found, Interface):
            return found
        procs = self._procs_named(name, event.is_function)
        if len(procs) == 1:
            return procs[0]
        return None

    def _classify_type_bound(self, event, answer):
        """Stratified edges for a `obj%binding(...)` call."""
        if answer is not None and answer[0] == "static":
            name = answer[1]
            mangled = demangle(name)
            if mangled:
                _, def_mod, specific = mangled
                return self._edges_for_mangled(event, def_mod, specific)
            # Prefer the impl reachable through the object's declared type.
            if event.bound_type_name:
                impl, defining_scope = self._resolve_binding_name(
                    name, event.bound_type_name)
                if defining_scope is not None:
                    target = self._proc_in_scope(defining_scope, impl, event.is_function)
                    if target is not None:
                        return [(RESOLVED, target)]
            target = self._locate_resolved(event, name)
            if target is not None:
                return [(RESOLVED, target)]
            return [(UNRESOLVED, UnknownTarget(name, None, event.is_function))]
        # Dynamic dispatch (or no answer): the declared type's binding table is a
        # guess — an override may be selected at runtime, and a generic binding
        # fans out over its specific bindings.
        edges = []
        if event.bound_type_name:
            for impl, defining_scope in self._binding_impls(
                    event.written_name, event.bound_type_name):
                target = self._proc_in_scope(defining_scope, impl, event.is_function)
                if target is not None:
                    edges.append((ASSUMED, target))
        if edges:
            return edges
        return [(UNRESOLVED,
                 UnknownTarget(event.written_name, None, event.is_function))]

    def _binding_impls(self, binding_name, type_name):
        """Implementation candidates for a type-bound *binding_name* on *type_name*.

        Yields (impl_name, defining_scope) pairs: one for a specific binding,
        one per member for a generic binding. A binding not found on the type
        itself is searched up its EXTENDS chain (inherited bindings); a type's
        own binding shadows the parent's.
        """
        binding_lower = binding_name.lower()
        seen = set()
        queue = [type_name.lower()]
        while queue:
            tname = queue.pop(0)
            if tname in seen:
                continue
            seen.add(tname)
            for dt in self.nr.derived_types:
                if dt.name.lower() != tname:
                    continue
                found_here = False
                for gname, members in dt.generic_bindings.items():
                    if gname.lower() == binding_lower:
                        for member in members:
                            yield dt.bindings.get(member, member), dt.scope
                            found_here = True
                for bname, iname in dt.bindings.items():
                    if bname.lower() == binding_lower:
                        yield iname, dt.scope
                        found_here = True
                if not found_here and dt.parent_type_name:
                    queue.append(dt.parent_type_name.lower())

    def _edges_for_mangled(self, event, owner_mod, specific, interface=None):
        """Stratified edges for a mangled sema answer (`imported$owner$specific`).

        The middle component is the module that *owns the specific's symbol* —
        usually its textual definition site, but the owner can itself hold the
        name by use-association (e.g. `fms2_io_mod$fms2_io_mod$compressed_read_2d`
        whose subroutine body lives in netcdf_io_mod), so the lookup falls back
        to the owner module's use-chain.
        """
        edges = []
        if interface is not None:
            edges.append((RESOLVED, interface))
        module = self._module_named(owner_mod)
        target = None
        if module is not None:
            target = self._proc_in_scope(module, specific, event.is_function)
            if target is None:
                found = self.find_named_entity(module, specific)
                if found is not None and not isinstance(found, Interface):
                    target = found
        if target is not None:
            edges.append((RESOLVED, target))
        else:
            # Sema names the owning module and the specific; the module just
            # isn't in the parsed set. The target identity is certain, so the
            # edge is resolved — to a defined=False entity.
            edges.append((RESOLVED,
                          UnknownTarget(specific, owner_mod, event.is_function)))
        return edges

    def _classify_event(self, event):
        """Resolve one call event into [(stratum, target), ...] edges.

        The confidence rules (D3): an edge whose callee comes from sema's
        unparse — or a direct call to a unique, visible, non-generic procedure —
        is *resolved*; a generic or dynamic-dispatch guess is *assumed*; a target
        found nowhere is *unresolved*. A generic call keeps the caller→interface
        edge alongside the resolved specific edge, mirroring
        ``interface_members``.
        """
        answer = self._sema_answer(event)
        if event.is_type_bound:
            return self._classify_type_bound(event, answer)

        written = event.written_name
        found = self.find_named_entity(event.caller, written)
        iface = found if isinstance(found, Interface) else None

        if answer is not None:
            name = answer[1]
            mangled = demangle(name)
            if mangled:
                _, def_mod, specific = mangled
                return self._edges_for_mangled(event, def_mod, specific, interface=iface)
            if iface is not None:
                edges = [(RESOLVED, iface)]
                member = next((p for p in iface.procedures
                               if p.name.lower() == name.lower()), None)
                if member is not None:
                    edges.append((RESOLVED, member))
                else:
                    # The answer does not line up with the generic's members —
                    # attribution failed, so fall back to the conservative fan-out.
                    edges += [(ASSUMED, p) for p in iface.procedures]
                return edges
            if found is not None:
                if name.lower() in (written.lower(), found.name.lower()):
                    return [(RESOLVED, found)]
                # Sema picked something other than the visible procedure of that
                # name (shouldn't happen; trust sema and try to locate it).
                target = self._locate_resolved(event, name)
                if target is not None:
                    return [(RESOLVED, target)]
                return [(UNRESOLVED, UnknownTarget(name, None, event.is_function))]
            # Nothing visible under the written name.
            if name.lower() == written.lower():
                # Sema echoes the name unchanged: an external / unparsed target.
                module = self._use_chain_module(event.caller, written)
                return [(UNRESOLVED, UnknownTarget(written, module, event.is_function))]
            target = self._locate_resolved(event, name)
            if target is not None:
                return [(RESOLVED, target)]
            return [(UNRESOLVED, UnknownTarget(name, None, event.is_function))]

        # No sema answer (attribution failure).
        if iface is not None:
            # The generic's identity is certain; which specific it dispatches to
            # is not — fan out to every member as assumed.
            return [(RESOLVED, iface)] + [(ASSUMED, p) for p in iface.procedures]
        if found is not None:
            # A direct call to a unique, visible, non-generic procedure.
            return [(RESOLVED, found)]
        module = self._use_chain_module(event.caller, written)
        return [(UNRESOLVED, UnknownTarget(written, module, event.is_function))]

    def classify_calls(self):
        """Resolve all recorded call events into stratified edges.

        Returns a list of ``(caller_node, stratum, target)`` triples, where
        *target* is an interned node or an :class:`UnknownTarget`. Must run after
        every file's structure/interface passes so cross-file lookups see the
        whole forest.
        """
        edges = []
        for event in self.call_events:
            for stratum, target in self._classify_event(event):
                edges.append((event.caller, stratum, target))
        return edges


# ============================================================================= #
# Frontend: orchestrate the parse passes and project the node graph onto the IR.
#
# Everything above this line is the flang-text working representation (ParseTree +
# its node/registry helpers). It stays below the seam. The IR projection below is
# the only thing consumers see (principle #3 — pull complexity down to the
# frontend; principle #10 — be pragmatic with the internal representation).
# ============================================================================= #

def _pu_id(pu):
    """EntityId for a program unit (module / program / subprogram)."""
    return pu.name


def _callable_id(c):
    """Scope-qualified EntityId for a subroutine or function (handles nesting)."""
    if getattr(c, "parent", None) is None:
        return f"{c.program_unit.name}::{c.name}"
    return f"{c.program_unit.name}::{c.parent.name}::{c.name}"


def _iface_id(iface):
    return f"{iface.program_unit.name}::{iface.name}"


def _dt_id(dt):
    return f"{dt.scope.name}::{dt.name}"


def _node_id(node):
    """EntityId for any interned node (used to resolve call targets)."""
    if isinstance(node, Interface):
        return _iface_id(node)
    if isinstance(node, DerivedType):
        return _dt_id(node)
    if isinstance(node, Callable):
        return _callable_id(node)
    return _pu_id(node)


def _signature(c):
    """Project a Callable's argument attributes onto an IR Signature (or None)."""
    if c.arg_types is None and c.arg_names is None:
        return None
    return Signature(
        arg_names=tuple(c.arg_names or ()),
        arg_types=tuple(c.arg_types or ()),
        arg_ranks=tuple(c.arg_ranks or ()),
        arg_kinds=tuple(c.arg_kinds or ()),
        num_required=c.num_required_args,
    )


def _scope_uses(ir, scope_node, scope_id):
    """Project a scope's USE clauses onto IR `uses` edges."""
    names_lists = getattr(scope_node, "used_names_lists", {}) or {}
    renames_lists = getattr(scope_node, "used_renames_lists", {}) or {}
    for used_module in set(names_lists) | set(renames_lists):
        only = tuple(names_lists.get(used_module, []) or [])
        renames = tuple(tuple(r) for r in (renames_lists.get(used_module, []) or []))
        ir.uses.add(Use(scope=scope_id, module=used_module.name,
                        only=only, renames=renames))


def _unknown_target(ir, name, kind, module=None):
    """Intern a referenced-but-undefined call target as a first-class entity.

    The atom is scope-qualified (``module::name``) when the use-chain pins the
    defining module, a bare name atom otherwise (DESIGN §2.1). Guards against the
    freak collision of a bare name atom with an existing non-callable entity.
    """
    eid = f"{module}::{name}" if module else name
    existing = ir.entities.get(eid)
    if existing is not None and existing.kind not in CALLABLE_KINDS:
        eid = f"::{name}"
        existing = ir.entities.get(eid)
    if existing is None:
        ir.entities[eid] = Entity(
            id=eid, kind=kind, name=name,
            scope=module, defined=False,
        )
    return eid


def project_registry(registry, file_errors, call_edges):
    """Walk the interned node graph and build the groundline IR (the seam).

    ``call_edges`` is the classified call relation from
    :meth:`ParseTree.classify_calls`: ``(caller_node, stratum, target)`` triples
    where *target* is an interned node or an :class:`UnknownTarget`.
    """
    ir = IR(file_errors=list(file_errors))

    # --- program units (modules / programs / subprograms) ---
    for pu, kind in (
        [(m, MODULE) for m in registry.modules]
        + [(p, PROGRAM) for p in registry.programs]
        + [(s, SUBPROGRAM) for s in registry.subprograms]
    ):
        pid = _pu_id(pu)
        ir.entities[pid] = Entity(
            id=pid, kind=kind, name=pu.name, scope=None,
            defined=getattr(pu, "parse_tree_path", None) is not None,
        )
        _scope_uses(ir, pu, pid)

    # --- subroutines & functions ---
    for c, kind in (
        [(s, SUBROUTINE) for s in registry.subroutines]
        + [(f, FUNCTION) for f in registry.functions]
    ):
        cid = _callable_id(c)
        scope_id = _callable_id(c.parent) if getattr(c, "parent", None) else _pu_id(c.program_unit)
        ir.entities[cid] = Entity(
            id=cid, kind=kind, name=c.name, scope=scope_id, signature=_signature(c),
        )
        ir.contains.add((scope_id, cid))
        _scope_uses(ir, c, cid)

    # --- interfaces ---
    for iface in registry.interfaces:
        iid = _iface_id(iface)
        pid = _pu_id(iface.program_unit)
        ir.entities[iid] = Entity(id=iid, kind=INTERFACE, name=iface.name, scope=pid)
        ir.contains.add((pid, iid))
        for proc in iface.procedures:
            ir.interface_members.add((iid, _node_id(proc)))

    # --- derived types ---
    for dt in registry.derived_types:
        did = _dt_id(dt)
        scope_id = _pu_id(dt.scope) if hasattr(dt.scope, "parse_tree_path") else _node_id(dt.scope)
        ir.entities[did] = Entity(
            id=did, kind=DERIVED_TYPE, name=dt.name, scope=scope_id,
            parent_type=dt.parent_type_name,
            bindings=tuple(sorted(dt.bindings.items())),
        )
        ir.contains.add((scope_id, did))

    # --- calls, stratified by confidence (D3) ---
    # An UnknownTarget becomes a defined=False entity (first-class partial
    # knowledge, principle #6); everything else is already interned.
    strata = {RESOLVED: ir.calls_resolved,
              ASSUMED: ir.calls_assumed,
              UNRESOLVED: ir.calls_unresolved}
    for caller_node, stratum, target in call_edges:
        if isinstance(target, UnknownTarget):
            kind = FUNCTION if target.is_function else SUBROUTINE
            callee_id = _unknown_target(ir, target.name, kind, target.module)
        else:
            callee_id = _node_id(target)
        strata[stratum].add((_node_id(caller_node), callee_id))

    return ir


class FlangDumpFrontend:
    """Frontend that scrapes flang's textual parse-tree dump into an :class:`IR`.

    Orchestrates the passes across all sources — structure, interfaces, call-site
    recording, then call classification (the order cross-file resolution
    requires) — with per-file fault isolation (W3), and projects the interned
    node graph onto the IR. Implements the
    :class:`~groundline.frontend.base.Frontend` protocol.

    Input is the with-sema dump (``-fdebug-dump-parse-tree``), the sole
    production input per VISION D4: call resolution is read from sema's unparse
    annotations. A no-sema dump still parses, but every generic call degrades to
    an `assumed` fan-out — that path is neither tested nor supported.
    """

    @staticmethod
    def _expand(sources):
        if isinstance(sources, (str, Path)):
            sources = [sources]
        paths = []
        for s in sources:
            p = Path(s)
            if p.is_dir():
                paths.extend(sorted(f for f in p.iterdir() if f.is_file()))
            else:
                paths.append(p)
        return paths

    def extract(self, sources):
        paths = self._expand(sources)
        registry = NodeRegistry()
        trees = []
        file_errors = []

        # Pass 1: structure (must complete for all files before cross-file resolution)
        for path in paths:
            tree = ParseTree(path, registry)
            try:
                tree.parse_structure()
            except Exception as e:  # fault isolation: skip the file, keep going
                file_errors.append(FileError(path, f"parse_structure: {e}"))
                continue
            trees.append(tree)

        # Pass 2: interfaces
        for tree in trees:
            try:
                tree.parse_interfaces()
            except Exception as e:
                file_errors.append(FileError(tree.parse_tree_path, f"parse_interfaces: {e}"))

        # Pass 3: record call sites
        for tree in trees:
            try:
                tree.parse_calls()
            except Exception as e:
                file_errors.append(FileError(tree.parse_tree_path, f"parse_calls: {e}"))

        # Pass 4: classify each call site against the whole forest — sema's
        # unparse answer where it exists, scope-correct lookup otherwise —
        # producing the stratified call relation (D3).
        call_edges = []
        for tree in trees:
            try:
                call_edges.extend(tree.classify_calls())
            except Exception as e:
                file_errors.append(FileError(tree.parse_tree_path, f"classify_calls: {e}"))

        return project_registry(registry, file_errors, call_edges)


