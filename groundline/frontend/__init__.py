"""Frontends: everything flang-specific (or format-specific) lives below here.

Consumers import :class:`~groundline.ir.IR` and a frontend; they never import the
flang-text machinery (``flang_dump``, ``_nodes``, ``_registry``, …) directly.
"""

from groundline.frontend.base import Frontend
from groundline.frontend.flang_dump import FlangDumpFrontend

__all__ = ["Frontend", "FlangDumpFrontend"]
