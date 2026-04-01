"""Classify supporting documents by filename keywords and extract key information.

Enhanced with comprehensive regex patterns for Chinese financial documents,
OCR error tolerance, and full-width character handling.
"""

import re
from decimal import Decimal

from config import CONFIG
from audit.models import DocumentInfo, ProcessedDocument
from utils.helpers import parse_financial_amount, clean_text, normalize_fullwidth


def classify_document(doc: ProcessedDocument) -> DocumentInfo:
    """Classify a PDF document and extract relevant fields."""
    fname = doc.file_name.lower()
    full_text = normalize_fullwidth(doc.full_text)
    tables = doc.extracted_tables

    doc_type = _detect_type(fname)

    info = DocumentInfo(
        file_name=doc.file_name,
        doc_type=doc_type,
        full_text=full_text,
        tables=tables,
        confidence=0.8,
    )

    if doc_type == "contract":
        _extract_contract_fields(info, full_text, tables)
    elif doc_type == "receipt":
        _extract_receipt_fields(info, full_text, tables)
    elif doc_type == "authorization":
        _extract_authorization_fields(info, full_text)

    return info


def _detect_type(filename: str) -> str:
    """Detect document type from filename keywords."""
    for kw in CONFIG.contract_keywords:
        if kw in filename:
            return "contract"
    for kw in CONFIG.receipt_keywords:
        if kw in filename:
            return "receipt"
    for kw in CONFIG.authorization_keywords:
        if kw in filename:
            return "authorization"
    for kw in CONFIG.reconciliation_keywords:
        if kw in filename:
            return "reconciliation"
    return "unknown"


def _search_patterns(text: str, patterns: list[str], flags=0) -> str:
    """Try multiple regex patterns and return first match group 1."""
    for pattern in patterns:
        m = re.search(pattern, text, flags)
        if m:
            return clean_text(m.group(1))
    return ""


def _extract_contract_fields(info: DocumentInfo, text: str, tables: list):
    """Extract customer name, product name, spec, unit price from contract."""
    # --- Customer name ---
    info.customer_name = _search_patterns(text, [
        r"(?:甲方|甲方名称|买方|购买方|客户|需方|采购方|发包方)[：:]\s*([^\n\r,，;；]{2,40})",
        r"(?:乙方|卖方|销售方|供方|供应商|承包方)[：:]\s*([^\n\r,，;；]{2,40})",
    ])

    # --- Product name ---
    info.product_name = _search_patterns(text, [
        r"(?:产品名称|品名|货物名称|物料名称|商品名称|货物描述)[：:]\s*([^\n\r]{2,60})",
        r"(?:品名及规格|产品及规格)[：:]\s*([^\n\r]{2,60})",
    ])

    # --- Spec model ---
    info.spec_model = _search_patterns(text, [
        r"(?:规格型号|规格|型号|外形尺寸)[：:]\s*([^\n\r]{1,50})",
    ])

    # --- Unit price (try text patterns first, then table) ---
    price_text = _search_patterns(text, [
        r"(?:含税单价|含税价格|含税价|单价)[：:]\s*([\d,.\uff0c\uff0e]+)",
        r"(?:不含税单价|不含税价格|不含税价)[：:]\s*([\d,.\uff0c\uff0e]+)",
        r"(?:价格|售价)[：:]\s*([\d,.\uff0c\uff0e]+)",
        r"(?:单价|含税单价)\s+([\d,.\uff0c\uff0e]+)",
    ])
    if price_text:
        info.unit_price = parse_financial_amount(price_text)

    # Fallback: try to find prices in tables
    if info.unit_price is None:
        for table in tables:
            df = table.data
            if df.empty:
                continue
            for col in df.columns:
                col_str = str(col)
                if any(kw in col_str for kw in ["单价", "价格", "含税"]):
                    for val in df[col]:
                        amount = parse_financial_amount(str(val))
                        if amount is not None and Decimal("0.01") < amount < Decimal("999999"):
                            info.unit_price = amount
                            break
                    if info.unit_price:
                        break
            if info.unit_price:
                break


