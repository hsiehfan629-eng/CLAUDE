"""Data models for the revenue detail testing application."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import pandas as pd


# --- PDF Processing Models (reused) ---

@dataclass
class TextBlock:
    page_number: int
    content: str
    bbox: tuple  # (x0, y0, x1, y1)
    confidence: float  # 0.0-1.0
    block_type: str  # "paragraph", "header", "footer"


@dataclass
class ExtractedTable:
    page_number: int
    data: pd.DataFrame
    headers: list[str]
    bbox: tuple
    confidence: float
    low_confidence_cells: list[tuple[int, int]]


@dataclass
class ProcessedDocument:
    file_name: str
    total_pages: int
    page_types: list[str]
    text_blocks: list[TextBlock]
    extracted_tables: list[ExtractedTable]
    raw_text_by_page: dict[int, str]
    processing_time: float
    warnings: list[str]

    @property
    def full_text(self) -> str:
        return "\n\n".join(
            self.raw_text_by_page.get(p, "")
            for p in sorted(self.raw_text_by_page.keys())
        )


# --- Comparison Models (used by comparator) ---

@dataclass
class ComparisonResult:
    matches: bool
    confidence: float
    extracted_value: str
    expected_value: str
    difference: str
    notes: str


# --- Revenue Audit Specific Models ---

@dataclass
class DocumentInfo:
    """Information extracted from a supporting document (PDF)."""
    file_name: str
    doc_type: str  # "contract", "receipt", "reconciliation", "authorization"
    full_text: str
    tables: list[ExtractedTable]
    confidence: float

    # Fields extracted from the document
    customer_name: str = ""
    product_name: str = ""
    spec_model: str = ""
    unit_price: Decimal | None = None

    # Receipt-specific fields
    delivery_no: str = ""
    delivery_qty: int | None = None
    delivery_date: str = ""
    logistics_company: str = ""
    logistics_no: str = ""
    sign_date: str = ""  # customer sign date
    signer: str = ""  # person who signed

    # Authorization-specific
    authorized_person: str = ""


@dataclass
class DeliveryGroup:
    """A group of Excel rows sharing the same delivery note number (出库单号)."""
    delivery_no: str
    rows: pd.DataFrame  # all Excel rows for this delivery note
    row_indices: list[int]  # original Excel row indices (0-based from data start)

    # Aggregated values from Excel
    customer_name: str = ""
    material_name: str = ""
    spec_model: str = ""
    unit_price: Decimal | None = None
    total_qty: int = 0
    total_revenue_tax: Decimal = Decimal("0")
    total_revenue_notax: Decimal = Decimal("0")
    delivery_date: str = ""
    confirm_date: str = ""  # revenue confirmation date (O column)

    # Matched supporting documents
    contract: DocumentInfo | None = None
    receipt: DocumentInfo | None = None
    reconciliation: DocumentInfo | None = None
    authorization: DocumentInfo | None = None

    # Verification results (to fill in Excel)
    logistics_company: str = ""
    logistics_no: str = ""
    customer_sign_date: str = ""
    signer: str = ""
    check1_result: str = ""  # ① contract consistency
    check2_result: str = ""  # ② delivery note consistency
    check3_result: str = ""  # ③ revenue amount accuracy
    check4_result: str = ""  # ④ revenue timing compliance
    check5_result: str = ""  # ⑤ signer authorization
    attachment_index: str = ""
    attachment_result: str = ""


@dataclass
class VerificationSummary:
    """Summary of all verification results."""
    total_groups: int = 0
    total_checked: int = 0
    check1_pass: int = 0
    check2_pass: int = 0
    check3_pass: int = 0
    check4_pass: int = 0
    check5_pass: int = 0
    check1_fail: int = 0
    check2_fail: int = 0
    check3_fail: int = 0
    check4_fail: int = 0
    check5_fail: int = 0
    all_pass: int = 0  # groups where all 5 checks passed
