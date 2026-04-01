"""Report generation: Excel and CSV export for audit findings."""

import io
from datetime import datetime

import pandas as pd

from audit.models import AuditFinding, AuditReport, AuditTestConfig
from config import t


class ReportGenerator:
    """Generate audit reports in Excel and CSV formats."""

    def generate_report(self, findings: list[AuditFinding], config: AuditTestConfig,
                        documents_processed: list[str]) -> AuditReport:
        """Build an AuditReport from findings."""
        total = len(findings)
        total_pass = sum(1 for f in findings if f.status == "pass")
        total_fail = sum(1 for f in findings if f.status == "fail")
        total_review = sum(1 for f in findings if f.status == "manual_review")

        return AuditReport(
            report_id=datetime.now().strftime("%Y%m%d_%H%M%S"),
            created_at=datetime.now(),
            test_config=config,
            findings=findings,
            total_tested=total,
            total_pass=total_pass,
            total_fail=total_fail,
            total_manual_review=total_review,
            documents_processed=documents_processed,
        )

    def to_excel_bytes(self, report: AuditReport, lang: str = "zh") -> bytes:
        """Generate Excel report as bytes (for Streamlit download)."""
        output = io.BytesIO()

        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            # Sheet 1: Summary
            summary_data = {
                t("report_id", lang) if lang == "zh" else "Report ID": [report.report_id],
                t("date", lang): [report.created_at.strftime("%Y-%m-%d %H:%M:%S")],
                t("select_test_type", lang): [report.test_config.test_type],
                t("total_tested", lang): [report.total_tested],
                t("pass", lang): [report.total_pass],
                t("fail", lang): [report.total_fail],
                t("manual_review", lang): [report.total_manual_review],
                t("pass_rate", lang): [f"{report.pass_rate:.1%}"],
            }
            pd.DataFrame(summary_data).to_excel(
                writer, sheet_name=t("summary", lang), index=False
            )

            # Sheet 2: Findings Detail
            if report.findings:
                findings_data = []
                for f in report.findings:
                    findings_data.append({
                        t("sample_id", lang): f.sample_id,
                        t("status", lang): f.status,
                        t("severity_high", lang).replace(
                            t("severity_high", lang), f.severity
                        ): f.severity,
                        t("matched_pdf", lang): f.matched_pdf,
                        t("field_name", lang) if lang == "zh" else "Field": f.field_name,
                        t("extracted_value", lang): f.extracted_value,
                        t("expected_value", lang): f.expected_value,
                        t("difference", lang): f.difference,
                        t("confidence", lang): f"{f.confidence:.1%}",
                        t("manual_review", lang): "Yes" if f.requires_manual_review else "No",
                        "Message": f.message,
                        t("page", lang): f.page_number,
                    })

                pd.DataFrame(findings_data).to_excel(
                    writer, sheet_name=t("detail", lang), index=False
                )

            # Sheet 3: Documents processed
            if report.documents_processed:
                pd.DataFrame({
                    t("file_name", lang): report.documents_processed
                }).to_excel(
                    writer, sheet_name="Documents", index=False
                )

        return output.getvalue()

    def to_csv_bytes(self, report: AuditReport, lang: str = "zh") -> bytes:
        """Generate CSV report as bytes."""
        if not report.findings:
            return b""

        findings_data = []
        for f in report.findings:
            findings_data.append({
                "sample_id": f.sample_id,
                "test_type": f.test_type,
                "status": f.status,
                "severity": f.severity,
                "matched_pdf": f.matched_pdf,
                "field_name": f.field_name,
                "extracted_value": f.extracted_value,
                "expected_value": f.expected_value,
                "difference": f.difference,
                "confidence": f.confidence,
                "manual_review": f.requires_manual_review,
                "message": f.message,
                "page_number": f.page_number,
            })

        df = pd.DataFrame(findings_data)
        return df.to_csv(index=False).encode("utf-8-sig")  # BOM for Excel compatibility
