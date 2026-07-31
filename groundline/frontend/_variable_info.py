from dataclasses import dataclass
from typing import Optional


@dataclass
class VariableInfo:
    """Information about a declared variable's type, rank, and kind.
    
    Attributes
    ----------
    type : str
        The type name: 'integer', 'real', 'logical', 'character', 'complex',
        'derived:typename', or 'unknown'.
    rank : int
        Array rank: 0 for scalar, 1+ for arrays.
    kind : str or None
        Kind specifier (e.g., 'r8_kind', 'i4_kind') or None if unknown.
    """
    type: str  # 'integer', 'real', 'logical', 'character', 'derived', 'unknown'
    rank: int = 0  # 0 for scalar, 1 for 1D array, etc.
    kind: Optional[str] = None  # Optional kind specifier
