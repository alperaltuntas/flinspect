"""Frontends: everything flang-specific (or format-specific) lives below here.

Consumers import :class:`~flinspect.ir.IR` and a frontend; they never import the
flang-text machinery (``flang_dump``, ``_nodes``, ``_registry``, …) directly.
"""

from flinspect.frontend.base import Frontend
from flinspect.frontend.flang_dump import FlangDumpFrontend

__all__ = ["Frontend", "FlangDumpFrontend"]
