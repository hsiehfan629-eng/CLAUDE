"""Data models for the audit detail testing application."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

import pandas as pd


# --- PDF Processing Models ---

@dataclass
class TextBlock:
    page_number: int
    content: str
    bbox: tuple  # (x0, y0, x1, y1)
    confidence: float  # 0.0-1.0, 1.0 for native text
    block_type: str  # "paragraph", "header", "footer"


@dataclass
class ExtractedTable:
    page_number: int
    data: pd.DataFrame
    headers: list[str]
    bbox: tuple
    confidence: float
    low_confidence_cells: list[tuple[int, int]]  # (row, col)


@dataclass
class ProcessedDocument:
    file_name: str
    total_pages: int
    page_types: list[str]  # per-page: "native", "scanned", "mixed", "error"
    text_blocks: list[TextBlock]
    extracted_tables: list[ExtractedTable]
    raw_text_by_page: dict[int, str]
    processing_time: float
    warnings: list[str]

    @property
    def full_text(self) -> str:
        """Concatenate all page text."""
        return "\n\n".join(
            self.raw_text_by_page.get(p, "")
            for p in sorted(self.raw_text_by_page.keys())
        )


# --- Audit Models ---

@dataclass
class ComparisonResult:
    matches: bool
    confidence: float  # 0.0-1.0
    extracted_value: str
    expected_value: str
    difference: str  # numeric difference or text diff description
    notes: str


@dataclass
class AuditFinding:
    finding_id: str
    test_type: str  # "vouching", "tracing", "recalculation", "analytical"
    status: str  # "pass", "fail", "manual_review", "error"
    severity: str  # "high", "medium", "low", "info"
    sample_id: str  # reference to the Excel sample row
    matched_pdf: str  # which PDF file was matched
    field_name: str
    extracted_value: str
    expected_value: str
    difference: str
    confidence: float
    requires_manual_review: bool
    message: str
    page_number: int = 0

    @staticmethod
    def create(test_type: str, status: str, severity: str, sample_id: str,
               matched_pdf: str, field_name: str, extracted_value: str,
               expected_value: str, difference: str, confidence: float,
               message: str, page_number: int = 0) -> AuditFinding:
        return AuditFinding(
            finding_id=str(uuid.uuid4())[:8],
            test_type=test_type,
            status=status,
            severity=severity,
            sample_id=sample_id,
            matched_pdf=matched_pdf,
            field_name=field_name,
            extracted_value=extracted_value,
            expected_value=expected_value,
            difference=difference,
            confidence=confidence,
            requires_manual_review=confidence < 0.6 or status == "manual_review",
            message=message,
            page_number=page_number,
        )


@dataclass
class AuditTestConfig:
    test_type: str  # "vouching", "tracing", "recalculation", "analytical"
    amount_tolerance: Decimal = Decimal("0.01")
    amount_tolerance_pct: Decimal = Decimal("0.01")
    date_tolerance_days: int = 3
    key_fields: list[str] = field(default_factory=list)
    field_mappings: dict[str, str] = field(default_factory=dict)  # pdf_field -> excel_field
    sum_columns: list[str] = field(default_factory=list)  # for recalculation
    total_column: str = ""  # for recalculation
    analytical_threshold_pct: Decimal = Decimal("0.10")  # 10%


@dataclass
class AuditReport:
    report_id: str
    created_at: datetime
    test_config: AuditTestConfig
    findings: list[AuditFinding]
    total_tested: int
    total_pass: int
    total_fail: int
    total_manual_review: int
    documents_processed: list[str]

    @property
    def pass_rate(self) -> float:
        return self.total_pass / self.total_tested if self.total_tested > 0 else 0.0

    @property
    def exception_rate(self) -> float:
        return self.total_fail / self.total_tested if self.total_tested > 0 else 0.0
