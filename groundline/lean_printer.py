"""Lean printer: render a pointized, functionalized kernel as Lean 4.

The output models real arithmetic over ℝ (VISION D6) and mirrors the *source's
own* expression shapes: source parentheses are preserved (``Paren``), operator
spellings map one-to-one, and nothing is algebraically simplified — fidelity is
the printer's whole job; equivalence is the theorem prover's.

Trusted-base rule: deterministic, no I/O beyond the returned string, small
enough to audit line by line against ``kir.py``.
"""

from __future__ import annotations

from groundline.kir import (
    ArrayRef, BinOp, Call, Cmp, ComponentRef, Cond, Expr, FunExpr, IfExpr,
    IntLit, Kernel, Let, Neg, Param, Paren, RealLit, Tuple_,
    UnsupportedConstruct, Var, functionalize,
)

# Operator spelling and precedence (higher binds tighter). Lean and Fortran
# agree on these levels for the supported subset.
_BIN = {"add": ("+", 1), "sub": ("-", 1), "mul": ("*", 2), "div": ("/", 2),
        "pow": ("^", 3)}
_CMP = {"lt": "<", "le": "≤", "gt": ">", "ge": "≥", "eq": "=", "ne": "≠"}


def _real_lit(text: str) -> str:
    """Print a Fortran real literal as a Lean numeral (``3.0`` → ``3``)."""
    if "." in text:
        whole, frac = text.split(".", 1)
        if frac.strip("0") == "":
            return whole or "0"
    return text


def print_expr(e: Expr, parent_prec: int = 0, right: bool = False) -> str:
    if isinstance(e, RealLit):
        return _real_lit(e.text)
    if isinstance(e, IntLit):
        return e.text
    if isinstance(e, Var):
        return e.name
    if isinstance(e, Paren):
        return f"({print_expr(e.inner)})"
    if isinstance(e, Neg):
        # Fortran only admits unary minus on a whole term (R1008), but Lean's
        # prefix `-` binds tighter than `*`, so a compound operand must regain
        # its grouping explicitly: Neg(2*x) prints as -(2 * x). Leaves — and
        # Paren/Call, which bring their own delimiters — stay bare.
        compound = isinstance(e.inner, (BinOp, Cmp, Cond))
        inner = f"({print_expr(e.inner)})" if compound else print_expr(e.inner)
        s = f"-{inner}"
        return f"({s})" if parent_prec > 1 else s
    if isinstance(e, BinOp):
        sym, prec = _BIN[e.op]
        lhs = print_expr(e.lhs, prec, right=False)
        rhs = print_expr(e.rhs, prec, right=True)
        s = f"{lhs} {sym} {rhs}"
        # Parenthesize when the source AST demands grouping the source text
        # didn't spell out (all supported ops are left-associative in both
        # languages except ^, which only takes literal exponents here).
        if prec < parent_prec or (prec == parent_prec and right):
            return f"({s})"
        return s
    if isinstance(e, Cmp):
        return f"{print_expr(e.lhs, 1)} {_CMP[e.op]} {print_expr(e.rhs, 1)}"
    if isinstance(e, Call):
        if e.name == "abs" and len(e.args) == 1:
            return f"|{print_expr(e.args[0])}|"
        if e.name in ("min", "max"):
            args = ", ".join(print_expr(a) for a in e.args)
            return f"{e.name} {args}" if len(e.args) != 2 else \
                f"{e.name} ({print_expr(e.args[0])}) ({print_expr(e.args[1])})"
        raise UnsupportedConstruct(f"cannot print call to '{e.name}'")
    if isinstance(e, Cond):
        # Inline conditional from a merged control-flow join. `if then else`
        # sits below every operator in Lean, so any operand position
        # (parent_prec > 0) needs parentheses.
        s = (f"if {print_expr(e.cond)} then {print_expr(e.then)} "
             f"else {print_expr(e.orelse)}")
        return f"({s})" if parent_prec > 0 else s
    if isinstance(e, ArrayRef):
        raise UnsupportedConstruct(f"array reference '{e.name}' survived pointization")
    if isinstance(e, ComponentRef):
        raise UnsupportedConstruct(
            f"component reference '{e.base}%{e.comp}' survived pointization")
    raise UnsupportedConstruct(f"cannot print {type(e).__name__}")


