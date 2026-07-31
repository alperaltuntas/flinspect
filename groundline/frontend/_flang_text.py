import re
from pathlib import Path

def level(line):
    """
    Determine the level of indentation based on the number of leading |.
    """
    res = 0
    for c in line:
        if c == '|':
            res += 1
        elif c == ' ':
            continue
        else:
            break

    return res


# ---------------------------------------------------------------------------
# with-sema line shapes
#
# In the `-fdebug-dump-parse-tree` (with-sema) dump, statement and expression
# nodes carry an *unparse annotation* — the source they unparse to after
# semantic analysis:
#     ActionStmt -> CallStmt = 'CALL compute_real(r,1_4)'
#     ActualArg -> Expr = '1_4'
# Only `CallStmt`, `AssignmentStmt`, `Expr` and `Variable` carry one; other
# nodes (`SubroutineStmt`, `UseStmt`, …) do not. An annotated `Expr` occupies
# its line alone, so its structural child sits one level deeper.
#
# `node_path` lets matchers ignore the annotation; `unparse_text` extracts it.
# The annotation is where sema's *resolution* lives (DESIGN Q2): generic and
# type-bound calls are printed with the specific procedure sema picked, so
# `call_candidates` + `demangle` below are how the frontend reads those answers.
# ---------------------------------------------------------------------------

_PAYLOAD_RE = re.compile(r" = '(.*)'\s*$")


def node_path(line):
    """The node path of a dump line, with any trailing ``= '...'`` payload removed.

    Strips both kinds of payload — a with-sema unparse annotation and a
    value-carrying leaf (``Name = 'foo'``) — which is what we want when matching
    on structure alone.
    """
    return _PAYLOAD_RE.sub("", line).rstrip()


def unparse_text(line):
    """The with-sema unparse annotation on *line*, or None if it has none.

    Only meaningful for nodes that carry an annotation rather than a leaf value
    (see the note above); asked of e.g. a ``Name`` line it would return the name.
    """
    m = _PAYLOAD_RE.search(line)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Reading sema's resolution out of an unparse annotation
# ---------------------------------------------------------------------------

# flang's name mangling in unparse text. When the resolved specific procedure is
# not accessible by name in the calling scope (e.g. only the generic is
# USE-imported, or the specifics are private), flang prints a fully qualified
# form:  <module-imported-through>$<symbol-owner-module>$<specific>
# Derived empirically from the MOM6+FMS2 production corpus (994 distinct mangled
# names, all exactly three components): the FIRST component is the module the
# name was imported through; the SECOND is the module that *owns the specific's
# symbol* — usually its definition site (`fms_mod$mpp_mod$mpp_error_basic`: the
# specific lives in mpp_mod), but the owner may itself hold the name by
# use-association (`fms2_io_mod$fms2_io_mod$compressed_read_2d`, whose body
# lives in netcdf_io_mod), so resolution must follow the owner's use-chain.
# Note this is pretty-printer behaviour with no stability contract (DESIGN Q1);
# the conformance fixture `test_private_specifics` pins it.
_MANGLED_RE = re.compile(r"^(\w+)\$(\w+)\$(\w+)$")


def demangle(name):
    """Split a mangled unparse name into (imported_via, owner_module, specific).

    Returns None if *name* is a plain identifier.
    """
    m = _MANGLED_RE.match(name)
    return m.groups() if m else None


# A call site in unparse text: an (optionally mangled) identifier directly
# applied to an argument list, optionally reached through `%` (type-bound).
_CALL_SITE_RE = re.compile(r"(%?)([A-Za-z_][A-Za-z0-9_$]*)\s*\(")

# A double-quoted character literal ('""' is the escaped quote). flang's
# unparser normalizes strings to double quotes.
_STRING_RE = re.compile(r'"(?:[^"]|"")*"')


def call_candidates(text):
    """Ordered call sites in an unparse text, as (offset, is_type_bound, name).

    ``offset`` is the position of the name in *text*; string-literal contents
    are blanked first so a parenthesis inside a message can't fake a call.
    """
    blanked = _STRING_RE.sub(lambda m: '"' * len(m.group(0)), text)
    return [(m.start(2), m.group(1) == "%", m.group(2))
            for m in _CALL_SITE_RE.finditer(blanked)]


_fortran_intrinsics = {
    "abs", "aimag", "aint", "anint", "ceiling", "conjg", "dble",
    "floor", "int", "real", "nint", "mod", "modulo", "sign",

    "acos", "acosd", "acospi", "acosh",
    "asin", "asind", "asinh", "asinpi",
    "atan", "atan2", "atan2d", "atan2pi", "atand", "atanh", "atanpi",
    "cos", "cosd", "cosh",
    "sin", "sind", "sinh",
    "tan", "tand", "tanh",
    "hypot",

    "all", "any", "count",
    "maxval", "minval", "product", "sum",
    "reshape", "pack", "spread", "unpack",
    "transpose",
    "lbound", "ubound", "shape", "size",
    "maxloc", "minloc",

    "and", "ior", "ieor", "not",
    "iand", "ibclr", "ibits", "ibset",
    "btest", "ishft", "ishftc",

    "associated", "allocated", "present",
    "len", "len_trim",
    "kind", "selected_real_kind", "selected_int_kind",

    "achar", "char", "iachar", "ichar",
    "adjustl", "adjustr",
    "index", "scan", "verify",
    "trim", "repeat",

    "date_and_time", "system_clock", "cpu_time",
    "random_number", "random_seed",

    "huge",

    "access",
    "backtrace",
    "abort",

    "atomic_add", "atomic_and", "atomic_cas", "atomic_define",
    "atomic_fetch_add", "atomic_fetch_and",
    "atomic_fetch_or", "atomic_fetch_xor",
    "atomic_or", "atomic_ref", "atomic_xor",

    "bessel_j0", "bessel_j1", "bessel_jn",
    "bessel_y0", "bessel_y1",

    "iall", "iany",

    "min", "max",

        # iso_fortran_env
    "compiler_version",
    "compiler_options",
    "compiler_date",
    "execution_environment",
    "get_environment_variable",
    "get_command_argument",
    "command_argument_count",

    # iso_c_binding
    "c_f_pointer",
    "c_f_procpointer",
    "c_associated",
    "c_loc",
    "c_funloc",
    "null",

    # ieee_arithmetic
    "ieee_is_nan",
    "ieee_is_finite",
    "ieee_is_normal",
    "ieee_copy_sign",
    "ieee_value",
    "ieee_next_after",
    "ieee_class",
    "ieee_support_flags",
    "ieee_support_halting",
    "ieee_get_flag",
    "ieee_set_flag",
    "ieee_get_halting_mode",
    "ieee_set_halting_mode",

    # ieee_exceptions
    "ieee_get_status",
    "ieee_set_status",

    # ieee_features
    "ieee_support_datatype",
    "ieee_support_attribute",
    "ieee_support_rounding",
    "ieee_support_decimal",
    "ieee_support_intrinsic",
    "ieee_support_state",

}

def is_fortran_intrinsic(name):
    return name.lower() in _fortran_intrinsics