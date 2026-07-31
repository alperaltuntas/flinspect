"""Kernel-IR frontend: extract one subroutine from a with-sema flang parse-tree
dump into the Track B kernel IR (``flinspect/kir.py``).

Below the seam (DESIGN §2.3): everything flang-dump-specific about *kernel
bodies* lives here, exactly as ``flang_dump.py`` owns the dump's *relational*
face. Trusted-base rule (VISION D6): deterministic; any construct outside the
supported subset raises :class:`~flinspect.kir.UnsupportedConstruct` — the
extractor refuses rather than guesses.

The dump is parsed into a literal node tree first (one node per ``A -> B -> C``
chain element, children attached by ``|``-depth), then walked structurally.
Expression structure is taken from the *tree*, never re-parsed from the unparse
annotations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from flinspect.kir import (
    ArrayRef, Assign, BinOp, Call, Cmp, DoConcurrent, Expr, If, IntLit, Kernel,
    Neg, Param, Paren, RealLit, Stmt, UnsupportedConstruct, Var,
)
from flinspect.frontend._flang_text import level


# --------------------------------------------------------------------------- #
# Generic dump-tree parsing
# --------------------------------------------------------------------------- #

@dataclass
class Node:
    name: str
    payload: Optional[str] = None      # the 'value' in  Name = 'value'
    children: list["Node"] = field(default_factory=list)

    def child(self, name: str) -> "Node":
        for c in self.children:
            if c.name == name:
                return c
        raise UnsupportedConstruct(f"expected child '{name}' under '{self.name}', "
                                   f"have {[c.name for c in self.children]}")

    def children_named(self, name: str) -> list["Node"]:
        return [c for c in self.children if c.name == name]

    def only_child(self) -> "Node":
        if len(self.children) != 1:
            raise UnsupportedConstruct(
                f"expected exactly one child under '{self.name}', "
                f"have {[c.name for c in self.children]}")
        return self.children[0]


def _split_chain(content: str) -> list[Node]:
    """Turn one dump line's content into a chain of Nodes (parent → … → leaf).

    ``Foo -> Bar -> Name = 'x'`` becomes Foo ▸ Bar ▸ Name(payload='x'). The
    payload split happens at the first `` = '`` so unparse text containing
    ``->`` can't confuse the chain split.
    """
    payload = None
    head, sep, tail = content.partition(" = '")
    if sep:
        payload = tail[:-1] if tail.endswith("'") else tail
        content = head
    elif content.endswith(" = "):        # e.g.  Kind =
        content = content[:-3]
    if content.endswith(" ->"):          # e.g.  IntegerTypeSpec ->  (empty tail)
        content = content[:-3]
    parts = [p for p in content.split(" -> ") if p]
    if payload is None and parts and " = " in parts[-1]:
        # unquoted payload on the leaf, e.g.  Intent = In  /  Kind = ModuleProcedure
        name, _, payload = parts[-1].partition(" = ")
        parts[-1] = name
    chain = [Node(p) for p in parts]
    if payload is not None:
        chain[-1].payload = payload
    for a, b in zip(chain, chain[1:]):
        a.children.append(b)
    return chain


def parse_dump_lines(lines: Iterable[str]) -> Node:
    """Build the node tree of an entire dump (or any depth-consistent slice)."""
    root = Node("<root>")
    # stack[d] = the node new depth-d lines' chains attach under
    stack: list[Node] = [root]
    for raw in lines:
        line = raw.rstrip("\n")
        if not line or line.startswith("="):
            continue
        depth = level(line)
        content = line[2 * depth:] if depth else line
        if not content.strip():
            continue
        chain = _split_chain(content.strip())
        parent = stack[depth] if depth < len(stack) else stack[-1]
        parent.children.append(chain[0])
        del stack[depth + 1:]
        stack.append(chain[-1])
    return root


def find_subroutine(root: Node, name: str) -> Node:
    """Locate the ``SubroutineSubprogram`` whose SubroutineStmt names ``name``."""
    hits: list[Node] = []

    def walk(n: Node) -> None:
        if n.name == "SubroutineSubprogram":
            stmt = n.child("SubroutineStmt")
            names = stmt.children_named("Name")
            if names and names[0].payload == name:
                hits.append(n)
                return
        for c in n.children:
            walk(c)

    walk(root)
    if len(hits) != 1:
        raise UnsupportedConstruct(f"subroutine '{name}': found {len(hits)} definitions")
    return hits[0]


# --------------------------------------------------------------------------- #
# Expression extraction
# --------------------------------------------------------------------------- #

_BINOPS = {"Add": "add", "Subtract": "sub", "Multiply": "mul",
           "Divide": "div", "Power": "pow"}
_CMPS = {"LT": "lt", "LE": "le", "GT": "gt", "GE": "ge", "EQ": "eq", "NE": "ne"}
_INTRINSICS = {"abs", "min", "max", "sqrt"}


def extract_expr(node: Node) -> Expr:
    """``node`` is an ``Expr`` node (with-sema: payload = unparse text)."""
    inner = node.only_child()
    return _extract_expr_inner(inner)


def _extract_expr_inner(n: Node) -> Expr:
    if n.name in ("Scalar", "Integer", "Logical"):     # transparent wrappers
        return _extract_expr_inner(n.only_child())
    if n.name == "Expr":
        return extract_expr(n)
    if n.name == "LiteralConstant":
        lit = n.only_child()
        if lit.name == "RealLiteralConstant":
            return RealLit(lit.child("Real").payload)
        if lit.name == "IntLiteralConstant":
            return IntLit(lit.payload)
        raise UnsupportedConstruct(f"literal kind '{lit.name}'")
    if n.name == "Designator":
        return _extract_dataref(n.child("DataRef"))
    if n.name == "Parentheses":
        return Paren(extract_expr(n.child("Expr")))
    if n.name == "Negate":
        return Neg(extract_expr(n.child("Expr")))
    if n.name in _BINOPS:
        lhs, rhs = n.children_named("Expr")
        return BinOp(_BINOPS[n.name], extract_expr(lhs), extract_expr(rhs))
    if n.name in _CMPS:
        lhs, rhs = n.children_named("Expr")
        return Cmp(_CMPS[n.name], extract_expr(lhs), extract_expr(rhs))
    if n.name == "FunctionReference":
        call = n.child("Call")
        fname = call.child("ProcedureDesignator").child("Name").payload
        if fname not in _INTRINSICS:
            raise UnsupportedConstruct(f"call to '{fname}' (not a supported intrinsic)")
        args = tuple(extract_expr(spec.child("ActualArg").child("Expr"))
                     for spec in call.children_named("ActualArgSpec"))
        return Call(fname, args)
    raise UnsupportedConstruct(f"expression node '{n.name}'")


def _extract_dataref(n: Node) -> Expr:
    inner = n.only_child()
    if inner.name == "Name":
        return Var(inner.payload)
    if inner.name == "ArrayElement":
        base = inner.child("DataRef").child("Name").payload
        subs = tuple(extract_expr(s.child("Integer").child("Expr"))
                     if s.children and s.children[0].name == "Integer"
                     else extract_expr(_descend_subscript(s))
                     for s in inner.children_named("SectionSubscript"))
        return ArrayRef(base, subs)
    raise UnsupportedConstruct(f"data reference '{inner.name}'")


def _descend_subscript(s: Node) -> Node:
    n = s
    while n.name != "Expr":
        n = n.only_child()
    return n


# --------------------------------------------------------------------------- #
# Statement extraction
# --------------------------------------------------------------------------- #

def extract_block(block: Node) -> tuple[Stmt, ...]:
    stmts: list[Stmt] = []
    for epc in block.children_named("ExecutionPartConstruct"):
        stmts.append(_extract_construct(epc.child("ExecutableConstruct")))
    return tuple(stmts)


def _extract_construct(ec: Node) -> Stmt:
    inner = ec.only_child()
    if inner.name == "ActionStmt":
        return _extract_action(inner)
    if inner.name == "IfConstruct":
        return _extract_if(inner)
    if inner.name == "DoConstruct":
        return _extract_do(inner)
    raise UnsupportedConstruct(f"executable construct '{inner.name}'")


def _extract_action(action: Node) -> Stmt:
    stmt = action.only_child()
    if stmt.name == "AssignmentStmt":
        var = stmt.child("Variable")
        target = _extract_dataref(var.child("Designator").child("DataRef"))
        value = extract_expr(stmt.child("Expr"))
        return Assign(target, value)
    if stmt.name == "IfStmt":
        # Logical IF statement (R1139): `if (cond) action` — the dump nests the
        # guarded action as a child ActionStmt of the IfStmt, alongside the
        # condition. Extracted as a single-branch If with no orelse.
        cond = extract_expr(stmt.child("Scalar").child("Logical").child("Expr"))
        return If(((cond, (_extract_action(stmt.child("ActionStmt")),)),), ())
    raise UnsupportedConstruct(f"action statement '{stmt.name}'")


def _extract_if(n: Node) -> If:
    branches: list[tuple[Expr, tuple[Stmt, ...]]] = []
    orelse: tuple[Stmt, ...] = ()
    kids = n.children
    i = 0
    while i < len(kids):
        kid = kids[i]
        if kid.name == "IfThenStmt":
            cond = extract_expr(kid.child("Scalar").child("Logical").child("Expr"))
            body = extract_block(kids[i + 1])       # the following Block
            branches.append((cond, body))
            i += 2
        elif kid.name == "ElseIfBlock":             # wraps ElseIfStmt + Block
            stmt = kid.child("ElseIfStmt")
            cond = extract_expr(stmt.child("Scalar").child("Logical").child("Expr"))
            branches.append((cond, extract_block(kid.child("Block"))))
            i += 1
        elif kid.name == "ElseBlock":               # wraps ElseStmt + Block
            orelse = extract_block(kid.child("Block"))
            i += 1
        elif kid.name in ("EndIfStmt",):
            i += 1
        else:
            raise UnsupportedConstruct(f"IfConstruct child '{kid.name}'")
    return If(tuple(branches), orelse)


def _extract_do(n: Node) -> DoConcurrent:
    do_stmt = n.child("NonLabelDoStmt")
    loop = do_stmt.child("LoopControl").only_child()
    if loop.name != "Concurrent":
        raise UnsupportedConstruct("only do-concurrent loops are supported")
    header = loop.child("ConcurrentHeader")
    controls = []
    for cc in header.children_named("ConcurrentControl"):
        idx = cc.child("Name").payload
        bounds = [extract_expr(_descend_subscript(sc))
                  for sc in cc.children_named("Scalar")]
        if len(bounds) != 2:
            raise UnsupportedConstruct("do-concurrent with a stride is unsupported")
        controls.append((idx, bounds[0], bounds[1]))
    body = extract_block(n.child("Block"))
    return DoConcurrent(tuple(controls), body)


# --------------------------------------------------------------------------- #
# Declarations + kernel assembly
# --------------------------------------------------------------------------- #

def _extract_decls(spec: Node) -> list[Param]:
    decls: list[Param] = []
    for dc in spec.children_named("DeclarationConstruct"):
        try:
            tds = dc.child("SpecificationConstruct").child("TypeDeclarationStmt")
        except UnsupportedConstruct:
            continue
        dts = tds.child("DeclarationTypeSpec").only_child()
        if dts.name == "IntrinsicTypeSpec":
            base = dts.only_child().name
            type_ = {"Real": "real", "IntegerTypeSpec": "integer"}.get(base)
            if type_ is None:
                raise UnsupportedConstruct(f"intrinsic type '{base}'")
        elif dts.name == "Type":
            type_ = "derived:" + dts.child("DerivedTypeSpec").child("Name").payload
        else:
            raise UnsupportedConstruct(f"type spec '{dts.name}'")
        intent = None
        rank = 0
        for attr in tds.children_named("AttrSpec"):
            kid = attr.only_child()
            if kid.name == "IntentSpec":
                intent = kid.child("Intent").payload.lower()
            elif kid.name == "ArraySpec":
                rank = len(kid.children_named("ExplicitShapeSpec"))
            else:
                raise UnsupportedConstruct(f"attribute '{kid.name}'")
        for ent in tds.children_named("EntityDecl"):
            decls.append(Param(ent.child("Name").payload, type_, intent, rank))
    return decls


def extract_kernel(dump_path: Path, subroutine: str) -> Kernel:
    """Extract ``subroutine`` from the with-sema dump at ``dump_path``."""
    with open(dump_path) as f:
        root = parse_dump_lines(f)
    sub = find_subroutine(root, subroutine)
    stmt = sub.child("SubroutineStmt")
    arg_order = [d.child("Name").payload for d in stmt.children_named("DummyArg")]
    decls = _extract_decls(sub.child("SpecificationPart"))
    by_name = {d.name: d for d in decls}
    missing = [a for a in arg_order if a not in by_name]
    if missing:
        raise UnsupportedConstruct(f"{subroutine}: undeclared dummy args {missing}")
    params = tuple(by_name[a] for a in arg_order)
    locals_ = tuple(d for d in decls if d.name not in set(arg_order))
    body = extract_block(sub.child("ExecutionPart").child("Block"))
    return Kernel(subroutine, params, locals_, body)
