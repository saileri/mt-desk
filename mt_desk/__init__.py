"""MT Desk — MT4/MT5 Trading Analytics Desktop.

Ported CSV import pipeline from pengfuchao/trading-record-analysis.
"""

from .parser import parse_statement
from .analysis import analyze
from .csv_import import import_csv

__version__ = "6.3.1"
__all__ = ["parse_statement", "analyze", "import_csv"]