def _print_fun(fe: FunExpr, indent: int) -> list[str]:
    ind = "  " * indent
    if isinstance(fe, Let):
        return [f"{ind}let {fe.name} := {print_expr(fe.value)}"] + \
            _print_fun(fe.body, indent)
    if isinstance(fe, Tuple_):
        return [f"{ind}{_tuple_text(fe)}"]
    if isinstance(fe, IfExpr):
        lines = [f"{ind}if {print_expr(fe.cond)} then"]
        lines += _print_fun(fe.then, indent + 1)
        lines += _print_else(fe.orelse, indent)
        return lines
    raise UnsupportedConstruct(f"cannot print {type(fe).__name__}")


def _print_else(fe: FunExpr, indent: int) -> list[str]:
    ind = "  " * indent
    if isinstance(fe, Tuple_):                       # compact: else (a, b)
        return [f"{ind}else {_tuple_text(fe)}"]
    if isinstance(fe, IfExpr):                       # chain: else if ... then
        lines = [f"{ind}else if {print_expr(fe.cond)} then"]
        lines += _print_fun(fe.then, indent + 1)
        lines += _print_else(fe.orelse, indent)
        return lines
    return [f"{ind}else"] + _print_fun(fe, indent + 1)


def _tuple_text(t: Tuple_) -> str:
    inner = ", ".join(print_expr(e) for e in t.elems)
    return f"({inner})" if len(t.elems) != 1 else inner


def print_kernel(kernel: Kernel, *, provenance: str = "") -> str:
    """Render a pointized kernel as a complete Lean ``def``.

    ``kernel`` must already be pointized (rank-0 params only); this function
    runs :func:`~groundline.kir.functionalize` itself so printing stays the
    single entry point.
    """
    params, outputs, body = functionalize(kernel)
    non_real = [p for p in params if p.type != "real"]
    if non_real:
        raise UnsupportedConstruct(
            f"{kernel.name}: non-real parameters survived pointization: "
            f"{[p.name for p in non_real]}")
    args = " ".join(p.name for p in params)
    ret = " × ".join("ℝ" for _ in outputs)
    # Name the outputs by their actual intents (dedup, declaration order).
    intents = []
    for p in params:
        if p.intent in ("inout", "out") and p.intent not in intents:
            intents.append(p.intent)
    kinds = "/".join(f"`intent({i})`" for i in intents)
    doc = (f"/-- Generated from {provenance}.\n"
           f"Outputs `({', '.join(outputs)})` — the {kinds} arguments, "
           f"modeled functionally over ℝ. -/\n") if provenance else ""
    header = f"{doc}def {kernel.name} ({args} : ℝ) : {ret} :="
    return "\n".join([header] + _print_fun(body, 1)) + "\n"


def print_module(kernels: list[tuple[Kernel, str]], *, namespace: str,
                 blurb: str) -> str:
    """Render a full Lean module for generated kernels (imports + namespace).

    ``blurb`` is the module-header provenance text — the caller (the kernel
    bank, ``groundline/kernel_bank.py``) owns it, since provenance names the
    manifest and toolchain; the semantic rendering below is identical for
    every frontend."""
    defs = "\n".join(print_kernel(k, provenance=prov) for k, prov in kernels)
    return f"""import Mathlib.Data.Real.Basic
import Mathlib.Tactic.Ring

set_option linter.style.header false
-- Generated expressions stay on one line, however wide.
set_option linter.style.longLine false
-- Outputs are also inputs; a kernel may never read an output's incoming value.
set_option linter.unusedVariables false

/-!
# GENERATED FILE — do not edit

{blurb}
-/

namespace {namespace}

noncomputable section

{defs}
end

end {namespace}
"""
