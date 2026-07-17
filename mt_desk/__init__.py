"""MT Desk — MT4/MT5 Trading Analytics Desktop."""

from .parser import parse_statement
from .analysis import analyze

__version__ = "1.0.0"
__all__ = ["parse_statement", "analyze"]
