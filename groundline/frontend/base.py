"""The frontend seam: anything that can turn Fortran sources into an :class:`IR`.

A frontend hides *everything* format-specific behind a single deep method
(design principle #2/#3). Today the only implementation is
:class:`~groundline.frontend.flang_dump.FlangDumpFrontend`, which scrapes flang's
textual parse-tree dump. A future :class:`~groundline.frontend.lfortran_asr` adapter
would implement the same protocol — the day it does is the day we learn whether the
seam was real.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Protocol, runtime_checkable

from groundline.ir import IR


@runtime_checkable
class Frontend(Protocol):
    """Extract a groundline :class:`IR` from a set of Fortran sources/dumps."""

    def extract(self, sources: Iterable[Path]) -> IR:
        ...
