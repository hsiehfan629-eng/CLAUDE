"""Unit tests for PDF processor and audit modules."""

import unittest
from decimal import Decimal
from datetime import date

from utils.helpers import parse_financial_amount, normalize_date, clean_text, detect_language
from audit.comparator import DataComparator


class TestParseFinancialAmount(unittest.TestCase):
    def test_simple_number(self):
        self.assertEqual(parse_financial_amount("1234.56"), Decimal("1234.56"))

    def test_with_comma_separator(self):
        self.assertEqual(parse_financial_amount("1,234.56"), Decimal("1234.56"))

    def test_negative_parentheses(self):
        self.assertEqual(parse_financial_amount("(1,234.56)"), Decimal("-1234.56"))

    def test_yen_symbol(self):
        self.assertEqual(parse_financial_amount("\u00a51,234.56"), Decimal("1234.56"))

    def test_cny_prefix(self):
        self.assertEqual(parse_financial_amount("CNY 1,234.56"), Decimal("1234.56"))

    def test_rmb_prefix(self):
        self.assertEqual(parse_financial_amount("RMB1234"), Decimal("1234"))

    def test_negative_sign(self):
        self.assertEqual(parse_financial_amount("-1,234.56"), Decimal("-1234.56"))

    def test_empty(self):
        self.assertIsNone(parse_financial_amount(""))
        self.assertIsNone(parse_financial_amount(None))

    def test_integer(self):
        self.assertEqual(parse_financial_amount("1000"), Decimal("1000"))


class TestNormalizeDate(unittest.TestCase):
    def test_iso_format(self):
        self.assertEqual(normalize_date("2024-01-15"), date(2024, 1, 15))

    def test_slash_format(self):
        self.assertEqual(normalize_date("2024/01/15"), date(2024, 1, 15))

    def test_chinese_format(self):
        self.assertEqual(normalize_date("2024年01月15日"), date(2024, 1, 15))

    def test_invalid(self):
        self.assertIsNone(normalize_date("not a date"))

    def test_empty(self):
        self.assertIsNone(normalize_date(""))


class TestCleanText(unittest.TestCase):
    def test_whitespace(self):
        self.assertEqual(clean_text("  hello   world  "), "hello world")

    def test_zero_width(self):
        self.assertEqual(clean_text("hello\u200bworld"), "helloworld")

    def test_empty(self):
        self.assertEqual(clean_text(""), "")
        self.assertEqual(clean_text(None), "")


class TestDetectLanguage(unittest.TestCase):
    def test_chinese(self):
        self.assertEqual(detect_language("这是一个测试"), "zh")

    def test_english(self):
        self.assertEqual(detect_language("this is a test"), "en")

    def test_mixed(self):
        # More Chinese chars than English
        self.assertEqual(detect_language("这是一个中文测试test"), "zh")


class TestComparator(unittest.TestCase):
    def setUp(self):
        self.comp = DataComparator()

    def test_amount_exact_match(self):
        result = self.comp.compare_amounts("1,234.56", 1234.56)
        self.assertTrue(result.matches)

    def test_amount_within_tolerance(self):
        result = self.comp.compare_amounts("1,234.56", 1234.57, tolerance=Decimal("0.02"))
        self.assertTrue(result.matches)

    def test_amount_mismatch(self):
        result = self.comp.compare_amounts("1,234.56", 1300.00, tolerance=Decimal("0.01"),
                                           tolerance_pct=Decimal("0.001"))
        self.assertFalse(result.matches)

    def test_date_exact_match(self):
        result = self.comp.compare_dates("2024-01-15", date(2024, 1, 15))
        self.assertTrue(result.matches)

    def test_date_within_tolerance(self):
        result = self.comp.compare_dates("2024-01-16", date(2024, 1, 15), tolerance_days=3)
        self.assertTrue(result.matches)

    def test_text_exact(self):
        result = self.comp.compare_text("hello world", "hello world")
        self.assertTrue(result.matches)

    def test_text_fuzzy(self):
        result = self.comp.compare_text("hello world", "hello worlb", threshold=0.8)
        self.assertTrue(result.matches)


if __name__ == "__main__":
    unittest.main()
