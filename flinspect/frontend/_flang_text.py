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
# with-sema vs no-sema line shapes
#
# `-fdebug-dump-parse-tree` (with sema) differs from `-...-no-sema` in two ways
# that matter to a line matcher:
#
#   1. Statement and expression nodes gain an *unparse annotation* — the source
#      they unparse to after semantic analysis:
#          ActionStmt -> CallStmt = 'CALL compute_real(r,1_4)'
#          ActualArg -> Expr = '1_4'
#      Only `CallStmt`, `AssignmentStmt`, `Expr` and `Variable` carry one; other
#      nodes (`SubroutineStmt`, `UseStmt`, …) are unchanged.
#   2. Because an annotated `Expr` occupies the line by itself, its structural
#      child is pushed one level deeper:
#          no-sema:  ActualArg -> Expr -> LiteralConstant -> IntLiteralConstant = '1'
#          sema:     ActualArg -> Expr = '1_4'
#                      LiteralConstant -> IntLiteralConstant = '1'
#
# The two helpers below let the matchers accept either variant: `node_path`
# ignores the annotation, and `splice_annotated_child` collapses (2) back into
# the single line a no-sema dump would have produced.
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


def splice_annotated_child(line, child):
    """Collapse an annotated node and its structural child onto one line.

    Reproduces the single line a no-sema dump would have emitted, so structural
    matchers keep working unchanged on with-sema input.
    """
    return f"{node_path(line)} -> {child.lstrip('| ').rstrip()}"


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