def _extract_receipt_fields(info: DocumentInfo, text: str, tables: list):
    """Extract delivery info, logistics, sign date, signer from receipt."""
    # --- Delivery note number ---
    info.delivery_no = _search_patterns(text, [
        r"(?:出库单号|单据编号|单号|编号|No|NO)[.：:]*\s*(\S{4,25})",
    ])

    # --- Delivery quantity ---
    qty_str = _search_patterns(text, [
        r"(?:合计|总数量|总计|数量合计)[：:]*\s*(\d+(?:[.,]\d+)?)\s*(?:件|个|台|套|kg|吨)?",
        r"(?:数量)\s+(\d+)",
    ])
    if qty_str:
        try:
            info.delivery_qty = int(float(qty_str.replace(",", "")))
        except (ValueError, TypeError):
            pass

    # Also sum from tables if qty not found
    if info.delivery_qty is None:
        for table in tables:
            df = table.data
            for col in df.columns:
                if "数量" in str(col) or "qty" in str(col).lower():
                    try:
                        total = 0
                        for v in df[col]:
                            s = str(v).strip()
                            if s and s.replace(".", "").replace(",", "").isdigit():
                                total += int(float(s.replace(",", "")))
                        if total > 0:
                            info.delivery_qty = total
                    except (ValueError, TypeError):
                        pass

    # --- Delivery date ---
    info.delivery_date = _search_patterns(text, [
        r"(?:制单日期|出库日期|日期|发货日期)[：:]\s*(\d{4}[-/年.]\d{1,2}[-/月.]\d{1,2}日?)",
        r"(?:制单日期|出库日期)[：:]\s*(\d{4}\d{2}\d{2})",
        r"(?:日期)[：:]\s*(\d{1,2}月\d{1,2}日)",
    ])

    # --- Logistics company ---
    info.logistics_company = _search_patterns(text, [
        r"(?:物流公司|快递公司|承运人|物流|运输公司)[：:]\s*([^\n，；:：]{2,20})",
    ])

    # --- Logistics tracking number ---
    info.logistics_no = _search_patterns(text, [
        r"(?:物流单号|快递单号|运单号|物流编号|快递编号)[：:]\s*([A-Za-z0-9]{6,25})",
        r"(?:物流单号|快递单号|运单号)[：:]\s*(\S{6,25})",
    ])

    # --- Customer sign date ---
    info.sign_date = _search_patterns(text, [
        r"(?:签收日期|收货日期|客户签收日期)[：:]\s*(\d{4}[-/年.]\d{1,2}[-/月.]\d{1,2}日?)",
        r"(?:签收日期|收货日期)[：:]\s*(\d{1,2}[/月]\d{1,2}日?)",
        # Look for date near bottom/signature area
        r"(?:签收|收货|签名).*?(\d{1,2}/\d{1,2})",
        r"(\d{1,2}月\d{1,2}日)\s*(?:签收|收到|确认)",
    ], flags=re.DOTALL)

    # --- Signer name ---
    signer = _search_patterns(text, [
        r"(?:签收人|收货人|领货人|签收)[：:]\s*([^\n，；(（【章]{2,8})",
        r"(?:收货方签章|客户签章|客户签名)[：:]*\s*([^\n，；(（【章]{2,8})",
    ])
    # Filter: must be a person name (2-5 chars, no special chars)
    if signer and 2 <= len(signer) <= 8 and "章" not in signer and "公司" not in signer:
        info.signer = signer

    # --- Customer name from receipt ---
    info.customer_name = _search_patterns(text, [
        r"(?:客户名称|客户|收货单位|购买方|收货方)[：:]\s*([^\n，；]{2,40})",
    ])


def _extract_authorization_fields(info: DocumentInfo, text: str):
    """Extract authorized person name from authorization letter."""
    person = _search_patterns(text, [
        r"(?:被授权人|授权代表|受托人|被委托人)[：:]\s*([^\n，；和及]{2,8})",
        r"(?:兹授权|特授权|现授权|兹委托)\s*([^\n，；且和及]{2,5})\s*(?:为|作为|代为|代表)",
        r"(?:授权|委托)\s+([^\n，；且和及]{2,5})\s+(?:为|作为|代为|代表)",
    ])
    if person and 2 <= len(person) <= 8:
        info.authorized_person = person
