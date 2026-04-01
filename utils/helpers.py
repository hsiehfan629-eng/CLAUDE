"""Utility functions: currency parsing, date normalization, text cleaning."""

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from config import CONFIG


def parse_financial_amount(text: str) -> Decimal | None:
    """Parse a financial amount string into Decimal.

    Handles: ¥1,234.56  (1,234.56)  CNY 1234.56  -1,234.56  RMB1234
    Returns None if parsing fails.
    """
    if not text or not text.strip():
        return None

    s = text.strip()
    # Determine sign from parentheses
    negative = False
    if (s.startswith("(") and s.endswith(")")) or (s.startswith("\uff08") and s.endswith("\uff09")):
        negative = True
        s = s[1:-1].strip()

    # Remove currency symbols and prefixes
    s = re.sub(r"[\$\u00a5\uffe5]", "", s)
    s = re.sub(r"(?:CNY|RMB|USD)\s*", "", s, flags=re.IGNORECASE)
    s = s.strip()

    if not s:
        return None

    # Handle explicit negative sign
    if s.startswith("-"):
        negative = True
        s = s[1:].strip()

    # Normalize full-width characters to ASCII
    s = s.replace("\uff0c", ",").replace("\uff0e", ".")

    # Determine decimal convention
    # If last separator is a dot with 1-2 digits after → dot is decimal
    # If last separator is a comma with 1-2 digits after → comma is decimal (European)
    if re.match(r"^[\d,]+\.\d{1,4}$", s):
        # Standard: 1,234.56
        s = s.replace(",", "")
    elif re.match(r"^[\d.]+,\d{1,4}$", s):
        # European: 1.234,56
        s = s.replace(".", "").replace(",", ".")
    else:
        # No decimal part, just remove separators
        s = s.replace(",", "").replace(".", "")

    try:
        value = Decimal(s)
        return -value if negative else value
    except InvalidOperation:
        return None


def normalize_date(text: str) -> date | None:
    """Try to parse a date string using supported formats.

    Returns None if no format matches.
    """
    if not text or not text.strip():
        return None

    s = text.strip()
    # Normalize full-width digits
    s = unicodedata.normalize("NFKC", s)

    for fmt in CONFIG.supported_date_formats:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def clean_text(text: str) -> str:
    """Normalize and clean extracted text for comparison."""
    if not text:
        return ""
    # Unicode NFC normalization (important for Chinese)
    s = unicodedata.normalize("NFC", text)
    # Remove zero-width characters
    s = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", s)
    # Normalize whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def detect_language(text: str) -> str:
    """Detect dominant language by character ranges.

    Returns 'zh' if Chinese characters dominate, else 'en'.
    """
    if not text:
        return "en"
    cjk_count = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    latin_count = sum(1 for c in text if c.isascii() and c.isalpha())
    return "zh" if cjk_count > latin_count else "en"


def safe_decimal_compare(a: Decimal, b: Decimal, tolerance: Decimal) -> bool:
    """Compare two Decimal amounts within a tolerance."""
    return abs(a - b) <= tolerance


def levenshtein_ratio(s1: str, s2: str) -> float:
    """Compute normalized Levenshtein similarity ratio (0.0 to 1.0)."""
    try:
        import Levenshtein
        return Levenshtein.ratio(s1, s2)
    except ImportError:
        # Fallback: simple ratio
        if not s1 and not s2:
            return 1.0
        if not s1 or not s2:
            return 0.0
        max_len = max(len(s1), len(s2))
        # Simple character overlap
        common = sum(1 for a, b in zip(s1, s2) if a == b)
        return common / max_len


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text for display purposes."""
    if not text or len(text) <= max_length:
        return text or ""
    return text[:max_length] + "..."
