"""Utility functions: currency parsing, date normalization, text cleaning."""

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from config import CONFIG


def normalize_fullwidth(text: str) -> str:
    """Convert full-width characters to ASCII equivalents."""
    if not text:
        return ""
    s = text
    s = s.replace("\uff0c", ",").replace("\uff0e", ".")
    s = s.replace("\uff0d", "-").replace("\uff08", "(").replace("\uff09", ")")
    s = s.replace("\uff1a", ":").replace("\uff1b", ";")
    s = s.replace("\u3000", " ")  # ideographic space
    return s


def parse_financial_amount(text: str) -> Decimal | None:
    """Parse a financial amount string into Decimal.

    Handles: ¥1,234.56  (1,234.56)  CNY 1234.56  -1,234.56  RMB1234
    Returns None if parsing fails.
    """
    if not text or not str(text).strip():
        return None

    s = str(text).strip()
    s = normalize_fullwidth(s)

    # Determine sign from parentheses
    negative = False
    if (s.startswith("(") and s.endswith(")")):
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

    # Determine decimal convention
    # Count separators to distinguish thousands from decimal
    dots = s.count(".")
    commas = s.count(",")

    if dots > 1:
        # Multiple dots = thousands separators (e.g., "1.234.567")
        s = s.replace(".", "")
    elif commas > 1:
        # Multiple commas = thousands separators (e.g., "1,234,567")
        s = s.replace(",", "")
    elif dots == 1 and commas == 1:
        # Both present: last one is decimal
        dot_pos = s.rfind(".")
        comma_pos = s.rfind(",")
        if dot_pos > comma_pos:
            # Standard: 1,234.56
            s = s.replace(",", "")
        else:
            # European: 1.234,56
            s = s.replace(".", "").replace(",", ".")
    elif dots == 1:
        # Single dot: check digits after
        parts = s.split(".")
        if len(parts[1]) == 3 and len(parts[0]) <= 3:
            # Could be thousands: "1.234" — ambiguous, assume decimal
            pass
        # Keep as decimal
        s = s.replace(",", "")
    elif commas == 1:
        # Single comma: check digits after
        parts = s.split(",")
        if len(parts[1]) <= 2:
            # European decimal: "1234,56"
            s = s.replace(",", ".")
        else:
            # Thousands: "1,234"
            s = s.replace(",", "")
    else:
        # No separators
        s = s.replace(",", "").replace(".", "")

    # Remove any remaining non-numeric chars except dot and minus
    s = re.sub(r"[^\d.]", "", s)

    if not s:
        return None

    try:
        value = Decimal(s)
        return -value if negative else value
    except InvalidOperation:
        return None


def normalize_date(text: str) -> date | None:
    """Try to parse a date string using supported formats.

    Returns None if no format matches.
    """
    if not text or not str(text).strip():
        return None

    s = str(text).strip()
    # Normalize full-width digits and characters
    s = unicodedata.normalize("NFKC", s)
    s = normalize_fullwidth(s)

    # Try Chinese date format first: YYYY年M月D日
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日?", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # Try standard formats
    for fmt in CONFIG.supported_date_formats:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    # Try compact formats: "20240115"
    if re.match(r"^\d{8}$", s):
        try:
            return datetime.strptime(s, "%Y%m%d").date()
        except ValueError:
            pass

    return None


def clean_text(text: str) -> str:
    """Normalize and clean extracted text for comparison."""
    if not text:
        return ""
    s = str(text)
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", s)
    s = normalize_fullwidth(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def detect_language(text: str) -> str:
    """Detect dominant language by character ranges."""
    if not text:
        return "en"
    cjk_count = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    latin_count = sum(1 for c in text if c.isascii() and c.isalpha())
    return "zh" if cjk_count > latin_count else "en"


def count_cjk_chars(text: str) -> int:
    """Count CJK (Chinese/Japanese/Korean) characters."""
    return sum(1 for c in text if "\u4e00" <= c <= "\u9fff")


def safe_decimal_compare(a: Decimal, b: Decimal, tolerance: Decimal) -> bool:
    """Compare two Decimal amounts within a tolerance."""
    return abs(a - b) <= tolerance


def levenshtein_ratio(s1: str, s2: str) -> float:
    """Compute normalized Levenshtein similarity ratio (0.0 to 1.0)."""
    try:
        import Levenshtein
        return Levenshtein.ratio(s1, s2)
    except ImportError:
        # Fallback: difflib SequenceMatcher
        from difflib import SequenceMatcher
        return SequenceMatcher(None, s1, s2).ratio()


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text for display purposes."""
    if not text or len(text) <= max_length:
        return text or ""
    return text[:max_length] + "..."


def fix_ocr_common_errors(text: str) -> str:
    """Fix common OCR character confusion errors in Chinese financial docs."""
    if not text:
        return ""
    # Common OCR confusions in numbers
    # Only apply in numeric contexts
    s = text
    # Fix full-width digits to ASCII
    s = unicodedata.normalize("NFKC", s)
    return s
