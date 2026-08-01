"""The kernel-IR frontend seam: anything that can turn one addressed
source kernel into a :class:`~groundline.kir.Kernel`.

The kernel-verification mirror of the relational seam in ``base.py`` (DESIGN §2.2/§2.3):
one deep method, ``extract(spec) -> Kernel``, hiding everything
format-specific — the flang dump walk on the Fortran side, the clang
invocation and JSON AST walk on the C++ side. What differs between the two
languages is only the *address* of a kernel, so each side has its own typed
spec; everything downstream (``kir``, ``functionalize``, the Lean printer) is
shared and spec-free.

Implementations: :class:`~groundline.frontend.flang_kernel.FlangKernelFrontend`
(consumes pre-generated with-sema dumps) and
:class:`~groundline.frontend.clang_kernel.ClangKernelFrontend` (invokes clang
itself; the invocation config travels in the spec, not in function kwargs).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, TypeVar, runtime_checkable

from groundline.kir import Kernel

SpecT = TypeVar("SpecT", contravariant=True)


@dataclass(frozen=True)
class FortranKernelSpec:
    """Address of one Fortran kernel in a with-sema flang parse-tree dump.

    ``nest`` selects rule-B inline-loop addressing: loop nest #``nest``
    (1-based, source order) of ``subroutine``, generated under ``def_name``
    (an inline loop has no name of its own — the spec records the pairing).
    With ``nest`` unset, the whole subroutine is the kernel and ``def_name``
    must be unset too (the def is named after the subroutine).
    """
    dump: Path
    subroutine: str
    nest: Optional[int] = None
    def_name: Optional[str] = None

    def __post_init__(self) -> None:
        if (self.nest is None) != (self.def_name is None):
            raise ValueError(
                f"FortranKernelSpec({self.subroutine!r}): nest and def_name "
                f"must be given together (inline-loop addressing) or not at all")


@dataclass(frozen=True)
class CppKernelSpec:
    """Address of one C++ point-kernel function, plus the pinned clang
    invocation that produces its JSON AST (compiler and include dirs are part
    of the kernel's identity — a different toolchain is a different dump)."""
    header: Path
    function: str
    include_dirs: tuple[str, ...] = ()
    clang: str = "clang++"


@runtime_checkable
class KernelFrontend(Protocol[SpecT]):
    """Extract one :class:`~groundline.kir.Kernel` from its typed spec."""

    def extract(self, spec: SpecT) -> Kernel:
        ...
