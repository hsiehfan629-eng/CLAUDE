"""Classify supporting documents by filename keywords and extract key information."""

import re
from decimal import Decimal

from config import CONFIG
from audit.models import DocumentInfo, ProcessedDocument
from utils.helpers import parse_financial_amount, clean_text


def classify_document(doc: ProcessedDocument) -> DocumentInfo:
    """Classify a PDF document by its filename and extract relevant fields."""
    fname = doc.file_name.lower()
    full_text = doc.full_text
    tables = doc.extracted_tables

    # Determine document type by filename keywords
    doc_type = _detect_type(fname)

    info = DocumentInfo(
        file_name=doc.file_name,
        doc_type=doc_type,
        full_text=full_text,
        tables=tables,
        confidence=0.8,
    )

    # Extract fields based on document type
    if doc_type == "contract":
        _extract_contract_fields(info, full_text, tables)
    elif doc_type == "receipt":
        _extract_receipt_fields(info, full_text, tables)
    elif doc_type == "authorization":
        _extract_authorization_fields(info, full_text)
    # reconciliation: no specific field extraction needed

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


def _extract_contract_fields(info: DocumentInfo, text: str, tables: list):
    """Extract customer name, product name, spec, unit price from contract."""
    # Try to extract from tables first (contracts often have item tables)
    for table in tables:
        df = table.data
        if df.empty:
            continue

        # Look for columns that might contain product/price info
        for _, row in df.iterrows():
            row_text = " ".join(str(v) for v in row.values)

            # Try to find unit price in table rows
            for val in row.values:
                s = str(val).strip()
                amount = parse_financial_amount(s)
                if amount is not None and Decimal("0.01") < amount < Decimal("100000"):
                    if info.unit_price is None:
                        info.unit_price = amount

    # Extract from text using patterns
    # Customer name - look for common patterns
    customer_patterns = [
        r"(?:甲方|买方|购买方|客户|需方)[：:]\s*(.+?)(?:\n|$)",
        r"(?:乙方|卖方|销售方|供方)[：:]\s*(.+?)(?:\n|$)",
    ]
    for pattern in customer_patterns:
        m = re.search(pattern, text)
        if m:
            info.customer_name = clean_text(m.group(1))
            break

    # Product name / spec model from text
    product_patterns = [
        r"(?:产品名称|品名|货物名称|物料名称)[：:]\s*(.+?)(?:\n|$)",
        r"(?:品名及规格)[：:]\s*(.+?)(?:\n|$)",
    ]
    for pattern in product_patterns:
        m = re.search(pattern, text)
        if m:
            info.product_name = clean_text(m.group(1))
            break

    spec_patterns = [
        r"(?:规格型号|规格|型号)[：:]\s*(.+?)(?:\n|$)",
    ]
    for pattern in spec_patterns:
        m = re.search(pattern, text)
        if m:
            info.spec_model = clean_text(m.group(1))
            break

    # Unit price from text
    price_patterns = [
        r"(?:单价|含税单价|含税价|价格)[：:]\s*([\d,.\uff0c\uff0e]+)",
        r"(?:单价|含税单价)\s+([\d,.\uff0c\uff0e]+)",
    ]
    for pattern in price_patterns:
        m = re.search(pattern, text)
        if m:
            price = parse_financial_amount(m.group(1))
            if price is not None:
                info.unit_price = price
                break


