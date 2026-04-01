"""Revenue detail testing: 5 verification checks.

① System info vs contract consistency (customer, product, spec, price)
② Delivery note consistency (delivery no, qty, date vs signed receipt)
③ Revenue amount accuracy (recalculation)
④ Revenue timing compliance (sign date <= confirm date, same month)
⑤ Signer authorization verification
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pandas as pd

from config import CONFIG
from audit.models import DeliveryGroup, DocumentInfo, VerificationSummary
from utils.helpers import parse_financial_amount, normalize_date, clean_text


class RevenueVerifier:
    """Execute the 5 revenue verification checks on each delivery group."""

    def verify_all(self, groups: list[DeliveryGroup]) -> VerificationSummary:
        """Run all 5 checks on all delivery groups."""
        summary = VerificationSummary(total_groups=len(groups))

        for group in groups:
            # Fill info from receipt first
            self._fill_receipt_info(group)

            # Run 5 checks
            self.check1_contract_consistency(group)
            self.check2_delivery_consistency(group)
            self.check3_revenue_accuracy(group)
            self.check4_revenue_timing(group)
            self.check5_signer_authorization(group)

            # Build attachment index and result
            self._build_attachment_info(group)

            # Update summary
            summary.total_checked += 1
            c1 = group.check1_result == "✓"
            c2 = group.check2_result == "✓"
            c3 = group.check3_result == "✓"
            c4 = group.check4_result == "✓"
            c5 = group.check5_result == "✓"

            if c1: summary.check1_pass += 1
            else: summary.check1_fail += 1
            if c2: summary.check2_pass += 1
            else: summary.check2_fail += 1
            if c3: summary.check3_pass += 1
            else: summary.check3_fail += 1
            if c4: summary.check4_pass += 1
            else: summary.check4_fail += 1
            if c5: summary.check5_pass += 1
            else: summary.check5_fail += 1

            if c1 and c2 and c3 and c4 and c5:
                summary.all_pass += 1

        return summary

    def _fill_receipt_info(self, group: DeliveryGroup):
        """Fill logistics/sign info from the matched receipt document."""
        receipt = group.receipt
        if receipt is None:
            return

        group.logistics_company = receipt.logistics_company or ""
        group.logistics_no = receipt.logistics_no or ""
        group.customer_sign_date = receipt.sign_date or ""
        group.signer = receipt.signer or ""

    def check1_contract_consistency(self, group: DeliveryGroup):
        """① Check system info vs contract/order consistency.

        Compare: customer name, product name, spec model, unit price.
        """
        contract = group.contract
        if contract is None:
            group.check1_result = "缺合同"
            return

        mismatches = []

        # Customer name comparison
        if contract.customer_name:
            sys_customer = clean_text(group.customer_name)
            doc_customer = clean_text(contract.customer_name)
            if sys_customer and doc_customer:
                if sys_customer not in doc_customer and doc_customer not in sys_customer:
                    mismatches.append(f"客户名称不一致：系统'{sys_customer}' vs 合同'{doc_customer}'")

        # Product name comparison (contains check, either direction)
        if contract.product_name:
            sys_product = clean_text(group.material_name)
            doc_product = clean_text(contract.product_name)
            if sys_product and doc_product:
                if sys_product not in doc_product and doc_product not in sys_product:
                    mismatches.append(f"产品名称不一致：系统'{sys_product}' vs 合同'{doc_product}'")

        # Spec model comparison (case insensitive)
        if contract.spec_model:
            sys_spec = clean_text(group.spec_model).lower()
            doc_spec = clean_text(contract.spec_model).lower()
            if sys_spec and doc_spec:
                if sys_spec != doc_spec:
                    mismatches.append(f"规格型号不一致：系统'{group.spec_model}' vs 合同'{contract.spec_model}'")

        # Unit price comparison
        if contract.unit_price is not None and group.unit_price is not None:
            if contract.unit_price != group.unit_price:
                mismatches.append(
                    f"单价不一致：系统{group.unit_price} vs 合同{contract.unit_price}"
                )

        group.check1_result = "✓" if not mismatches else "; ".join(mismatches)

    def check2_delivery_consistency(self, group: DeliveryGroup):
        """② Check delivery note info consistency.

        Compare: delivery no, total qty, delivery date vs signed receipt.
        """
        receipt = group.receipt
        if receipt is None:
            group.check2_result = "缺回签联"
            return

        mismatches = []

        # Delivery number
        if receipt.delivery_no:
            sys_no = clean_text(group.delivery_no)
            doc_no = clean_text(receipt.delivery_no)
            if sys_no and doc_no and sys_no != doc_no:
                mismatches.append(f"出库单号不一致：系统'{sys_no}' vs 回签联'{doc_no}'")

        # Total quantity
        if receipt.delivery_qty is not None:
            if group.total_qty != receipt.delivery_qty:
                mismatches.append(
                    f"出库数量不一致：系统{group.total_qty} vs 回签联{receipt.delivery_qty}"
                )

        # Delivery date
        if receipt.delivery_date:
            sys_date = clean_text(group.delivery_date)
            doc_date = clean_text(receipt.delivery_date)
            if sys_date and doc_date:
                # Normalize both dates for comparison
                sys_d = normalize_date(sys_date)
                doc_d = normalize_date(doc_date)
                if sys_d and doc_d and sys_d != doc_d:
                    mismatches.append(
                        f"出库日期不一致：系统{sys_date} vs 回签联{receipt.delivery_date}"
                    )

        group.check2_result = "✓" if not mismatches else "; ".join(mismatches)

    def check3_revenue_accuracy(self, group: DeliveryGroup):
        """③ Check revenue amount accuracy.

        含税收入 = 出库数量汇总 × 产品单价
        不含税收入 = 含税收入 ÷ 1.13
        Tolerance: ±1 yuan
        """
        if group.unit_price is None or group.total_qty == 0:
            group.check3_result = "数据不完整，无法计算"
            return

        tolerance = CONFIG.amount_tolerance
        tax_rate = CONFIG.tax_rate
        mismatches = []

        # Calculate expected values
        expected_tax = group.unit_price * group.total_qty
        expected_notax = expected_tax / tax_rate

        # Compare 含税收入
        actual_tax = group.total_revenue_tax
        diff_tax = abs(actual_tax - expected_tax)
        if diff_tax > tolerance:
            mismatches.append(
                f"含税收入差异：系统{actual_tax} vs 计算{expected_tax}，差{actual_tax - expected_tax}"
            )

        # Compare 不含税收入
        actual_notax = group.total_revenue_notax
        diff_notax = abs(actual_notax - expected_notax)
        if diff_notax > tolerance:
            mismatches.append(
                f"不含税收入差异：系统{actual_notax} vs 计算{expected_notax:.2f}，差{actual_notax - expected_notax:.2f}"
            )

        group.check3_result = "✓" if not mismatches else "; ".join(mismatches)

    def check4_revenue_timing(self, group: DeliveryGroup):
        """④ Check revenue confirmation timing compliance.

        Rules:
        - Customer sign date <= Revenue confirmation date
        - Both dates in the same month
        """
        confirm_date_str = group.confirm_date
        sign_date_str = group.customer_sign_date

        if not confirm_date_str:
            group.check4_result = "收入确认日期缺失"
            return

        if not sign_date_str:
            group.check4_result = "日期缺失"
            return

        confirm_d = normalize_date(confirm_date_str)
        sign_d = _parse_short_date(sign_date_str, confirm_date_str)

        if confirm_d is None:
            group.check4_result = f"无法解析收入确认日期：{confirm_date_str}"
            return
        if sign_d is None:
            group.check4_result = f"无法解析签收日期：{sign_date_str}"
            return

        mismatches = []

        # Check: sign date <= confirm date
        if sign_d > confirm_d:
            mismatches.append(f"签收{sign_d} > 确认{confirm_d}，时点不合规")

        # Check: same month
        if sign_d.year != confirm_d.year or sign_d.month != confirm_d.month:
            mismatches.append(
                f"签收{sign_d} vs 确认{confirm_d}，跨月"
            )

        group.check4_result = "✓" if not mismatches else "; ".join(mismatches)

    def check5_signer_authorization(self, group: DeliveryGroup):
        """⑤ Check if the signer is authorized.

        Rules:
        - Must have authorization letter
        - Authorized person name == signer name on receipt (exact match)
        """
        auth = group.authorization
        signer = group.signer

        if auth is None:
            group.check5_result = "✗ 未提供授权书"
            return

        if not signer:
            group.check5_result = "✗ 回签联未识别到签收人"
            return

        authorized = clean_text(auth.authorized_person)
        actual_signer = clean_text(signer)

        if not authorized:
            group.check5_result = "✗ 授权书未识别到被授权人"
            return

        if authorized == actual_signer:
            group.check5_result = "✓"
        else:
            group.check5_result = f"✗ 授权人\"{authorized}\"≠签收人\"{actual_signer}\""

    def _build_attachment_info(self, group: DeliveryGroup):
        """Build attachment index string and overall attachment result."""
        attachments = []
        idx = 1

        if group.contract:
            name = group.contract.file_name.replace(".pdf", "").replace(".PDF", "")
            attachments.append(f"附件{idx}:合同{name}")
            idx += 1
        if group.receipt:
            name = group.receipt.file_name.replace(".pdf", "").replace(".PDF", "")
            attachments.append(f"附件{idx}:回签联{name}")
            idx += 1
        if group.reconciliation:
            name = group.reconciliation.file_name.replace(".pdf", "").replace(".PDF", "")
            attachments.append(f"附件{idx}:对账单{name}")
            idx += 1
        if group.authorization:
            name = group.authorization.file_name.replace(".pdf", "").replace(".PDF", "")
            attachments.append(f"附件{idx}:授权书{name}")
            idx += 1

        group.attachment_index = "; ".join(attachments) if attachments else ""

        # Overall result
        checks = [
            ("①", group.check1_result),
            ("②", group.check2_result),
            ("③", group.check3_result),
            ("④", group.check4_result),
            ("⑤", group.check5_result),
        ]
        failures = [label for label, result in checks if result != "✓"]

        if not failures:
            group.attachment_result = "全部通过"
        else:
            group.attachment_result = "、".join(failures) + "存在异常"


def _parse_short_date(date_str: str, reference_date_str: str = "") -> date | None:
    """Parse short date formats like '4/8' using year context from reference date."""
    # First try standard formats
    d = normalize_date(date_str)
    if d:
        return d

    # Try short format: M/D or D/M
    date_str = clean_text(date_str)
    m = __import__("re").match(r"^(\d{1,2})/(\d{1,2})$", date_str)
    if m:
        part1, part2 = int(m.group(1)), int(m.group(2))

        # Determine year from reference date
        ref_d = normalize_date(reference_date_str)
        year = ref_d.year if ref_d else datetime.now().year

        # Assume M/D format (month/day)
        if 1 <= part1 <= 12 and 1 <= part2 <= 31:
            try:
                return date(year, part1, part2)
            except ValueError:
                pass

    return None
