"""Report generation: fill Excel columns R-AC with verification results."""

import io
import copy
from datetime import datetime

import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string

from audit.models import DeliveryGroup, VerificationSummary
from config import EXCEL_COLS


# No pre-computed map needed — use _col_idx() directly


def _col_idx(col_letter: str) -> int:
    """Convert column letter (e.g., 'A', 'AA') to 1-based index."""
    return column_index_from_string(col_letter)


class ReportGenerator:
    """Fill verification results into the original Excel template."""

    def fill_excel(self, original_excel_bytes: bytes, groups: list[DeliveryGroup],
                   sheet_name: str | None = None) -> bytes:
        """Fill columns R-AC in the original Excel with verification results.

        Args:
            original_excel_bytes: The original uploaded Excel file bytes.
            groups: Verified delivery groups with results.
            sheet_name: Sheet to modify (None = active sheet).

        Returns:
            Modified Excel file as bytes.
        """
        wb = load_workbook(io.BytesIO(original_excel_bytes))
        ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active

        # Data starts from row 3 (row 1 = title?, row 2 = headers)
        data_start_row = 3

        # Build a map: row_index -> group (row_index is 0-based from data start)
        for group in groups:
            for row_idx in group.row_indices:
                excel_row = data_start_row + row_idx  # actual Excel row number

                # R: 物流公司
                ws.cell(row=excel_row, column=_col_idx("R"),
                        value=group.logistics_company)

                # S: 物流单号
                ws.cell(row=excel_row, column=_col_idx("S"),
                        value=group.logistics_no)

                # T: 签收日期 - 留空不填
                # (don't write anything)

                # U: 客户签收日期
                ws.cell(row=excel_row, column=_col_idx("U"),
                        value=group.customer_sign_date)

                # V: 签收人员
                ws.cell(row=excel_row, column=_col_idx("V"),
                        value=group.signer)

                # W: ① 核查结果
                ws.cell(row=excel_row, column=_col_idx("W"),
                        value=group.check1_result)

                # X: ② 核查结果
                ws.cell(row=excel_row, column=_col_idx("X"),
                        value=group.check2_result)

                # Y: ③ 核查结果
                ws.cell(row=excel_row, column=_col_idx("Y"),
                        value=group.check3_result)

                # Z: ④ 核查结果
                ws.cell(row=excel_row, column=_col_idx("Z"),
                        value=group.check4_result)

                # AA: ⑤ 核查结果
                ws.cell(row=excel_row, column=_col_idx("AA"),
                        value=group.check5_result)

                # AB: 附件索引号
                ws.cell(row=excel_row, column=_col_idx("AB"),
                        value=group.attachment_index)

                # AC: 附件检查结果
                ws.cell(row=excel_row, column=_col_idx("AC"),
                        value=group.attachment_result)

        output = io.BytesIO()
        wb.save(output)
        return output.getvalue()

    def generate_summary_df(self, groups: list[DeliveryGroup]) -> pd.DataFrame:
        """Generate a summary DataFrame for display in Streamlit."""
        rows = []
        for g in groups:
            all_pass = all(r == "✓" for r in [
                g.check1_result, g.check2_result, g.check3_result,
                g.check4_result, g.check5_result
            ])
            rows.append({
                "出库单号": g.delivery_no,
                "客户名称": g.customer_name,
                "出库数量": g.total_qty,
                "含税收入": str(g.total_revenue_tax),
                "①合同": g.check1_result,
                "②出库单": g.check2_result,
                "③金额": g.check3_result,
                "④时点": g.check4_result,
                "⑤授权": g.check5_result,
                "总结": "全部通过" if all_pass else "存在异常",
            })
        return pd.DataFrame(rows)
