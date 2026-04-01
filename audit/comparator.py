"""Data comparison engine for matching extracted PDF data against expected values."""

from datetime import date
from decimal import Decimal, InvalidOperation

from audit.models import ComparisonResult
from utils.helpers import (
    parse_financial_amount,
    normalize_date,
    clean_text,
    levenshtein_ratio,
    safe_decimal_compare,
)


class DataComparator:
    """Compare extracted values against expected values with tolerance."""

    def compare_amounts(self, extracted: str, expected, tolerance: Decimal = Decimal("0.01"),
                        tolerance_pct: Decimal = Decimal("0.01")) -> ComparisonResult:
        """Compare financial amounts with absolute and percentage tolerance."""
        extracted_clean = clean_text(str(extracted))
        extracted_amount = parse_financial_amount(extracted_clean)

        if extracted_amount is None:
            return ComparisonResult(
                matches=False, confidence=0.0,
                extracted_value=str(extracted), expected_value=str(expected),
                difference="N/A - cannot parse extracted amount",
                notes="Failed to parse extracted amount as a number",
            )

        # Parse expected value
        if isinstance(expected, (int, float)):
            expected_amount = Decimal(str(expected))
        elif isinstance(expected, Decimal):
            expected_amount = expected
        else:
            expected_amount = parse_financial_amount(str(expected))
            if expected_amount is None:
                return ComparisonResult(
                    matches=False, confidence=0.0,
                    extracted_value=str(extracted_amount), expected_value=str(expected),
                    difference="N/A - cannot parse expected amount",
                    notes="Failed to parse expected amount as a number",
                )

        diff = extracted_amount - expected_amount
        abs_diff = abs(diff)

        # Check absolute tolerance
        abs_match = abs_diff <= tolerance

        # Check percentage tolerance
        pct_diff = (abs_diff / abs(expected_amount) * 100) if expected_amount != 0 else Decimal("0")
        pct_match = pct_diff <= (tolerance_pct * 100) if expected_amount != 0 else abs_match

        matches = abs_match or pct_match
        confidence = 1.0 if matches else max(0.0, 1.0 - float(pct_diff) / 100)

        return ComparisonResult(
            matches=matches,
            confidence=confidence,
            extracted_value=str(extracted_amount),
            expected_value=str(expected_amount),
            difference=str(diff),
            notes=f"Abs diff: {abs_diff}, Pct diff: {pct_diff:.2f}%",
        )

    def compare_dates(self, extracted: str, expected, tolerance_days: int = 3) -> ComparisonResult:
        """Compare dates within a day tolerance."""
        extracted_date = normalize_date(str(extracted))

        if extracted_date is None:
            return ComparisonResult(
                matches=False, confidence=0.0,
                extracted_value=str(extracted), expected_value=str(expected),
                difference="N/A - cannot parse extracted date",
                notes="Failed to parse extracted date",
            )

        # Parse expected
        if isinstance(expected, date):
            expected_date = expected
        else:
            expected_date = normalize_date(str(expected))
            if expected_date is None:
                return ComparisonResult(
                    matches=False, confidence=0.0,
                    extracted_value=str(extracted_date), expected_value=str(expected),
                    difference="N/A - cannot parse expected date",
                    notes="Failed to parse expected date",
                )

        day_diff = abs((extracted_date - expected_date).days)
        matches = day_diff <= tolerance_days
        confidence = 1.0 if day_diff == 0 else max(0.0, 1.0 - day_diff / (tolerance_days * 2))

        return ComparisonResult(
            matches=matches,
            confidence=confidence,
            extracted_value=str(extracted_date),
            expected_value=str(expected_date),
            difference=f"{day_diff} days",
            notes=f"Date difference: {day_diff} days (tolerance: {tolerance_days})",
        )

    def compare_text(self, extracted: str, expected: str, threshold: float = 0.8) -> ComparisonResult:
        """Compare text using fuzzy matching."""
        e1 = clean_text(str(extracted))
        e2 = clean_text(str(expected))

        if not e1 and not e2:
            return ComparisonResult(
                matches=True, confidence=1.0,
                extracted_value=e1, expected_value=e2,
                difference="", notes="Both empty",
            )

        if e1 == e2:
            return ComparisonResult(
                matches=True, confidence=1.0,
                extracted_value=e1, expected_value=e2,
                difference="", notes="Exact match",
            )

        # Fuzzy match
        ratio = levenshtein_ratio(e1, e2)
        matches = ratio >= threshold

        return ComparisonResult(
            matches=matches,
            confidence=ratio,
            extracted_value=e1,
            expected_value=e2,
            difference=f"Similarity: {ratio:.1%}",
            notes=f"Fuzzy match ratio: {ratio:.3f} (threshold: {threshold})",
        )

    def auto_compare(self, extracted: str, expected, field_type: str = "auto",
                     **kwargs) -> ComparisonResult:
        """Auto-detect field type and compare accordingly."""
        if field_type == "amount":
            return self.compare_amounts(extracted, expected, **kwargs)
        elif field_type == "date":
            return self.compare_dates(extracted, expected, **kwargs)
        elif field_type == "text":
            return self.compare_text(extracted, str(expected), **kwargs)

        # Auto-detect
        # Try amount first
        amount = parse_financial_amount(str(extracted))
        if amount is not None:
            expected_amount = parse_financial_amount(str(expected))
            if expected_amount is not None:
                return self.compare_amounts(extracted, expected, **kwargs)

        # Try date
        d = normalize_date(str(extracted))
        if d is not None:
            return self.compare_dates(extracted, expected, **kwargs)

        # Fallback to text
        return self.compare_text(extracted, str(expected), **kwargs)
