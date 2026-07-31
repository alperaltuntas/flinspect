"""Kernel IR (Track B) — per-procedure semantic trees, and the passes that
shape them for the Lean printer.

This is the *second* IR of DESIGN §2.3: deep (typed expression/statement trees)
exactly where the relational IR (`flinspect/ir.py`) is deliberately shallow, and
consumed only by the Lean printer (`flinspect/lean_printer.py`). Nothing here may
leak into the relational IR, and nothing here is flang-specific — a frontend
(`frontend/flang_kernel.py` today) populates it.

Trusted-base rule (VISION D6): everything in this module is deterministic and
small enough to audit. A construct outside the supported subset raises
:class:`UnsupportedConstruct` — refusal, never a guess.

Passes:

- :func:`pointize` — strip a single ``do concurrent`` wrapper and turn every
  array reference indexed *exactly* by the loop indices into a scalar. This is
  the semantic move that pairs a Fortran loop nest with an AMReX per-point
  kernel; it is valid precisely because ``do concurrent`` asserts iteration
  independence. Any other subscript pattern (offsets, masks, partial indexing)
  is refused.
- :func:`functionalize` — turn the imperative body (assignments + structured
  ifs) into a single functional expression tree: local assignments become
  ``Let`` bindings, assignments to inout arguments update a symbolic state, and
  each control-flow path ends by materializing the state tuple. Statements
  *after* an ``If`` (a control-flow join) are supported in exactly one shape:
  the ``If`` has a single branch (no elseif chain) and every branch body is
  assignments to state (output) variables only — no locals (a ``Let`` may not
  escape a branch), no nested ``If``s. Each variable a branch assigned merges
  as ``state'[v] = Cond(cond, state_then[v], state_else[v])``; the remaining
  statements then run against the *merged* state, so a later read of a
  variable the ``If`` may have updated observes the conditional value —
  sequential semantics, as in the source. Any other join shape is refused.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union


class UnsupportedConstruct(Exception):
    """A source construct outside the supported kernel subset (refuse, don't guess)."""


# --------------------------------------------------------------------------- #
# Expressions
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class RealLit:
    text: str          # source spelling, e.g. "3.0"


@dataclass(frozen=True)
class IntLit:
    text: str          # source spelling, e.g. "2"


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class ArrayRef:
    name: str
    subscripts: tuple["Expr", ...]


@dataclass(frozen=True)
class Paren:
    """Source parentheses — semantically transparent, kept so the printed model
    mirrors the source's own grouping (the pilot's fidelity principle)."""
    inner: "Expr"


@dataclass(frozen=True)
class Neg:
    """Unary minus. Fortran only admits it on a whole term (R1008), so the
    frontend produces it wrapping either a leaf or an entire term/paren."""
    inner: "Expr"


@dataclass(frozen=True)
class BinOp:
    op: str            # 'add' | 'sub' | 'mul' | 'div' | 'pow'
    lhs: "Expr"
    rhs: "Expr"


@dataclass(frozen=True)
class Cmp:
    op: str            # 'lt' | 'le' | 'gt' | 'ge' | 'eq' | 'ne'
    lhs: "Expr"
    rhs: "Expr"


@dataclass(frozen=True)
class Call:
    """Intrinsic reference (``abs``, later ``min``/``max``)."""
    name: str
    args: tuple["Expr", ...]


@dataclass(frozen=True)
class Cond:
    """Conditional *expression* — the functional layer's inline
    ``if cond then a else b``. No frontend ever produces one: only
    :func:`functionalize` creates it, when merging a control-flow join
    (see the module docstring)."""
    cond: "Expr"
    then: "Expr"
    orelse: "Expr"


Expr = Union[RealLit, IntLit, Var, ArrayRef, Paren, Neg, BinOp, Cmp, Call, Cond]


# --------------------------------------------------------------------------- #
# Statements
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Assign:
    target: Union[Var, ArrayRef]
    value: Expr


@dataclass(frozen=True)
class If:
    """Structured IF: ``branches`` are (condition, body) in source order
    (if/elseif...), ``orelse`` the else body ([] if absent)."""
    branches: tuple[tuple[Expr, tuple["Stmt", ...]], ...]
    orelse: tuple["Stmt", ...]


@dataclass(frozen=True)
class DoConcurrent:
    """``do concurrent`` nest: controls are (index_name, lower, upper) in
    source order; the body is a statement sequence."""
    controls: tuple[tuple[str, Expr, Expr], ...]
    body: tuple["Stmt", ...]


Stmt = Union[Assign, If, DoConcurrent]


# --------------------------------------------------------------------------- #
# Kernel
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Param:
    name: str
    type: str          # 'real' | 'integer' | 'derived:<name>'
    intent: Optional[str]   # 'in' | 'inout' | 'out' | None (local)
    rank: int          # 0 = scalar


@dataclass(frozen=True)
class Kernel:
    name: str
    params: tuple[Param, ...]   # dummy arguments, in source order
    locals: tuple[Param, ...]   # local declarations (intent None)
    body: tuple[Stmt, ...]


# --------------------------------------------------------------------------- #
# Pass 1: pointization
# --------------------------------------------------------------------------- #

def pointize(kernel: Kernel) -> Kernel:
    """Strip a single top-level ``do concurrent`` wrapper; scalarize arrays.

    Every ``ArrayRef`` whose subscripts are exactly the concurrent indices (as
    plain ``Var``s, in the same order per array) becomes ``Var(name)``. The
    loop indices, the bound variables, and any parameter no longer referenced
    by the pointized body (grid structs, index ranges) are dropped.
    """
    if len(kernel.body) != 1 or not isinstance(kernel.body[0], DoConcurrent):
        raise UnsupportedConstruct(
            f"{kernel.name}: pointize expects the body to be exactly one do-concurrent nest")
    loop = kernel.body[0]
    indices = tuple(name for (name, _, _) in loop.controls)

    def scalarize_expr(e: Expr) -> Expr:
        if isinstance(e, (RealLit, IntLit, Var)):
            return e
        if isinstance(e, ArrayRef):
            subs = tuple(s.name if isinstance(s, Var) else None for s in e.subscripts)
            if set(subs) == set(indices) and None not in subs:
                return Var(e.name)
            raise UnsupportedConstruct(
                f"{kernel.name}: array reference {e.name}{subs} is not indexed "
                f"exactly by the concurrent indices {indices}")
        if isinstance(e, Paren):
            return Paren(scalarize_expr(e.inner))
        if isinstance(e, Neg):
            return Neg(scalarize_expr(e.inner))
        if isinstance(e, BinOp):
            return BinOp(e.op, scalarize_expr(e.lhs), scalarize_expr(e.rhs))
        if isinstance(e, Cmp):
            return Cmp(e.op, scalarize_expr(e.lhs), scalarize_expr(e.rhs))
        if isinstance(e, Call):
            return Call(e.name, tuple(scalarize_expr(a) for a in e.args))
        raise UnsupportedConstruct(f"{kernel.name}: cannot scalarize {type(e).__name__}")

    def scalarize_stmt(s: Stmt) -> Stmt:
        if isinstance(s, Assign):
            tgt = scalarize_expr(s.target)
            if not isinstance(tgt, Var):
                raise UnsupportedConstruct(f"{kernel.name}: unsupported assignment target")
            return Assign(tgt, scalarize_expr(s.value))
        if isinstance(s, If):
            return If(
                tuple((scalarize_expr(c), tuple(scalarize_stmt(b) for b in body))
                      for (c, body) in s.branches),
                tuple(scalarize_stmt(b) for b in s.orelse))
        raise UnsupportedConstruct(
            f"{kernel.name}: {type(s).__name__} inside the concurrent body is unsupported")

    body = tuple(scalarize_stmt(s) for s in loop.body)

    used: set[str] = set()

    def collect(e: Expr) -> None:
        if isinstance(e, Var):
            used.add(e.name)
        elif isinstance(e, (Paren, Neg)):
            collect(e.inner)
        elif isinstance(e, BinOp):
            collect(e.lhs); collect(e.rhs)
        elif isinstance(e, Cmp):
            collect(e.lhs); collect(e.rhs)
        elif isinstance(e, Call):
            for a in e.args:
                collect(a)

    def collect_stmt(s: Stmt) -> None:
        if isinstance(s, Assign):
            used.add(s.target.name); collect(s.value)
        elif isinstance(s, If):
            for (c, b) in s.branches:
                collect(c)
                for x in b:
                    collect_stmt(x)
            for x in s.orelse:
                collect_stmt(x)

    for s in body:
        collect_stmt(s)

    params = tuple(Param(p.name, p.type, p.intent, 0)
                   for p in kernel.params if p.name in used and p.name not in indices)
    locals_ = tuple(Param(p.name, p.type, None, 0)
                    for p in kernel.locals if p.name in used and p.name not in indices)
    return Kernel(kernel.name, params, locals_, body)


# --------------------------------------------------------------------------- #
# Pass 2: functionalization
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Let:
    """Functional form: ``let name := value; body``."""
    name: str
    value: Expr
    body: "FunExpr"


@dataclass(frozen=True)
class IfExpr:
    cond: Expr
    then: "FunExpr"
    orelse: "FunExpr"


@dataclass(frozen=True)
class Tuple_:
    elems: tuple[Expr, ...]


FunExpr = Union[Let, IfExpr, Tuple_]


def functionalize(kernel: Kernel) -> tuple[tuple[Param, ...], tuple[str, ...], FunExpr]:
    """Translate the (pointized) imperative body into one functional expression.

    Returns ``(input_params, output_names, expr)`` where the outputs are the
    ``inout``/``out`` parameters in declaration order; ``expr`` evaluates to
    their tuple. Locals become ``Let`` bindings; an output's current value is
    tracked symbolically, starting at its own input ``Var``.
    """
    outputs = tuple(p.name for p in kernel.params if p.intent in ("inout", "out"))
    if not outputs:
        raise UnsupportedConstruct(f"{kernel.name}: no inout/out parameters — nothing to return")
    local_names = {p.name for p in kernel.locals}

    def go(stmts: tuple[Stmt, ...], state: dict[str, Expr]) -> FunExpr:
        if not stmts:
            return Tuple_(tuple(state[o] for o in outputs))
        head, rest = stmts[0], stmts[1:]
        if isinstance(head, Assign):
            name = head.target.name
            value = subst(head.value, state)
            if name in local_names:
                return Let(name, value, go(rest, state))
            if name in state:
                return go(rest, {**state, name: value})
            raise UnsupportedConstruct(
                f"{kernel.name}: assignment to '{name}', neither local nor output")
        if isinstance(head, If):
            if rest:
                # Control-flow join: the remaining statements run against the
                # MERGED state, so a later read of a variable this IF may have
                # updated observes the conditional value (sequential semantics).
                return go(rest, merge_if(head, state))
            def branch(i: int) -> FunExpr:
                if i < len(head.branches):
                    cond, body = head.branches[i]
                    return IfExpr(subst(cond, state), go(body, dict(state)), branch(i + 1))
                return go(head.orelse, dict(state))
            return branch(0)
        raise UnsupportedConstruct(f"{kernel.name}: {type(head).__name__} is unsupported here")

    def merge_if(head: If, state: dict[str, Expr]) -> dict[str, Expr]:
        """Merge an ``If`` that statements follow into a per-variable ``Cond``.

        Supported ONLY when the ``If`` has a single branch (no elseif chain)
        and every branch body consists solely of assignments to state (output)
        variables — no locals (a ``Let`` may not escape), no nested ``If``s.
        Per variable a branch assigned: ``state'[v] = Cond(cond, state_then[v],
        state_else[v])``; unassigned variables pass through unchanged.
        """
        if len(head.branches) != 1:
            raise UnsupportedConstruct(
                f"{kernel.name}: statements after an IF with an elseif chain "
                f"(control-flow join) are unsupported")
        cond, then_body = head.branches[0]

        def branch_state(body: tuple[Stmt, ...]) -> tuple[dict[str, Expr], set[str]]:
            st, assigned = dict(state), set()
            for s in body:
                if not isinstance(s, Assign):
                    raise UnsupportedConstruct(
                        f"{kernel.name}: statements after an IF (control-flow join) "
                        f"require its branches to hold only assignments to output "
                        f"variables; found {type(s).__name__}")
                if s.target.name not in state:
                    raise UnsupportedConstruct(
                        f"{kernel.name}: assignment to non-output '{s.target.name}' "
                        f"inside a joined IF branch (a Let may not escape the branch)")
                st[s.target.name] = subst(s.value, st)
                assigned.add(s.target.name)
            return st, assigned

        st_then, asg_then = branch_state(then_body)
        st_else, asg_else = branch_state(head.orelse)
        cond_now = subst(cond, state)
        merged = dict(state)
        for v in asg_then | asg_else:
            merged[v] = Cond(cond_now, st_then[v], st_else[v])
        return merged

    def subst(e: Expr, state: dict[str, Expr]) -> Expr:
        """Replace reads of *output* variables with their current symbolic value.
        (Locals are bound by ``Let`` and read by name, so they pass through.)

        Unconditional on purpose: when the current value is the identity
        ``Var(name)`` the substitution is a no-op, and when it is any other
        expression — including a plain ``Var`` alias like ``b = a`` — the read
        must see it, or a later statement would silently read the *input*
        value. Sequential threading is the whole contract here."""
        if isinstance(e, Var) and e.name in state:
            return state[e.name]
        if isinstance(e, Paren):
            return Paren(subst(e.inner, state))
        if isinstance(e, Neg):
            return Neg(subst(e.inner, state))
        if isinstance(e, BinOp):
            return BinOp(e.op, subst(e.lhs, state), subst(e.rhs, state))
        if isinstance(e, Cmp):
            return Cmp(e.op, subst(e.lhs, state), subst(e.rhs, state))
        if isinstance(e, Call):
            return Call(e.name, tuple(subst(a, state) for a in e.args))
        return e

    state0: dict[str, Expr] = {o: Var(o) for o in outputs}
    return kernel.params, outputs, go(kernel.body, state0)