def _extract_receipt_fields(info: DocumentInfo, text: str, tables: list):
    """Extract delivery info, logistics, sign date, signer from receipt."""
    # Delivery note number
    delivery_patterns = [
        r"(?:出库单号|单据编号|单号|编号)[：:]\s*(\S+)",
        r"(?:No|NO|编号)[.：:]\s*(\S+)",
    ]
    for pattern in delivery_patterns:
        m = re.search(pattern, text)
        if m:
            info.delivery_no = clean_text(m.group(1))
            break

    # Delivery quantity - look for total quantity
    qty_patterns = [
        r"(?:合计|总数量|数量合计|总计)[：:]*\s*(\d+)",
        r"(?:数量)\s+(\d+)",
    ]
    for pattern in qty_patterns:
        m = re.search(pattern, text)
        if m:
            try:
                info.delivery_qty = int(m.group(1))
            except ValueError:
                pass
            break

    # Also try to sum quantities from tables
    if info.delivery_qty is None:
        for table in tables:
            df = table.data
            for col in df.columns:
                col_lower = str(col).lower()
                if "数量" in col_lower or "qty" in col_lower:
                    try:
                        total = sum(int(float(str(v))) for v in df[col] if str(v).strip().isdigit())
                        if total > 0:
                            info.delivery_qty = total
                    except (ValueError, TypeError):
                        pass

    # Delivery date
    date_patterns = [
        r"(?:制单日期|出库日期|日期)[：:]\s*(\d{4}[-/年.]\d{1,2}[-/月.]\d{1,2}日?)",
        r"(?:日期)[：:]\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
    ]
    for pattern in date_patterns:
        m = re.search(pattern, text)
        if m:
            info.delivery_date = clean_text(m.group(1))
            break

    # Logistics company
    logistics_patterns = [
        r"(?:物流公司|快递公司|承运人|物流)[：:]\s*(.+?)(?:\n|$)",
        r"(?:物流|快递|运输)\s*[：:]\s*(.+?)(?:\n|$)",
    ]
    for pattern in logistics_patterns:
        m = re.search(pattern, text)
        if m:
            info.logistics_company = clean_text(m.group(1))
            break

    # Logistics tracking number
    tracking_patterns = [
        r"(?:物流单号|快递单号|运单号|物流编号)[：:]\s*(\S+)",
    ]
    for pattern in tracking_patterns:
        m = re.search(pattern, text)
        if m:
            info.logistics_no = clean_text(m.group(1))
            break

    # Sign date - look for date near signature area
    # Common pattern: "4/8" or "2024/4/8" near bottom of document
    sign_date_patterns = [
        r"(?:签收日期|收货日期|签收)[：:]\s*(\d{4}[-/年.]\d{1,2}[-/月.]\d{1,2}日?)",
        r"(?:签收日期|收货日期)[：:]\s*(\d{1,2}/\d{1,2})",
        r"(?:日期)[：:]*\s*(\d{1,2}/\d{1,2})\s*$",
    ]
    for pattern in sign_date_patterns:
        m = re.search(pattern, text, re.MULTILINE)
        if m:
            info.sign_date = clean_text(m.group(1))
            break

    # Signer name
    signer_patterns = [
        r"(?:签收人|收货人|签收)[：:]\s*(.+?)(?:\n|$)",
        r"(?:收货方签章|客户签章)[：:]*\s*(.+?)(?:\n|$)",
    ]
    for pattern in signer_patterns:
        m = re.search(pattern, text)
        if m:
            name = clean_text(m.group(1))
            # Filter out stamps/seals - we need actual person name
            if name and "章" not in name and len(name) <= 10:
                info.signer = name
                break

    # Customer name from receipt
    customer_patterns = [
        r"(?:客户名称|客户|收货单位|购买方)[：:]\s*(.+?)(?:\n|$)",
    ]
    for pattern in customer_patterns:
        m = re.search(pattern, text)
        if m:
            info.customer_name = clean_text(m.group(1))
            break


def _extract_authorization_fields(info: DocumentInfo, text: str):
    """Extract authorized person name from authorization letter."""
    auth_patterns = [
        r"(?:被授权人|授权代表|受托人|被委托人)[：:]\s*(.+?)(?:\n|[,，]|$)",
        r"(?:授权|委托)\s*(.{2,4})\s*(?:为|作为|代表)",
        r"(?:兹授权|兹委托)\s*(.{2,4})\s*",
    ]
    for pattern in auth_patterns:
        m = re.search(pattern, text)
        if m:
            name = clean_text(m.group(1))
            if name and len(name) <= 10:
                info.authorized_person = name
                break
