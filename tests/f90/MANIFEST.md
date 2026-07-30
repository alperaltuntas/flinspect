# Conformance corpus manifest (D7)

Maps each Fortran construct the frontend parses to the fixture that pins it and
the parser code path that consumes it (all paths in
`flinspect/frontend/flang_dump.py` unless noted). The corpus is the
format-stability defense of VISION D7: on an LLVM upgrade, regenerate with
`./gen_ptree_files.sh` (version stamped into `PROVENANCE`) and the failures
localize which constructs' dump format moved.

Two assertion tiers per construct:
- **dump snapshot** — the committed `*_ptree` file itself; regenerate + `git diff`
  is the early-warning tier;
- **IR assertions** — `tests/test_ir.py` (above the seam) and
  `tests/frontend/test_flang_dump.py` (below it) are the contract tier.

| Construct | Fixture | Parser code path |
|---|---|---|
| Module / END module bracketing | every fixture | `parse_module_stmt`, `parse_end_module_stmt` |
| Subroutine/function definitions, dummy lists | every fixture | `parse_routine_begin`, `parse_routine_end` |
| Signature facts: arg types/ranks/kinds, OPTIONAL | `test_interface_basic`, `test_interface_rank`, `test_optional_args` | `_parse_routine_signature`, `_extract_type_from_decl`, `_parse_array_spec`, `_kind_selector_name` |
| USE with only-list | `test_private_specifics`, `test_external_calls` | `parse_use_stmt`, `parse_only_clause` |
| USE, whole-module (wildcard) | `test_interface_basic`, `test_type_bound_generic`, … | `parse_use_stmt` |
| Generic interface block (`module procedure`) | `test_interface_basic` (types), `test_interface_rank` (ranks) | `parse_interface_stmt` |
| Generic subroutine CALL, resolved by sema | `test_interface_basic`, `test_interface_rank` | `parse_subroutine_call_stmt`, `_sema_answer`, `_classify_event` |
| Generic function reference in an expression | `test_generic_function` | `parse_function_call_stmt`, the `_expr_stack` in `parse_calls` |
| Keyword actual arguments | `test_keyword_args` | call texts via `_sema_answer` (`call_candidates` ignores `kw=`) |
| Calls omitting OPTIONAL arguments | `test_optional_args` | `parse_subroutine_call_stmt` + sema answer |
| Array-section actual argument (rank reduction) | `test_func_ref_array` | `parse_subroutine_call_stmt` (sema resolves the specific) |
| Assumed-shape declarations (explicit lower bounds) | `test_assumed_shape` | `_parse_array_spec`, `_count_explicit_dimensions` |
| Structure-component actual arguments (`cs%field`) | `test_struct_component` | `parse_subroutine_call_stmt` + sema answer |
| Derived type + type-bound bindings (specific, `=>` rename, generic) | `test_type_bound_generic` | `parse_derived_type_stmt`, `parse_type_bound_proc_binding` |
| Type-bound CALL, static dispatch (sema hoists the object) | `test_type_bound_generic` | `_extract_structure_component_name`, `_classify_type_bound` |
| PUBLIC/PRIVATE accessibility (default + per-name) | `test_private_specifics` | `parse_access_stmt`, `_exports` / `find_named_entity` |
| Mangled resolved names (`imported$owner$specific`) | `test_private_specifics` | `_flang_text.demangle`, `_edges_for_mangled` |
| Unresolved externals → first-class `defined=False` targets | `test_external_calls` | `_classify_event` unresolved branch, `_unknown_target` |
| Local variable declarations (type/rank/kind; `type(t)` / `class(t)`) | `test_interface_rank`, `test_type_bound_generic` | `parse_variable_declaration` |

## Known gaps (parser paths with no fixture yet)

Recorded per the D7 coverage rule — every parse branch should gain a fixture;
these don't have one yet:

- **USE renames** (`use m, alias => name`; only-list and bare forms) —
  `parse_rename_clause` / the rename branches of `find_named_entity` are
  exercised only by unit tests over a hand-built registry.
- **Dynamic type-bound dispatch** (polymorphic receiver keeping `obj%binding(...)`
  in the unparse; deferred bindings) — `_classify_type_bound`'s
  `assumed`/`unresolved` branches; currently covered only by the production
  corpus replay.
- **Derived-type EXTENDS** (inheritance; the `_binding_impls` ancestor walk and
  the ParseForest type-extension edges).
- **Nested (CONTAINS'd) routines** inside a routine.
- **Main PROGRAM and module-less subprogram files** — `parse_program_unit`'s
  `MainProgram` / `Subprogram` branches.
- **Scope-qualified unresolved targets** (only-list import from a module outside
  the parsed set) — cannot be fixtured self-contained (sema needs the `.mod`);
  unit-tested against a hand-built registry (`TestUseChainModule`).
