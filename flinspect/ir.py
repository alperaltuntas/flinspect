"""flinspect IR — the seam between frontends and consumers.

The IR is a small collection of **named, typed relations over interned atoms**
(see ``docs/DESIGN.md`` §2.1). Entity *kinds* are sets of atoms; structural facts
are relations (tuple-sets) between them. Nothing flang-specific appears here: a
frontend (flang dump today, LFortran ASR tomorrow) populates an ``IR`` and every
consumer reads only from it.

Identity is a scope-qualified, interned ``EntityId`` string — never a bare name
(design principle #7). Relations are plain tuple-sets so that confidence can later
be modeled by *stratifying* a relation into ``calls_resolved`` / ``calls_assumed`` /
``calls_unresolved`` (principle #2, D3) without reshaping anything. Phase 1a keeps a
single ``calls`` relation; ``unresolved_calls`` is already kept as a first-class
fact rather than silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# An interned, scope-qualified identity, e.g. "mom_grid_mod::set_grid" or
# "mom_grid_mod::outer_routine::inner_routine". Never a bare name.
EntityId = str

# Entity kinds (the unary relations / "sets" of the universe).
MODULE = "module"
PROGRAM = "program"
SUBPROGRAM = "subprogram"
SUBROUTINE = "subroutine"
FUNCTION = "function"
INTERFACE = "interface"
DERIVED_TYPE = "derived_type"

#: Kinds that can appear as a call target (subroutine, function, or a generic
#: interface that fans out to specific procedures).
CALLABLE_KINDS = frozenset({SUBROUTINE, FUNCTION, INTERFACE})


@dataclass(frozen=True)
class Signature:
    """A subprogram's argument list, projected into parallel positional tuples.

    A signature is inherently a sequence of records; at the IR boundary it is kept
    as parallel tuples (cf. DESIGN §2.1 — the awkward case for a flat-relational
    model). Empty tuples mean "no arguments"; ``num_required`` is ``None`` when the
    frontend could not determine it.
    """

    arg_names: tuple[str, ...] = ()
    arg_types: tuple[str, ...] = ()
    arg_ranks: tuple[int, ...] = ()
    arg_kinds: tuple[Optional[str], ...] = ()
    num_required: Optional[int] = None

    @property
    def num_args(self) -> int:
        return len(self.arg_types)


@dataclass(frozen=True)
class Entity:
    """An interned atom: a Fortran program unit, subprogram, interface, or type."""

    id: EntityId
    kind: str
    name: str
    scope: Optional[EntityId] = None          # containing program unit / parent routine
    signature: Optional[Signature] = None      # subroutines / functions
    parent_type: Optional[str] = None          # derived-type EXTENDS target (by name)
    bindings: tuple[tuple[str, str], ...] = ()  # derived type: (binding_name, impl_name)
    defined: bool = True                        # False for referenced-but-not-parsed externals

    def __str__(self) -> str:
        return self.id


@dataclass(frozen=True)
class Use:
    """A ``USE`` relation edge: ``scope`` imports from module named ``module``.

    ``module`` is a name, not necessarily a defined ``EntityId`` — external modules
    (netcdf, mpi, …) are referenced but never defined in the corpus.
    """

    scope: EntityId
    module: str
    only: tuple[str, ...] = ()                  # only-list names ("" / absent = whole module)
    renames: tuple[tuple[str, str], ...] = ()   # (alias, original)


@dataclass(frozen=True)
class FileError:
    """A source file the frontend could not fully parse (fault isolation, W3)."""

    path: Path
    message: str


@dataclass
class IR:
    """The fact base: entities (atoms) plus relations (tuple-sets) over them."""

    entities: dict[EntityId, Entity] = field(default_factory=dict)

    # Relations. Each is a set of tuples of EntityIds (or names where the target
    # may be external/unresolved).
    calls: set[tuple[EntityId, EntityId]] = field(default_factory=set)
    contains: set[tuple[EntityId, EntityId]] = field(default_factory=set)
    interface_members: set[tuple[EntityId, EntityId]] = field(default_factory=set)
    uses: set[Use] = field(default_factory=set)

    # First-class partial knowledge: a call whose target could not be resolved.
    # (caller_id, callee_name) — kept, never silently dropped (D3, principle #6).
    unresolved_calls: set[tuple[EntityId, str]] = field(default_factory=set)

    # Fault isolation: files that failed to parse (W3).
    file_errors: list[FileError] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    # Entity-set views (unary relations)
    # ------------------------------------------------------------------ #
    def of_kind(self, kind: str) -> list[Entity]:
        return [e for e in self.entities.values() if e.kind == kind]

    @property
    def modules(self) -> list[Entity]:
        return self.of_kind(MODULE)

    @property
    def programs(self) -> list[Entity]:
        return self.of_kind(PROGRAM)

    @property
    def subprograms(self) -> list[Entity]:
        return self.of_kind(SUBPROGRAM)

    @property
    def subroutines(self) -> list[Entity]:
        return self.of_kind(SUBROUTINE)

    @property
    def functions(self) -> list[Entity]:
        return self.of_kind(FUNCTION)

    @property
    def interfaces(self) -> list[Entity]:
        return self.of_kind(INTERFACE)

    @property
    def derived_types(self) -> list[Entity]:
        return self.of_kind(DERIVED_TYPE)

    def get(self, eid: EntityId) -> Optional[Entity]:
        return self.entities.get(eid)

    # ------------------------------------------------------------------ #
    # Derived / inverse relations (computed, not stored)
    # ------------------------------------------------------------------ #
    def callees(self, eid: EntityId) -> set[Entity]:
        """Entities directly called by ``eid``."""
        return {self.entities[c] for (caller, c) in self.calls
                if caller == eid and c in self.entities}

    def callers(self, eid: EntityId) -> set[Entity]:
        """Entities that directly call ``eid``."""
        return {self.entities[caller] for (caller, c) in self.calls
                if c == eid and caller in self.entities}

    def members(self, interface_id: EntityId) -> set[Entity]:
        """Specific procedures belonging to a generic interface."""
        return {self.entities[p] for (iface, p) in self.interface_members
                if iface == interface_id and p in self.entities}

    def used_modules(self, scope_id: EntityId) -> set[str]:
        """Module names USE'd by a given scope."""
        return {u.module for u in self.uses if u.scope == scope_id}
