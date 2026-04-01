"""Table extraction from PDF pages using pdfplumber + OCR text-based fallback."""

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
    """Extract tables from PDF pages (native and scanned)."""

    def extract_tables(self, page: fitz.Page, page_number: int,
                       page_type: str) -> list[ExtractedTable]:
        """Extract all tables from a page."""
        tables = []

        if page_type == "scanned":
            # For scanned pages, try to reconstruct tables from OCR text
            tables = self._extract_from_text(page, page_number)
            return tables

        if pdfplumber is None:
            return []

        try:
            src_doc = page.parent
            tmp_doc = fitz.open()
            tmp_doc.insert_pdf(src_doc, from_page=page.number, to_page=page.number)
            pdf_bytes = tmp_doc.tobytes()
            tmp_doc.close()

            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                if not pdf.pages:
                    return []
                plumber_page = pdf.pages[0]

                # Strategy 1: Line-based (ruled tables)
                extracted = self._extract_with_lines(plumber_page)
                if not extracted:
                    # Strategy 2: Text-based (borderless tables)
                    extracted = self._extract_with_text(plumber_page)

                for raw_table in extracted:
                    df = self._raw_to_dataframe(raw_table)
                    if df is not None and not df.empty:
                        confidence = self._estimate_table_confidence(df)
                        tables.append(ExtractedTable(
                            page_number=page_number,
                            data=df,
                            headers=list(df.columns),
                            bbox=(0, 0, 0, 0),
                            confidence=confidence,
                            low_confidence_cells=[],
                        ))

        except Exception:
            pass

        return tables

    def _extract_from_text(self, page: fitz.Page, page_number: int) -> list[ExtractedTable]:
        """Reconstruct tables from native text positions (for scanned PDFs after OCR)."""
        tables = []
        try:
            text_dict = page.get_text("dict", flags=0)
            blocks = text_dict.get("blocks", [])

            # Collect all text spans with positions
            spans = []
            for block in blocks:
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if text:
                            bbox = span.get("bbox", (0, 0, 0, 0))
                            spans.append({
                                "text": text,
                                "x0": bbox[0], "y0": bbox[1],
                                "x1": bbox[2], "y1": bbox[3],
                            })

            if len(spans) < 4:
                return []

            # Cluster spans into rows by y-coordinate
            rows = self._cluster_into_rows(spans)
            if len(rows) < 2:
                return []

            # Cluster into columns by x-coordinate
            columns = self._detect_columns(spans)
            if len(columns) < 2:
                return []

            # Build table grid
            grid = []
            for row_spans in rows:
                row_data = [""] * len(columns)
                for span in row_spans:
                    col_idx = self._find_column(span["x0"], columns)
                    if col_idx is not None:
                        if row_data[col_idx]:
                            row_data[col_idx] += " " + span["text"]
                        else:
                            row_data[col_idx] = span["text"]
                grid.append(row_data)

            df = self._raw_to_dataframe(grid)
            if df is not None and not df.empty:
                tables.append(ExtractedTable(
                    page_number=page_number,
                    data=df,
                    headers=list(df.columns),
                    bbox=(0, 0, 0, 0),
                    confidence=0.6,  # lower confidence for text-reconstructed tables
                    low_confidence_cells=[],
                ))

        except Exception:
            pass

        return tables

    def _cluster_into_rows(self, spans: list[dict], tolerance: float = 5.0) -> list[list[dict]]:
        """Cluster text spans into rows by y-coordinate proximity."""
        if not spans:
            return []

        sorted_spans = sorted(spans, key=lambda s: s["y0"])
        rows = []
        current_row = [sorted_spans[0]]
        current_y = sorted_spans[0]["y0"]

        for span in sorted_spans[1:]:
            if abs(span["y0"] - current_y) <= tolerance:
                current_row.append(span)
            else:
                rows.append(sorted(current_row, key=lambda s: s["x0"]))
                current_row = [span]
                current_y = span["y0"]

        if current_row:
            rows.append(sorted(current_row, key=lambda s: s["x0"]))

        return rows

    def _detect_columns(self, spans: list[dict], tolerance: float = 15.0) -> list[float]:
        """Detect column boundaries from x-coordinates of text spans."""
        x_starts = sorted(set(round(s["x0"] / tolerance) * tolerance for s in spans))

        # Merge close x positions
        columns = [x_starts[0]]
        for x in x_starts[1:]:
            if x - columns[-1] > tolerance:
                columns.append(x)

        return columns

    def _find_column(self, x0: float, columns: list[float]) -> int | None:
        """Find which column a span belongs to."""
        best_idx = None
        best_dist = float("inf")
        for i, col_x in enumerate(columns):
            dist = abs(x0 - col_x)
            if dist < best_dist:
                best_dist = dist
                best_idx = i
        return best_idx if best_dist < 50 else None

    def _extract_with_lines(self, page) -> list[list[list[str]]]:
        """Extract tables using line-based detection."""
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
        """Extract tables using text alignment."""
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
        """Convert raw table to a clean DataFrame."""
        if not raw_table or len(raw_table) < 2:
            return None

        cleaned = []
        for row in raw_table:
            cleaned.append([str(cell).strip() if cell else "" for cell in row])

        # Use first row as header
        headers = cleaned[0]
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
        """Estimate extraction confidence based on data quality."""
        if df.empty:
            return 0.0

        total_cells = df.size
        empty_cells = (df == "").sum().sum() + df.isna().sum().sum()
        non_empty_ratio = 1.0 - (empty_cells / total_cells) if total_cells > 0 else 0.0

        if non_empty_ratio < 0.3:
            return 0.3

        return min(1.0, non_empty_ratio * 0.8 + 0.2)
