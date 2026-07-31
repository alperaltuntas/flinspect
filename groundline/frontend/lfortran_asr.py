"""Stub frontend built on LFortran's ASR (DESIGN "Option B", VISION D5).

This file is deliberately unimplemented. Its existence is a *forcing function*:
it keeps the :class:`~groundline.ir.IR` honest by asserting that a second, very
different frontend is supposed to populate the same contract. The day it is filled
in is the day we find out whether the seam leaked flang (see DESIGN §2.2). Until
then a frontend upgrade is explicitly deferred (VISION D5).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from groundline.ir import IR


class LFortranASRFrontend:
    """Placeholder for an LFortran-ASR-backed frontend (not yet implemented)."""

    def extract(self, sources: Iterable[Path]) -> IR:
        raise NotImplementedError(
            "The LFortran ASR frontend is a deferred option (VISION D5). "
            "groundline currently extracts facts only via FlangDumpFrontend."
        )
