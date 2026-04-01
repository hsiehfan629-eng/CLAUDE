"""Audit detail test implementations: vouching, tracing, recalculation, analytical."""

from decimal import Decimal

import pandas as pd

from audit.models import (
    AuditFinding,
    AuditTestConfig,
    ProcessedDocument,
    ExtractedTable,
)
from audit.comparator import DataComparator
from utils.helpers import parse_financial_amount, clean_text


class DetailTestRunner:
    """Run audit detail tests on extracted PDF data against Excel samples."""

    def __init__(self):
        self.comparator = DataComparator()

    def run_test(self, config: AuditTestConfig, documents: list[ProcessedDocument],
                 sample_data: pd.DataFrame) -> list[AuditFinding]:
        """Dispatch to the appropriate test method."""
        if config.test_type == "vouching":
            return self.vouching_test(config, documents, sample_data)
        elif config.test_type == "tracing":
            return self.tracing_test(config, documents, sample_data)
        elif config.test_type == "recalculation":
            return self.recalculation_test(config, documents)
        elif config.test_type == "analytical":
            return self.analytical_test(config, documents, sample_data)
        else:
            return []

    def vouching_test(self, config: AuditTestConfig, documents: list[ProcessedDocument],
                      sample_data: pd.DataFrame) -> list[AuditFinding]:
        """Vouching: verify each Excel sample item exists in the PDF documents.

        For each row in the Excel sample, search across all PDF extracted tables
        to find a matching record, then compare mapped fields.
        """
        findings = []
        all_pdf_tables = []

        # Collect all tables from all documents
        for doc in documents:
            for table in doc.extracted_tables:
                all_pdf_tables.append((doc.file_name, table))

        # For each sample row
        for idx, sample_row in sample_data.iterrows():
            sample_id = str(sample_row.get(config.key_fields[0], idx)) if config.key_fields else str(idx)

            best_match = None
            best_score = 0.0
            best_doc_name = ""
            best_page = 0

            # Search across all PDF tables for a match
            for doc_name, table in all_pdf_tables:
                match_result = self._find_match_in_table(
                    table, sample_row, config.key_fields, config.field_mappings
                )
                if match_result and match_result[1] > best_score:
                    best_match = match_result[0]
                    best_score = match_result[1]
                    best_doc_name = doc_name
                    best_page = table.page_number

            if best_match is None:
                # No match found
                findings.append(AuditFinding.create(
                    test_type="vouching",
                    status="fail",
                    severity="high",
                    sample_id=sample_id,
                    matched_pdf="",
                    field_name="record",
                    extracted_value="NOT FOUND",
                    expected_value=str(dict(sample_row)),
                    difference="Missing",
                    confidence=0.0,
                    message=f"Sample {sample_id}: No matching record found in any PDF",
                ))
                continue

            # Compare mapped fields
            for pdf_field, excel_field in config.field_mappings.items():
                if excel_field not in sample_row.index:
                    continue

                extracted_val = str(best_match.get(pdf_field, ""))
                expected_val = sample_row[excel_field]

                result = self.comparator.auto_compare(
                    extracted_val, expected_val,
                    tolerance=config.amount_tolerance,
                    tolerance_pct=config.amount_tolerance_pct,
                    tolerance_days=config.date_tolerance_days,
                )

                if result.matches:
                    findings.append(AuditFinding.create(
                        test_type="vouching",
                        status="pass",
                        severity="info",
                        sample_id=sample_id,
                        matched_pdf=best_doc_name,
                        field_name=excel_field,
                        extracted_value=result.extracted_value,
                        expected_value=result.expected_value,
                        difference=result.difference,
                        confidence=result.confidence,
                        message=f"Match: {excel_field}",
                        page_number=best_page,
                    ))
                else:
                    severity = "high" if pdf_field in config.key_fields else "medium"
                    findings.append(AuditFinding.create(
                        test_type="vouching",
                        status="fail",
                        severity=severity,
                        sample_id=sample_id,
                        matched_pdf=best_doc_name,
                        field_name=excel_field,
                        extracted_value=result.extracted_value,
                        expected_value=result.expected_value,
                        difference=result.difference,
                        confidence=result.confidence,
                        message=f"Mismatch: {excel_field} - {result.notes}",
                        page_number=best_page,
                    ))

        return findings

    def tracing_test(self, config: AuditTestConfig, documents: list[ProcessedDocument],
                     sample_data: pd.DataFrame) -> list[AuditFinding]:
        """Tracing: verify each PDF record has a corresponding entry in the sample.

        Inverse of vouching - start from PDF records and look for them in Excel.
        """
        findings = []

        for doc in documents:
            for table in doc.extracted_tables:
                df = table.data
                for row_idx, pdf_row in df.iterrows():
                    # Try to find this PDF record in the sample data
                    matched = False
                    best_sample_id = ""

                    for sample_idx, sample_row in sample_data.iterrows():
                        score = self._compute_match_score(
                            pdf_row, sample_row, config.key_fields, config.field_mappings
                        )
                        if score > 0.7:
                            matched = True
                            best_sample_id = str(sample_row.get(
                                config.key_fields[0], sample_idx
                            )) if config.key_fields else str(sample_idx)
                            break

                    if not matched:
                        findings.append(AuditFinding.create(
                            test_type="tracing",
                            status="fail",
                            severity="high",
                            sample_id=f"PDF_row_{row_idx}",
                            matched_pdf=doc.file_name,
                            field_name="record",
                            extracted_value=str(dict(pdf_row)),
                            expected_value="NOT FOUND IN SAMPLE",
                            difference="Unmatched",
                            confidence=0.0,
                            message=f"PDF record not found in Excel sample",
                            page_number=table.page_number,
                        ))
                    else:
                        findings.append(AuditFinding.create(
                            test_type="tracing",
                            status="pass",
                            severity="info",
                            sample_id=best_sample_id,
                            matched_pdf=doc.file_name,
                            field_name="record",
                            extracted_value=str(dict(pdf_row))[:200],
                            expected_value=f"Matched to sample {best_sample_id}",
                            difference="",
                            confidence=0.9,
                            message=f"Traced to sample {best_sample_id}",
                            page_number=table.page_number,
                        ))

        return findings

    def recalculation_test(self, config: AuditTestConfig,
                           documents: list[ProcessedDocument]) -> list[AuditFinding]:
        """Recalculation: verify arithmetic in extracted tables."""
        findings = []

        for doc in documents:
            for table in doc.extracted_tables:
                df = table.data

                # Check column sums if sum_columns specified
                for col_name in config.sum_columns:
                    if col_name not in df.columns:
                        continue

                    # Parse all values in the column
                    values = []
                    for val in df[col_name]:
                        parsed = parse_financial_amount(str(val))
                        if parsed is not None:
                            values.append(parsed)

                    if not values:
                        continue

                    calculated_sum = sum(values[:-1], Decimal("0"))  # Exclude last row (assumed total)
                    reported_total = values[-1] if values else Decimal("0")

                    diff = calculated_sum - reported_total
                    matches = abs(diff) <= config.amount_tolerance

                    findings.append(AuditFinding.create(
                        test_type="recalculation",
                        status="pass" if matches else "fail",
                        severity="info" if matches else "high",
                        sample_id=f"{doc.file_name}_p{table.page_number}",
                        matched_pdf=doc.file_name,
                        field_name=f"{col_name} column sum",
                        extracted_value=str(reported_total),
                        expected_value=str(calculated_sum),
                        difference=str(diff),
                        confidence=1.0 if matches else 0.5,
                        message=f"Column '{col_name}' sum: calculated={calculated_sum}, reported={reported_total}",
                        page_number=table.page_number,
                    ))

                # Cross-footing: check row totals if total_column specified
                if config.total_column and config.total_column in df.columns and config.sum_columns:
                    for row_idx, row in df.iterrows():
                        row_sum = Decimal("0")
                        parseable = True
                        for col in config.sum_columns:
                            if col in df.columns and col != config.total_column:
                                val = parse_financial_amount(str(row.get(col, "")))
                                if val is not None:
                                    row_sum += val
                                else:
                                    parseable = False

                        if not parseable:
                            continue

                        reported = parse_financial_amount(str(row.get(config.total_column, "")))
                        if reported is None:
                            continue

                        diff = row_sum - reported
                        matches = abs(diff) <= config.amount_tolerance

                        if not matches:
                            findings.append(AuditFinding.create(
                                test_type="recalculation",
                                status="fail",
                                severity="medium",
                                sample_id=f"{doc.file_name}_p{table.page_number}_row{row_idx}",
                                matched_pdf=doc.file_name,
                                field_name=f"Row {row_idx} cross-foot",
                                extracted_value=str(reported),
                                expected_value=str(row_sum),
                                difference=str(diff),
                                confidence=0.8,
                                message=f"Row {row_idx}: cross-foot mismatch",
                                page_number=table.page_number,
                            ))

        return findings

    def analytical_test(self, config: AuditTestConfig, documents: list[ProcessedDocument],
                        sample_data: pd.DataFrame) -> list[AuditFinding]:
        """Analytical procedures: ratio analysis, outlier detection, threshold checks."""
        findings = []

        for doc in documents:
            for table in doc.extracted_tables:
                df = table.data

                # For each numeric column, check for outliers
                for col in df.columns:
                    values = []
                    for val in df[col]:
                        parsed = parse_financial_amount(str(val))
                        if parsed is not None:
                            values.append(parsed)

                    if len(values) < 3:
                        continue

                    # IQR-based outlier detection
                    sorted_vals = sorted(values)
                    n = len(sorted_vals)
                    q1 = sorted_vals[n // 4]
                    q3 = sorted_vals[3 * n // 4]
                    iqr = q3 - q1

                    if iqr == 0:
                        continue

                    lower_bound = q1 - Decimal("1.5") * iqr
                    upper_bound = q3 + Decimal("1.5") * iqr

                    for i, val in enumerate(values):
                        if val < lower_bound or val > upper_bound:
                            findings.append(AuditFinding.create(
                                test_type="analytical",
                                status="manual_review",
                                severity="medium",
                                sample_id=f"{doc.file_name}_p{table.page_number}_row{i}",
                                matched_pdf=doc.file_name,
                                field_name=col,
                                extracted_value=str(val),
                                expected_value=f"Range: [{lower_bound}, {upper_bound}]",
                                difference=str(val - q3 if val > upper_bound else val - q1),
                                confidence=0.7,
                                message=f"Outlier detected in '{col}': {val} outside IQR bounds",
                                page_number=table.page_number,
                            ))

        # Compare totals against sample data if available
        if not sample_data.empty and config.field_mappings:
            for pdf_field, excel_field in config.field_mappings.items():
                if excel_field not in sample_data.columns:
                    continue

                # Calculate expected total from sample
                sample_values = []
                for val in sample_data[excel_field]:
                    parsed = parse_financial_amount(str(val))
                    if parsed is not None:
                        sample_values.append(parsed)

                if not sample_values:
                    continue

                sample_total = sum(sample_values, Decimal("0"))

                # Calculate extracted total
                for doc in documents:
                    for table in doc.extracted_tables:
                        if pdf_field not in table.data.columns:
                            continue

                        pdf_values = []
                        for val in table.data[pdf_field]:
                            parsed = parse_financial_amount(str(val))
                            if parsed is not None:
                                pdf_values.append(parsed)

                        if not pdf_values:
                            continue

                        pdf_total = sum(pdf_values, Decimal("0"))

                        if sample_total != 0:
                            pct_diff = abs(pdf_total - sample_total) / abs(sample_total)
                        else:
                            pct_diff = Decimal("0") if pdf_total == 0 else Decimal("1")

                        threshold = config.analytical_threshold_pct
                        matches = pct_diff <= threshold

                        findings.append(AuditFinding.create(
                            test_type="analytical",
                            status="pass" if matches else "fail",
                            severity="info" if matches else "high",
                            sample_id="total_comparison",
                            matched_pdf=doc.file_name,
                            field_name=f"{excel_field} total",
                            extracted_value=str(pdf_total),
                            expected_value=str(sample_total),
                            difference=f"{pct_diff:.2%}",
                            confidence=1.0 - float(pct_diff),
                            message=f"Total comparison: PDF={pdf_total}, Sample={sample_total}, Diff={pct_diff:.2%}",
                        ))

        return findings

    # --- Internal matching helpers ---

    def _find_match_in_table(self, table: ExtractedTable, sample_row: pd.Series,
                             key_fields: list[str],
                             field_mappings: dict[str, str]) -> tuple[pd.Series, float] | None:
        """Find the best matching row in a table for a sample row."""
        df = table.data
        best_row = None
        best_score = 0.0

        for _, pdf_row in df.iterrows():
            score = self._compute_match_score(pdf_row, sample_row, key_fields, field_mappings)
            if score > best_score:
                best_score = score
                best_row = pdf_row

        if best_score >= 0.5:
            return (best_row, best_score)
        return None

    def _compute_match_score(self, pdf_row: pd.Series, sample_row: pd.Series,
                             key_fields: list[str],
                             field_mappings: dict[str, str]) -> float:
        """Compute a weighted match score between a PDF row and a sample row."""
        if not field_mappings:
            return 0.0

        scores = []
        weights = []

        for pdf_field, excel_field in field_mappings.items():
            if pdf_field not in pdf_row.index or excel_field not in sample_row.index:
                continue

            extracted = str(pdf_row[pdf_field])
            expected = sample_row[excel_field]

            result = self.comparator.auto_compare(extracted, expected)

            weight = 2.0 if pdf_field in key_fields else 1.0
            scores.append(result.confidence * weight)
            weights.append(weight)

        if not weights:
            return 0.0

        return sum(scores) / sum(weights)
