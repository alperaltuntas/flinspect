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