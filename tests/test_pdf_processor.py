"""Unit tests for revenue detail testing modules."""

import unittest
from decimal import Decimal
from datetime import date

from utils.helpers import parse_financial_amount, normalize_date, clean_text, detect_language
from audit.comparator import DataComparator
from audit.models import DeliveryGroup, DocumentInfo
from audit.detail_tests import RevenueVerifier
import pandas as pd


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


class TestRevenueVerifier(unittest.TestCase):
    def setUp(self):
        self.verifier = RevenueVerifier()

    def _make_group(self, **kwargs):
        defaults = dict(
            delivery_no="ZB240101001",
            rows=pd.DataFrame(),
            row_indices=[0],
            customer_name="测试公司",
            material_name="测试产品",
            spec_model="A100",
            unit_price=Decimal("100"),
            total_qty=10,
            total_revenue_tax=Decimal("1000"),
            total_revenue_notax=Decimal("884.96"),
            delivery_date="2024-01-15",
            confirm_date="2024-01-20",
        )
        defaults.update(kwargs)
        return DeliveryGroup(**defaults)

    def _make_doc(self, doc_type, **kwargs):
        defaults = dict(
            file_name="test.pdf",
            doc_type=doc_type,
            full_text="",
            tables=[],
            confidence=0.9,
        )
        defaults.update(kwargs)
        return DocumentInfo(**defaults)

    def test_check1_pass(self):
        group = self._make_group()
        group.contract = self._make_doc("contract",
            customer_name="测试公司", product_name="测试产品",
            spec_model="A100", unit_price=Decimal("100"))
        self.verifier.check1_contract_consistency(group)
        self.assertEqual(group.check1_result, "✓")

    def test_check1_missing_contract(self):
        group = self._make_group()
        self.verifier.check1_contract_consistency(group)
        self.assertEqual(group.check1_result, "缺合同")

    def test_check1_price_mismatch(self):
        group = self._make_group()
        group.contract = self._make_doc("contract",
            customer_name="测试公司", product_name="测试产品",
            spec_model="A100", unit_price=Decimal("90"))
        self.verifier.check1_contract_consistency(group)
        self.assertIn("单价不一致", group.check1_result)

    def test_check2_pass(self):
        group = self._make_group()
        group.receipt = self._make_doc("receipt",
            delivery_no="ZB240101001", delivery_qty=10,
            delivery_date="2024-01-15")
        self.verifier.check2_delivery_consistency(group)
        self.assertEqual(group.check2_result, "✓")

    def test_check2_missing_receipt(self):
        group = self._make_group()
        self.verifier.check2_delivery_consistency(group)
        self.assertEqual(group.check2_result, "缺回签联")

    def test_check3_pass(self):
        # 10 * 100 = 1000 (tax), 1000/1.13 = 884.96
        group = self._make_group(
            total_revenue_tax=Decimal("1000"),
            total_revenue_notax=Decimal("884.96"),
        )
        self.verifier.check3_revenue_accuracy(group)
        self.assertEqual(group.check3_result, "✓")

    def test_check3_fail(self):
        group = self._make_group(
            total_revenue_tax=Decimal("1050"),  # wrong
            total_revenue_notax=Decimal("884.96"),
        )
        self.verifier.check3_revenue_accuracy(group)
        self.assertIn("含税收入差异", group.check3_result)

    def test_check4_pass(self):
        group = self._make_group(confirm_date="2024-01-20")
        group.customer_sign_date = "2024-01-18"
        self.verifier.check4_revenue_timing(group)
        self.assertEqual(group.check4_result, "✓")

    def test_check4_cross_month(self):
        group = self._make_group(confirm_date="2024-02-03")
        group.customer_sign_date = "2024-01-28"
        self.verifier.check4_revenue_timing(group)
        self.assertIn("跨月", group.check4_result)

    def test_check5_pass(self):
        group = self._make_group()
        group.signer = "张三"
        group.authorization = self._make_doc("authorization",
            authorized_person="张三")
        self.verifier.check5_signer_authorization(group)
        self.assertEqual(group.check5_result, "✓")

    def test_check5_no_auth(self):
        group = self._make_group()
        group.signer = "张三"
        self.verifier.check5_signer_authorization(group)
        self.assertEqual(group.check5_result, "✗ 未提供授权书")

    def test_check5_mismatch(self):
        group = self._make_group()
        group.signer = "李四"
        group.authorization = self._make_doc("authorization",
            authorized_person="张三")
        self.verifier.check5_signer_authorization(group)
        self.assertIn("授权人", group.check5_result)
        self.assertIn("签收人", group.check5_result)


if __name__ == "__main__":
    unittest.main()
