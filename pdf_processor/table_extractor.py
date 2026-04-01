"""Table extraction from PDF pages using pdfplumber with fallbacks."""

import io
from decimal import Decimal

import pandas as pd
import fitz

from config import CONFIG
from audit.models import ExtractedTable

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


class TableExtractor:
    """Extract tables from PDF pages."""

    def extract_tables(self, page: fitz.Page, page_number: int,
                       page_type: str) -> list[ExtractedTable]:
        """Extract all tables from a page.

        Uses pdfplumber for native pages, with fallback strategies.
        """
        if page_type == "scanned":
            # For scanned pages, pdfplumber won't work well on the raw PDF
            # We rely on text-based table detection from OCR output
            return []

        if pdfplumber is None:
            return []

        tables = []

        # Get page bytes for pdfplumber
        try:
            # Extract single page as PDF bytes
            src_doc = page.parent
            tmp_doc = fitz.open()
            tmp_doc.insert_pdf(src_doc, from_page=page.number, to_page=page.number)
            pdf_bytes = tmp_doc.tobytes()
            tmp_doc.close()

            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                if not pdf.pages:
                    return []
                plumber_page = pdf.pages[0]

                # Strategy 1: Line-based (for ruled tables)
                extracted = self._extract_with_lines(plumber_page)
                if not extracted:
                    # Strategy 2: Text-based (for borderless tables)
                    extracted = self._extract_with_text(plumber_page)

                for i, raw_table in enumerate(extracted):
                    df = self._raw_to_dataframe(raw_table)
                    if df is not None and not df.empty:
                        # Calculate confidence based on data quality
                        confidence = self._estimate_table_confidence(df)
                        tables.append(ExtractedTable(
                            page_number=page_number,
                            data=df,
                            headers=list(df.columns),
                            bbox=(0, 0, 0, 0),  # simplified
                            confidence=confidence,
                            low_confidence_cells=[],
                        ))

        except Exception:
            pass

        return tables

    def _extract_with_lines(self, page) -> list[list[list[str]]]:
        """Extract tables using line-based detection (for ruled tables)."""
        settings = {
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
            "snap_tolerance": CONFIG.table_snap_tolerance,
            "join_tolerance": CONFIG.table_join_tolerance,
        }
        try:
            tables = page.extract_tables(table_settings=settings)
            return [t for t in tables if t] if tables else []
        except Exception:
            return []

    def _extract_with_text(self, page) -> list[list[list[str]]]:
        """Extract tables using text alignment (for borderless tables)."""
        settings = {
            "vertical_strategy": "text",
            "horizontal_strategy": "text",
            "snap_tolerance": CONFIG.table_snap_tolerance,
            "join_tolerance": CONFIG.table_join_tolerance,
        }
        try:
            tables = page.extract_tables(table_settings=settings)
            return [t for t in tables if t] if tables else []
        except Exception:
            return []

    def _raw_to_dataframe(self, raw_table: list[list[str]]) -> pd.DataFrame | None:
        """Convert raw table (list of rows) to a clean DataFrame."""
        if not raw_table or len(raw_table) < 2:
            return None

        # Clean cells
        cleaned = []
        for row in raw_table:
            cleaned_row = []
            for cell in row:
                if cell is None:
                    cleaned_row.append("")
                else:
                    cleaned_row.append(str(cell).strip())
            cleaned_row = cleaned_row
            cleaned.append(cleaned_row)

        # Use first row as header
        headers = cleaned[0]
        # Ensure unique headers
        seen = {}
        unique_headers = []
        for h in headers:
            h = h if h else "Column"
            if h in seen:
                seen[h] += 1
                unique_headers.append(f"{h}_{seen[h]}")
            else:
                seen[h] = 0
                unique_headers.append(h)

        data_rows = cleaned[1:]
        if not data_rows:
            return None

        # Ensure all rows have same length as headers
        max_cols = len(unique_headers)
        normalized_rows = []
        for row in data_rows:
            if len(row) < max_cols:
                row = row + [""] * (max_cols - len(row))
            elif len(row) > max_cols:
                row = row[:max_cols]
            normalized_rows.append(row)

        return pd.DataFrame(normalized_rows, columns=unique_headers)

    def _estimate_table_confidence(self, df: pd.DataFrame) -> float:
        """Estimate extraction confidence for a table."""
        if df.empty:
            return 0.0

        total_cells = df.size
        empty_cells = (df == "").sum().sum() + df.isna().sum().sum()
        non_empty_ratio = 1.0 - (empty_cells / total_cells) if total_cells > 0 else 0.0

        # Tables with too many empty cells are likely misdetected
        if non_empty_ratio < 0.3:
            return 0.3

        return min(1.0, non_empty_ratio * 0.8 + 0.2)
